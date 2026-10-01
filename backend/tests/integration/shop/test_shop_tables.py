"""The shop tables enforce their own rules, so even buggy code can't store bad data."""

from datetime import date, time

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.shop.models import Shop, ShopClosure, ShopHours

pytestmark = pytest.mark.asyncio


def _shop(owner_id: int, slug: str = "fade-factory", **overrides) -> Shop:
    values = {"owner_user_id": owner_id, "name": "Fade Factory", "slug": slug, "timezone": "Asia/Kolkata"}
    values.update(overrides)
    return Shop(**values)


async def _save(db: AsyncSession, *rows) -> None:
    db.add_all(rows)
    await db.commit()


async def _assert_rejected(db: AsyncSession, *rows) -> None:
    db.add_all(rows)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_a_shop_with_hours_and_a_closure_is_stored(db_session: AsyncSession, test_user: dict):
    shop = _shop(test_user["id"])
    await _save(db_session, shop)
    await _save(
        db_session,
        ShopHours(shop_id=shop.id, weekday=0, open_time=time(9), close_time=time(20)),
        ShopClosure(shop_id=shop.id, closed_on=date(2026, 12, 25), reason="Christmas"),
    )

    stored = await db_session.scalar(select(Shop).where(Shop.slug == "fade-factory"))
    assert stored is not None
    assert stored.timezone == "Asia/Kolkata"
    assert stored.min_notice_minutes == 60
    assert stored.slot_step_minutes == 15


async def test_slugs_are_unique(db_session: AsyncSession, test_user: dict, test_user_2: dict):
    await _save(db_session, _shop(test_user["id"]))

    await _assert_rejected(db_session, _shop(test_user_2["id"]))


async def test_an_owner_has_one_shop(db_session: AsyncSession, test_user: dict):
    await _save(db_session, _shop(test_user["id"]))

    await _assert_rejected(db_session, _shop(test_user["id"], slug="second-shop"))


@pytest.mark.parametrize(
    "weekday, open_time, close_time",
    [(7, time(9), time(17)), (-1, time(9), time(17)), (0, time(17), time(9)), (0, time(9), time(9))],
)
async def test_hours_must_be_a_real_weekday_and_open_before_close(
    db_session: AsyncSession, test_user: dict, weekday: int, open_time: time, close_time: time
):
    shop = _shop(test_user["id"])
    await _save(db_session, shop)

    await _assert_rejected(
        db_session, ShopHours(shop_id=shop.id, weekday=weekday, open_time=open_time, close_time=close_time)
    )


async def test_one_hours_row_per_weekday(db_session: AsyncSession, test_user: dict):
    shop = _shop(test_user["id"])
    await _save(db_session, shop)
    await _save(db_session, ShopHours(shop_id=shop.id, weekday=1, open_time=time(9), close_time=time(13)))

    await _assert_rejected(
        db_session, ShopHours(shop_id=shop.id, weekday=1, open_time=time(14), close_time=time(18))
    )


async def test_one_closure_per_date(db_session: AsyncSession, test_user: dict):
    shop = _shop(test_user["id"])
    await _save(db_session, shop)
    await _save(db_session, ShopClosure(shop_id=shop.id, closed_on=date(2026, 12, 25)))

    await _assert_rejected(db_session, ShopClosure(shop_id=shop.id, closed_on=date(2026, 12, 25)))


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_notice_minutes": -1},
        {"max_days_ahead": 0},
        {"max_days_ahead": 366},
        {"cancel_window_minutes": -5},
        {"slot_step_minutes": 7},
    ],
)
async def test_booking_rules_must_be_sensible(db_session: AsyncSession, test_user: dict, overrides: dict):
    await _assert_rejected(db_session, _shop(test_user["id"], **overrides))


async def test_deleting_a_shop_deletes_its_hours_and_closures(db_session: AsyncSession, test_user: dict):
    shop = _shop(test_user["id"])
    await _save(db_session, shop)
    await _save(
        db_session,
        ShopHours(shop_id=shop.id, weekday=0, open_time=time(9), close_time=time(20)),
        ShopClosure(shop_id=shop.id, closed_on=date(2026, 12, 25)),
    )

    await db_session.execute(delete(Shop).where(Shop.id == shop.id))
    await db_session.commit()

    assert await db_session.scalar(select(func.count()).select_from(ShopHours)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ShopClosure)) == 0
