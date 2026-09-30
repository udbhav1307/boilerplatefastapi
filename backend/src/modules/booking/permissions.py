"""Booking module permissions."""

from enum import StrEnum

from ..role.permission_registry import register_permissions


@register_permissions("booking")
class BookingPermission(StrEnum):
    """Permissions for appointments."""

    CREATE = "booking.create"
    CANCEL_OWN = "booking.cancel_own"
    MANAGE_SHOP = "booking.manage_shop"
    UPDATE_OWN_STATUS = "booking.update_own_status"
