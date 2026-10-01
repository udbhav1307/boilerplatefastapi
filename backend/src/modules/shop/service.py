"""Business rules for shops: opening one, editing it, its weekly hours and closures.

Methods that act on an owner's shop take the ``Shop`` row itself, already resolved from the
logged-in user (see ``dependencies.py``), never a shop id from the request. That is what keeps
one owner away from another owner's shop.
"""

import os
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ClosureNotFoundError, ConflictError, RuleViolationError, ShopNotFoundError
from ..role.defaults import OWNER_ROLE
from ..role.service import assign_role
from .models import Shop, ShopClosure, ShopHours
from .schemas import ClosureCreate, ClosureRead, DayHours, ShopCreate, ShopRead, ShopUpdate, WeeklyHoursSet


def shop_today(shop: Shop) -> str:
    """Today's date where the shop is, which can differ from the server's date."""
    return datetime.now(ZoneInfo(shop.timezone)).date()


class ShopService:
    # --- the shop itself -----------------------------------------------------------

    async def create(self, owner_user_id: int, data: ShopCreate, db: AsyncSession) -> dict[str, Any]:
        """Open a shop; its creator becomes an owner. Shop and role are saved together or not at all."""
        if await self.get_owned_by(owner_user_id, db) is not None:
            raise ConflictError("You already have a shop.")
        assert data.slug is not None  # ShopCreate always derives one
        await self._ensure_slug_free(data.slug, db)

        shop = Shop(owner_user_id=owner_user_id, **data.model_dump())
        try:
            db.add(shop)
            await db.flush()
            await assign_role(db, owner_user_id, OWNER_ROLE, commit=False)
            await db.commit()
        except IntegrityError as error:
            # Two requests raced for the same slug or owner; the unique constraints decided.
            await db.rollback()
            raise ConflictError("That shop or web address was just taken. Please try another.") from error
        except Exception:
            await db.rollback()
            raise
        return _read(shop)

    async def get_owned_by(self, owner_user_id: int, db: AsyncSession) -> Shop | None:
        """The (not deleted) shop this user owns, if any."""
        result = await db.execute(select(Shop).where(Shop.owner_user_id == owner_user_id, Shop.is_deleted.is_(False)))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str, db: AsyncSession) -> dict[str, Any]:
        shop = await db.scalar(select(Shop).where(Shop.slug == slug))
        if shop is None:
            raise ShopNotFoundError(f"No shop at '{slug}'")
        return _read(shop)

    async def update(self, shop: Shop, data: ShopUpdate, db: AsyncSession) -> dict[str, Any]:
        changes = data.model_dump(exclude_unset=True)
        if "slug" in changes and changes["slug"] != shop.slug:
            await self._ensure_slug_free(changes["slug"], db)

        for field, value in changes.items():
            setattr(shop, field, value)
        try:
            await db.commit()
        except IntegrityError as error:
            await db.rollback()
            raise ConflictError("That web address was just taken. Please try another.") from error
        return _read(shop)

    async def _ensure_slug_free(self, slug: str, db: AsyncSession) -> None:
        if await db.scalar(select(Shop.id).where(Shop.slug == slug)) is not None:
            raise ConflictError(f"The web address '{slug}' is already taken.")

    # --- weekly hours ----------------------------------------------------------------

    async def get_hours(self, shop_id: int, db: AsyncSession) -> list[dict[str, Any]]:
        rows = await db.scalars(select(ShopHours).where(ShopHours.shop_id == shop_id).order_by(ShopHours.weekday))
        return [DayHours.model_validate(row).model_dump() for row in rows]

    async def set_hours(self, shop: Shop, week: WeeklyHoursSet, db: AsyncSession) -> list[dict[str, Any]]:
        """Replace the whole week in one transaction; days not listed become closed."""
        try:
            await db.execute(delete(ShopHours).where(ShopHours.shop_id == shop.id))
            db.add_all(
                ShopHours(shop_id=shop.id, weekday=day.weekday, open_time=day.open_time, close_time=day.close_time)
                for day in week.days
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return await self.get_hours(shop.id, db)

    # --- closures --------------------------------------------------------------------

    async def list_closures(self, shop: Shop, db: AsyncSession, *, today: date | None = None) -> list[dict[str, Any]]:
        """Closures from today onwards, soonest first."""
        today = today or shop_today(shop)
        rows = await db.scalars(
            select(ShopClosure)
            .where(ShopClosure.shop_id == shop.id, ShopClosure.closed_on >= today)
            .order_by(ShopClosure.closed_on)
        )
        return [ClosureRead.model_validate(row).model_dump() for row in rows]

    async def add_closure(
        self, shop: Shop, data: ClosureCreate, db: AsyncSession, *, today: date | None = None
    ) -> dict[str, Any]:
        if data.closed_on < (today or shop_today(shop)):
            raise RuleViolationError("A closure can't be in the past.")

        closure = ShopClosure(shop_id=shop.id, closed_on=data.closed_on, reason=data.reason)
        db.add(closure)
        try:
            await db.commit()
        except IntegrityError as error:
            await db.rollback()
            raise ConflictError(f"The shop is already closed on {data.closed_on}.") from error
        return ClosureRead.model_validate(closure).model_dump()

    async def remove_closure(self, shop: Shop, closure_id: int, db: AsyncSession) -> None:
        # Scoped by shop: another shop's closure id is "not found", not "forbidden".
        result = await db.execute(
            delete(ShopClosure).where(ShopClosure.id == closure_id, ShopClosure.shop_id == shop.id)
        )
        if result.rowcount == 0:  # type: ignore[attr-defined]
            # Nothing changed, so there's nothing to roll back (and a rollback would expire
            # every loaded object, e.g. the caller's Shop).
            raise ClosureNotFoundError(f"Closure {closure_id} not found")
        await db.commit()


def _read(shop: Shop) -> dict[str, Any]:
    return ShopRead.model_validate(shop).model_dump()
