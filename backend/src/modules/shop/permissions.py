"""Shop module permissions."""

from enum import StrEnum

from ..role.permission_registry import register_permissions


@register_permissions("shop")
class ShopPermission(StrEnum):
    """Permissions for a shop's own settings."""

    MANAGE = "shop.manage"
