"""The default role definitions only name permissions that actually exist."""

from src.modules.role.defaults import DEFAULT_ROLES
from src.modules.role.permission_registry import all_permissions


def test_default_roles_are_owner_staff_and_customer():
    assert set(DEFAULT_ROLES) == {"owner", "staff", "customer"}


def test_every_default_permission_is_registered():
    registered = all_permissions()

    for role_name, role in DEFAULT_ROLES.items():
        unknown = role.permissions - registered
        assert not unknown, f"{role_name} names unregistered permissions: {sorted(unknown)}"


def test_customers_cannot_manage_anything():
    customer = DEFAULT_ROLES["customer"].permissions

    assert not any(name.endswith(".manage") or name.endswith(".manage_shop") for name in customer)
