"""Catalog module permissions."""

from enum import StrEnum

from ..role.permission_registry import register_permissions


@register_permissions("catalog")
class CatalogPermission(StrEnum):
    """Permissions for a shop's services and prices."""

    MANAGE = "catalog.manage"
