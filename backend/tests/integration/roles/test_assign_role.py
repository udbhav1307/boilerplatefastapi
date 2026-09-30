"""assign_role() gives a user a role by name, once."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.dependencies import load_permissions
from src.modules.common.exceptions import RoleNotFoundError
from src.modules.role.defaults import DEFAULT_ROLES
from src.modules.role.models import UserRole
from src.modules.role.service import assign_role

pytestmark = pytest.mark.asyncio


async def test_assigning_a_role_grants_its_permissions(db_session: AsyncSession, test_user: dict):
    await assign_role(db_session, test_user["id"], "customer")

    assert await load_permissions(db_session, test_user["id"]) == DEFAULT_ROLES["customer"].permissions


async def test_assigning_the_same_role_twice_keeps_one_row(db_session: AsyncSession, test_user: dict):
    await assign_role(db_session, test_user["id"], "customer")
    await assign_role(db_session, test_user["id"], "customer")

    count = await db_session.scalar(
        select(func.count()).select_from(UserRole).where(UserRole.user_id == test_user["id"])
    )
    assert count == 1


async def test_an_unknown_role_is_an_error(db_session: AsyncSession, test_user: dict):
    with pytest.raises(RoleNotFoundError):
        await assign_role(db_session, test_user["id"], "janitor")


async def test_without_commit_the_caller_decides(db_session: AsyncSession, test_user: dict):
    await assign_role(db_session, test_user["id"], "customer", commit=False)
    await db_session.rollback()

    assert await load_permissions(db_session, test_user["id"]) == frozenset()
