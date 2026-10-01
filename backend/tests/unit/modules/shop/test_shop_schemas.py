"""Shop request schemas reject malformed input before any business logic runs."""

from datetime import date, time

import pytest
from pydantic import ValidationError

from src.modules.shop.schemas import ClosureCreate, DayHours, ShopCreate, ShopUpdate, WeeklyHoursSet, slugify


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Fade Factory", "fade-factory"),
        ("  Fade   Factory!! ", "fade-factory"),
        ("Ravi's Cuts & Shaves", "ravi-s-cuts-shaves"),
        ("Studio 54", "studio-54"),
        ("--Sharp--Edge--", "sharp-edge"),
    ],
)
def test_slugify_makes_url_friendly_names(text: str, expected: str):
    assert slugify(text) == expected


def test_a_shop_gets_its_slug_from_its_name():
    shop = ShopCreate(name="Fade Factory", timezone="Asia/Kolkata")

    assert shop.slug == "fade-factory"


def test_a_given_slug_is_normalised():
    shop = ShopCreate(name="Fade Factory", slug="My Shop", timezone="Asia/Kolkata")

    assert shop.slug == "my-shop"


def test_a_name_without_letters_or_digits_needs_an_explicit_slug():
    with pytest.raises(ValidationError):
        ShopCreate(name="!!!", timezone="Asia/Kolkata")


@pytest.mark.parametrize("zone", ["Mars/Base", "IST", "", "asia/kolkata"])
def test_the_timezone_must_be_a_real_iana_zone(zone: str):
    with pytest.raises(ValidationError):
        ShopCreate(name="Fade Factory", timezone=zone)


@pytest.mark.parametrize(
    "rules",
    [
        {"min_notice_minutes": -1},
        {"max_days_ahead": 0},
        {"max_days_ahead": 400},
        {"cancel_window_minutes": -1},
        {"slot_step_minutes": 7},
    ],
)
def test_booking_rules_are_checked(rules: dict):
    with pytest.raises(ValidationError):
        ShopCreate(name="Fade Factory", timezone="Asia/Kolkata", **rules)


def test_unknown_fields_are_rejected():
    """A client can't smuggle in owner_user_id or other server-side fields."""
    with pytest.raises(ValidationError):
        ShopCreate(name="Fade Factory", timezone="Asia/Kolkata", owner_user_id=1)


def test_an_update_only_carries_the_fields_sent():
    update = ShopUpdate(phone="+91 98765 43210")

    assert update.model_dump(exclude_unset=True) == {"phone": "+91 98765 43210"}


def test_an_update_checks_the_timezone_too():
    with pytest.raises(ValidationError):
        ShopUpdate(timezone="Mars/Base")


@pytest.mark.parametrize(
    "weekday, open_time, close_time",
    [(7, time(9), time(17)), (-1, time(9), time(17)), (0, time(17), time(9)), (0, time(9), time(9))],
)
def test_day_hours_must_be_a_real_day_and_open_before_close(weekday: int, open_time: time, close_time: time):
    with pytest.raises(ValidationError):
        DayHours(weekday=weekday, open_time=open_time, close_time=close_time)


def test_a_week_lists_each_day_once():
    with pytest.raises(ValidationError):
        WeeklyHoursSet(
            days=[
                DayHours(weekday=0, open_time=time(9), close_time=time(17)),
                DayHours(weekday=0, open_time=time(10), close_time=time(18)),
            ]
        )


def test_an_empty_week_means_closed_every_day():
    assert WeeklyHoursSet(days=[]).days == []


def test_a_closure_reason_is_optional():
    assert ClosureCreate(closed_on=date(2026, 12, 25)).reason is None
