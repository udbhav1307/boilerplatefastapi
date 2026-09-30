"""ensure_default_roles() makes the database hold at least the roles the code defines."""

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.role.defaults import DEFAULT_ROLES, ensure_default_roles
from src.modules.role.models import Role, RolePermission

pytestmark = pytest.mark.asyncio


async def _permissions_by_role(db: AsyncSession) -> dict[str, set[str]]:
    rows = await db.execute(
        select(Role.name, RolePermission.permission_name).join(RolePermission, RolePermission.role_id == Role.id)
    )
    result: dict[str, set[str]] = {}
    for role_name, permission_name in rows:
        result.setdefault(role_name, set()).add(permission_name)
    return result


async def _start_empty(db: AsyncSession) -> None:
    """Remove every role, so a test can watch them being created."""
    await db.execute(delete(Role))
    await db.commit()


async def test_creates_every_default_role_with_its_permissions(db_session: AsyncSession):
    await _start_empty(db_session)

    await ensure_default_roles(db_session)

    stored = await _permissions_by_role(db_session)
    for role_name, role in DEFAULT_ROLES.items():
        assert stored.get(role_name) == set(role.permissions)


async def test_running_twice_creates_no_duplicates(db_session: AsyncSession):
    await _start_empty(db_session)

    await ensure_default_roles(db_session)
    await ensure_default_roles(db_session)

    role_count = await db_session.scalar(select(func.count()).select_from(Role))
    permission_count = await db_session.scalar(select(func.count()).select_from(RolePermission))
    assert role_count == len(DEFAULT_ROLES)
    assert permission_count == sum(len(role.permissions) for role in DEFAULT_ROLES.values())


async def test_restores_a_permission_that_went_missing(db_session: AsyncSession):
    await ensure_default_roles(db_session)
    owner_id = await db_session.scalar(select(Role.id).where(Role.name == "owner"))
    await db_session.execute(
        delete(RolePermission).where(RolePermission.role_id == owner_id, RolePermission.permission_name == "staff.manage")
    )
    await db_session.commit()

    await ensure_default_roles(db_session)

    assert "staff.manage" in (await _permissions_by_role(db_session))["owner"]


async def test_keeps_a_permission_an_admin_added_by_hand(db_session: AsyncSession):
    await ensure_default_roles(db_session)
    staff_id = await db_session.scalar(select(Role.id).where(Role.name == "staff"))
    db_session.add(RolePermission(role_id=staff_id, permission_name="user.read"))
    await db_session.commit()

    await ensure_default_roles(db_session)

    assert "user.read" in (await _permissions_by_role(db_session))["staff"]
