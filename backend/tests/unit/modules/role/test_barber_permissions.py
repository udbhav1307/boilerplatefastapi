"""The barber shop permissions are registered, so roles can be granted them."""

from src.modules.role.permission_registry import all_permissions, permission_groups

EXPECTED_GROUPS = {
    "shop": ("shop.manage",),
    "staff": ("staff.manage", "staff.view_own_schedule"),
    "catalog": ("catalog.manage",),
    "booking": (
        "booking.create",
        "booking.cancel_own",
        "booking.manage_shop",
        "booking.update_own_status",
    ),
}


def test_barber_shop_permissions_are_registered():
    registered = all_permissions()

    for names in EXPECTED_GROUPS.values():
        for name in names:
            assert name in registered, f"{name} is not registered"


def test_barber_shop_permissions_are_grouped_by_resource():
    groups = permission_groups()

    for resource, names in EXPECTED_GROUPS.items():
        assert groups.get(resource) == names
