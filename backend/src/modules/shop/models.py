"""A barber shop, its weekly opening hours and the dates it is closed."""

from datetime import date, time

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, SmallInteger, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin
from ...infrastructure.database.session import Base
from .constants import (
    ADDRESS_MAX_LENGTH,
    ALLOWED_SLOT_STEPS,
    MAX_BOOKING_HORIZON_DAYS,
    NAME_MAX_LENGTH,
    PHONE_MAX_LENGTH,
    REASON_MAX_LENGTH,
    SLUG_MAX_LENGTH,
    TIMEZONE_MAX_LENGTH,
)


class Shop(Base, TimestampMixin, SoftDeleteMixin):
    """A shop, owned by one user, with the booking rules its customers follow."""

    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint("min_notice_minutes >= 0", name="min_notice_not_negative"),
        CheckConstraint(f"max_days_ahead BETWEEN 1 AND {MAX_BOOKING_HORIZON_DAYS}", name="max_days_ahead_range"),
        CheckConstraint("cancel_window_minutes >= 0", name="cancel_window_not_negative"),
        CheckConstraint(
            f"slot_step_minutes IN ({', '.join(str(step) for step in ALLOWED_SLOT_STEPS)})",
            name="slot_step_allowed",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    # One shop per owner for now; a multi-branch owner would drop this unique constraint.
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    slug: Mapped[str] = mapped_column(String(SLUG_MAX_LENGTH), unique=True, index=True)
    # IANA zone name, e.g. "Asia/Kolkata". Bookings are stored in UTC and shown in this zone.
    timezone: Mapped[str] = mapped_column(String(TIMEZONE_MAX_LENGTH))
    address: Mapped[str | None] = mapped_column(String(ADDRESS_MAX_LENGTH), default=None)
    phone: Mapped[str | None] = mapped_column(String(PHONE_MAX_LENGTH), default=None)

    # Booking rules, chosen per shop.
    min_notice_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_days_ahead: Mapped[int] = mapped_column(Integer, default=30)
    cancel_window_minutes: Mapped[int] = mapped_column(Integer, default=120)
    slot_step_minutes: Mapped[int] = mapped_column(Integer, default=15)

    def __repr__(self) -> str:
        return self.name


class ShopHours(Base, TimestampMixin):
    """Opening hours for one weekday. A weekday with no row is a closed day."""

    __tablename__ = "shop_hours"
    __table_args__ = (
        UniqueConstraint("shop_id", "weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("close_time > open_time", name="open_before_close"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday ... 6 = Sunday
    open_time: Mapped[time] = mapped_column(Time)
    close_time: Mapped[time] = mapped_column(Time)


class ShopClosure(Base, TimestampMixin):
    """A single date the shop is closed (holiday, renovation...)."""

    __tablename__ = "shop_closures"
    __table_args__ = (UniqueConstraint("shop_id", "closed_on"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    closed_on: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(REASON_MAX_LENGTH), default=None)
