"""Staff module permissions."""

from enum import StrEnum

from ..role.permission_registry import register_permissions


@register_permissions("staff")
class StaffPermission(StrEnum):
    """Permissions for barbers (staff members) of a shop."""

    MANAGE = "staff.manage"
    VIEW_OWN_SCHEDULE = "staff.view_own_schedule"
