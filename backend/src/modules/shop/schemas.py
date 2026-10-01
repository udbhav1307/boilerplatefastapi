"""Request and response shapes for shops, their weekly hours and closures."""

import re
from datetime import date, datetime, time
from functools import lru_cache
from typing import Annotated, Self
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .constants import (
    ADDRESS_MAX_LENGTH,
    ALLOWED_SLOT_STEPS,
    MAX_BOOKING_HORIZON_DAYS,
    NAME_MAX_LENGTH,
    PHONE_MAX_LENGTH,
    REASON_MAX_LENGTH,
    SLUG_MAX_LENGTH,
)

_NOT_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Turn a display name into a URL-friendly slug: "Fade Factory!" -> "fade-factory"."""
    return _NOT_SLUG_CHARS.sub("-", text.lower()).strip("-")[:SLUG_MAX_LENGTH].strip("-")


@lru_cache(maxsize=1)
def _known_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def _check_timezone(value: str) -> str:
    # Exact match against the IANA list. ZoneInfo() alone would accept "asia/kolkata" on a
    # case-insensitive filesystem (macOS) and reject it on Linux.
    if value not in _known_timezones():
        raise ValueError(f"Unknown timezone '{value}'. Use an IANA name such as 'Asia/Kolkata'.")
    return value


def _check_slot_step(value: int) -> int:
    if value not in ALLOWED_SLOT_STEPS:
        raise ValueError(f"Slot step must be one of {ALLOWED_SLOT_STEPS} minutes.")
    return value


Timezone = Annotated[str, AfterValidator(_check_timezone)]
SlotStep = Annotated[int, AfterValidator(_check_slot_step)]
NoticeMinutes = Annotated[int, Field(ge=0, le=7 * 24 * 60)]
HorizonDays = Annotated[int, Field(ge=1, le=MAX_BOOKING_HORIZON_DAYS)]
CancelWindowMinutes = Annotated[int, Field(ge=0, le=7 * 24 * 60)]


class ShopCreate(BaseModel):
    """What an owner sends to open a shop. The slug defaults to one made from the name."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=NAME_MAX_LENGTH, examples=["Fade Factory"])]
    slug: Annotated[str | None, Field(default=None, max_length=SLUG_MAX_LENGTH, examples=["fade-factory"])]
    timezone: Annotated[Timezone, Field(examples=["Asia/Kolkata"])]
    address: Annotated[str | None, Field(default=None, max_length=ADDRESS_MAX_LENGTH)]
    phone: Annotated[str | None, Field(default=None, max_length=PHONE_MAX_LENGTH)]
    min_notice_minutes: NoticeMinutes = 60
    max_days_ahead: HorizonDays = 30
    cancel_window_minutes: CancelWindowMinutes = 120
    slot_step_minutes: SlotStep = 15

    @model_validator(mode="after")
    def _derive_slug(self) -> Self:
        self.slug = slugify(self.slug if self.slug is not None else self.name)
        if not self.slug:
            raise ValueError("Couldn't make a web address from the name; send a 'slug' with letters or digits.")
        return self


class ShopUpdate(BaseModel):
    """Owner's changes to their shop; only the fields sent are changed."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)]
    slug: Annotated[str | None, Field(default=None, max_length=SLUG_MAX_LENGTH)]
    timezone: Timezone | None = None
    address: Annotated[str | None, Field(default=None, max_length=ADDRESS_MAX_LENGTH)]
    phone: Annotated[str | None, Field(default=None, max_length=PHONE_MAX_LENGTH)]
    min_notice_minutes: NoticeMinutes | None = None
    max_days_ahead: HorizonDays | None = None
    cancel_window_minutes: CancelWindowMinutes | None = None
    slot_step_minutes: SlotStep | None = None

    @field_validator("slug")
    @classmethod
    def _normalise_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        slug = slugify(value)
        if not slug:
            raise ValueError("The slug needs letters or digits.")
        return slug


class ShopRead(BaseModel):
    """A shop as shown to anyone. The owner's user id is deliberately left out."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    timezone: str
    address: str | None
    phone: str | None
    min_notice_minutes: int
    max_days_ahead: int
    cancel_window_minutes: int
    slot_step_minutes: int
    created_at: datetime


class DayHours(BaseModel):
    """Opening hours for one weekday (0 = Monday ... 6 = Sunday)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    weekday: Annotated[int, Field(ge=0, le=6)]
    open_time: Annotated[time, Field(examples=["09:00"])]
    close_time: Annotated[time, Field(examples=["20:00"])]

    @model_validator(mode="after")
    def _open_before_close(self) -> Self:
        if self.close_time <= self.open_time:
            raise ValueError("Closing time must be after opening time.")
        return self


class WeeklyHoursSet(BaseModel):
    """The full week. Days that aren't listed are closed; an empty list closes every day."""

    model_config = ConfigDict(extra="forbid")

    days: Annotated[list[DayHours], Field(max_length=7)]

    @field_validator("days")
    @classmethod
    def _each_day_once(cls, days: list[DayHours]) -> list[DayHours]:
        weekdays = [day.weekday for day in days]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError("Each weekday can appear only once.")
        return sorted(days, key=lambda day: day.weekday)


class ClosureCreate(BaseModel):
    """A date the shop is closed."""

    model_config = ConfigDict(extra="forbid")

    closed_on: Annotated[date, Field(examples=["2026-12-25"])]
    reason: Annotated[str | None, Field(default=None, max_length=REASON_MAX_LENGTH, examples=["Christmas"])]


class ClosureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    closed_on: date
    reason: str | None
