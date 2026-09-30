"""Role assignment shared by sign-up, OAuth registration and (later) staff management."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import RoleNotFoundError
from .models import Role, UserRole


async def assign_role(db: AsyncSession, user_id: int, role_name: str, *, commit: bool = True) -> None:
    """Give a user the named role; assigning a role the user already has does nothing.

    Pass ``commit=False`` to make the assignment part of the caller's transaction, so that
    e.g. a new account and its role are saved together or not at all.
    """
    role_id = await db.scalar(select(Role.id).where(Role.name == role_name))
    if role_id is None:
        raise RoleNotFoundError(f"Role '{role_name}' does not exist")

    now = datetime.now(UTC)
    await db.execute(
        insert(UserRole)
        .values(user_id=user_id, role_id=role_id, created_at=now, updated_at=now)
        .on_conflict_do_nothing(index_elements=["user_id", "role_id"])
    )

    if commit:
        await db.commit()
