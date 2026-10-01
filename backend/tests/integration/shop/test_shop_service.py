"""ShopService business rules, against a real database."""

from datetime import date, time

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.dependencies import load_permissions
from src.modules.common.exceptions import (
    ClosureNotFoundError,
    ConflictError,
    RoleNotFoundError,
    RuleViolationError,
    ShopNotFoundError,
)
from src.modules.role.models import Role
from src.modules.shop.models import Shop
from src.modules.shop.schemas import ClosureCreate, DayHours, ShopCreate, ShopUpdate, WeeklyHoursSet
from src.modules.shop.service import ShopService

pytestmark = pytest.mark.asyncio

service = ShopService()
TODAY = date(2026, 10, 1)


def _new_shop(name: str = "Fade Factory", **extra) -> ShopCreate:
    return ShopCreate(name=name, timezone="Asia/Kolkata", **extra)


async def _owned_shop(db: AsyncSession, owner_id: int, name: str = "Fade Factory") -> Shop:
    await service.create(owner_id, _new_shop(name), db)
    shop = await service.get_owned_by(owner_id, db)
    assert shop is not None
    return shop


# --- creating a shop -------------------------------------------------------------


async def test_creating_a_shop_makes_the_creator_its_owner(db_session: AsyncSession, test_user: dict):
    created = await service.create(test_user["id"], _new_shop(), db_session)

    assert created["slug"] == "fade-factory"
    assert "owner_user_id" not in created
    assert "shop.manage" in await load_permissions(db_session, test_user["id"])


async def test_an_owner_can_open_only_one_shop(db_session: AsyncSession, test_user: dict):
    await service.create(test_user["id"], _new_shop(), db_session)

    with pytest.raises(ConflictError, match="already have a shop"):
        await service.create(test_user["id"], _new_shop("Second Shop"), db_session)


async def test_a_taken_web_address_is_refused(db_session: AsyncSession, test_user: dict, test_user_2: dict):
    await service.create(test_user["id"], _new_shop(), db_session)

    with pytest.raises(ConflictError, match="fade-factory"):
        await service.create(test_user_2["id"], _new_shop(), db_session)


async def test_no_shop_is_saved_when_the_owner_role_is_missing(db_session: AsyncSession, test_user: dict):
    await db_session.execute(delete(Role).where(Role.name == "owner"))
    await db_session.commit()

    with pytest.raises(RoleNotFoundError):
        await service.create(test_user["id"], _new_shop(), db_session)

    assert await db_session.scalar(select(func.count()).select_from(Shop)) == 0


# --- reading and updating ------------------------------------------------------------


async def test_a_shop_is_found_by_its_slug(db_session: AsyncSession, test_user: dict):
    await service.create(test_user["id"], _new_shop(), db_session)

    assert (await service.get_by_slug("fade-factory", db_session))["name"] == "Fade Factory"


async def test_an_unknown_or_deleted_shop_is_not_found(db_session: AsyncSession, test_user: dict):
    shop = await _owned_shop(db_session, test_user["id"])
    shop.is_deleted = True
    await db_session.commit()

    for slug in ("no-such-shop", "fade-factory"):
        with pytest.raises(ShopNotFoundError):
            await service.get_by_slug(slug, db_session)


async def test_an_update_changes_only_what_was_sent(db_session: AsyncSession, test_user: dict):
    shop = await _owned_shop(db_session, test_user["id"])

    updated = await service.update(shop, ShopUpdate(phone="+91 98765 43210", min_notice_minutes=30), db_session)

    assert updated["phone"] == "+91 98765 43210"
    assert updated["min_notice_minutes"] == 30
    assert updated["name"] == "Fade Factory"


async def test_an_update_cannot_take_another_shops_slug(
    db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    shop = await _owned_shop(db_session, test_user["id"])
    await service.create(test_user_2["id"], _new_shop("Sharp Edge"), db_session)

    with pytest.raises(ConflictError):
        await service.update(shop, ShopUpdate(slug="sharp-edge"), db_session)

    # Re-sending your own slug is not a conflict.
    assert (await service.update(shop, ShopUpdate(slug="fade-factory"), db_session))["slug"] == "fade-factory"


# --- weekly hours --------------------------------------------------------------------


async def test_setting_hours_replaces_the_whole_week(db_session: AsyncSession, test_user: dict):
    shop = await _owned_shop(db_session, test_user["id"])
    await service.set_hours(
        shop,
        WeeklyHoursSet(days=[DayHours(weekday=d, open_time=time(9), close_time=time(20)) for d in range(6)]),
        db_session,
    )

    week = await service.set_hours(
        shop,
        WeeklyHoursSet(
            days=[
                DayHours(weekday=5, open_time=time(8), close_time=time(22)),
                DayHours(weekday=0, open_time=time(10), close_time=time(18)),
            ]
        ),
        db_session,
    )

    assert [(day["weekday"], day["open_time"]) for day in week] == [(0, time(10)), (5, time(8))]
    assert await service.get_hours(shop.id, db_session) == week


async def test_an_empty_week_closes_every_day(db_session: AsyncSession, test_user: dict):
    shop = await _owned_shop(db_session, test_user["id"])
    await service.set_hours(
        shop, WeeklyHoursSet(days=[DayHours(weekday=0, open_time=time(9), close_time=time(17))]), db_session
    )

    assert await service.set_hours(shop, WeeklyHoursSet(days=[]), db_session) == []


# --- closures ------------------------------------------------------------------------


async def test_a_future_closure_is_added_and_listed(db_session: AsyncSession, test_user: dict):
    shop = await _owned_shop(db_session, test_user["id"])

    await service.add_closure(shop, ClosureCreate(closed_on=date(2026, 12, 25), reason="Christmas"), db_session, today=TODAY)
    await service.add_closure(shop, ClosureCreate(closed_on=date(2026, 10, 2)), db_session, today=TODAY)

    closures = await service.list_closures(shop, db_session, today=TODAY)
    assert [c["closed_on"] for c in closures] == [date(2026, 10, 2), date(2026, 12, 25)]


async def test_a_closure_in_the_past_is_refused(db_session: AsyncSession, test_user: dict):
    shop = await _owned_shop(db_session, test_user["id"])

    with pytest.raises(RuleViolationError, match="past"):
        await service.add_closure(shop, ClosureCreate(closed_on=date(2026, 9, 30)), db_session, today=TODAY)


async def test_the_same_date_cannot_be_closed_twice(db_session: AsyncSession, test_user: dict):
    shop = await _owned_shop(db_session, test_user["id"])
    await service.add_closure(shop, ClosureCreate(closed_on=date(2026, 12, 25)), db_session, today=TODAY)

    with pytest.raises(ConflictError):
        await service.add_closure(shop, ClosureCreate(closed_on=date(2026, 12, 25)), db_session, today=TODAY)


async def test_past_closures_are_not_listed(db_session: AsyncSession, test_user: dict):
    shop = await _owned_shop(db_session, test_user["id"])
    await service.add_closure(shop, ClosureCreate(closed_on=date(2026, 10, 5)), db_session, today=TODAY)

    assert await service.list_closures(shop, db_session, today=date(2026, 10, 6)) == []


async def test_an_owner_cannot_remove_another_shops_closure(
    db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    mine = await _owned_shop(db_session, test_user["id"])
    theirs = await _owned_shop(db_session, test_user_2["id"], name="Sharp Edge")
    their_closure = await service.add_closure(theirs, ClosureCreate(closed_on=date(2026, 12, 25)), db_session, today=TODAY)

    with pytest.raises(ClosureNotFoundError):
        await service.remove_closure(mine, their_closure["id"], db_session)

    await service.remove_closure(theirs, their_closure["id"], db_session)
    assert await service.list_closures(theirs, db_session, today=TODAY) == []
