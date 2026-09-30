"""The roles every environment needs, and a startup sync that makes the database hold them.

The code is the source of truth: ``DEFAULT_ROLES`` lists each role and the permissions it
must have. ``ensure_default_roles()`` runs at startup and adds whatever is missing. It never
removes anything, so a permission an admin granted by hand survives a restart.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Role, RolePermission
from .permission_registry import all_permissions, discover_permissions

OWNER_ROLE = "owner"
STAFF_ROLE = "staff"
CUSTOMER_ROLE = "customer"


@dataclass(frozen=True)
class DefaultRole:
    description: str
    permissions: frozenset[str]


DEFAULT_ROLES: dict[str, DefaultRole] = {
    OWNER_ROLE: DefaultRole(
        description="Shop owner: manages the shop, its staff, services and every booking.",
        permissions=frozenset({"shop.manage", "staff.manage", "catalog.manage", "booking.manage_shop"}),
    ),
    STAFF_ROLE: DefaultRole(
        description="Barber: sees their own schedule and clients, marks their bookings done or no-show.",
        permissions=frozenset({"staff.view_own_schedule", "booking.update_own_status"}),
    ),
    CUSTOMER_ROLE: DefaultRole(
        description="Customer: books appointments and cancels their own.",
        permissions=frozenset({"booking.create", "booking.cancel_own"}),
    ),
}


async def ensure_default_roles(db: AsyncSession) -> None:
    """Create any missing default role or role permission (idempotent, safe to run concurrently).

    Uses ``INSERT ... ON CONFLICT DO NOTHING`` rather than check-then-insert, so several app
    workers starting at the same moment can't collide on the unique role name.
    """
    discover_permissions()
    unknown = {name for role in DEFAULT_ROLES.values() for name in role.permissions} - all_permissions()
    if unknown:
        raise ValueError(f"Default roles name unregistered permissions: {sorted(unknown)}")

    now = datetime.now(UTC)

    await db.execute(
        insert(Role)
        .values(
            [
                {"name": name, "description": role.description, "created_at": now, "updated_at": now}
                for name, role in DEFAULT_ROLES.items()
            ]
        )
        .on_conflict_do_nothing(index_elements=["name"])
    )

    role_ids = dict((await db.execute(select(Role.name, Role.id).where(Role.name.in_(DEFAULT_ROLES)))).tuples().all())

    await db.execute(
        insert(RolePermission)
        .values(
            [
                {"role_id": role_ids[name], "permission_name": permission, "created_at": now, "updated_at": now}
                for name, role in DEFAULT_ROLES.items()
                for permission in sorted(role.permissions)
            ]
        )
        .on_conflict_do_nothing(index_elements=["role_id", "permission_name"])
    )

    await db.commit()
