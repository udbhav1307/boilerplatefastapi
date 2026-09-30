"""Every new account becomes a customer, however it signed up."""

import uuid

import pytest
from crudauth import HookContext
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.dependencies import load_permissions
from src.infrastructure.auth.setup import auth
from src.modules.role.defaults import DEFAULT_ROLES
from src.modules.role.models import Role
from src.modules.user.models import User

pytestmark = pytest.mark.asyncio

PASSWORD = "Password123!"


def _signup_payload() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:6]
    return {
        "name": f"Customer {suffix}",
        "username": f"cust{suffix}",
        "email": f"cust.{suffix}@example.com",
        "password": PASSWORD,
    }


async def test_password_signup_grants_the_customer_role(client: AsyncClient, db_session: AsyncSession):
    response = await client.post("/api/v1/users/", json=_signup_payload())

    assert response.status_code == 201
    user_id = response.json()["id"]
    assert await load_permissions(db_session, user_id) == DEFAULT_ROLES["customer"].permissions


async def test_a_new_customer_cannot_list_all_users(client: AsyncClient):
    payload = _signup_payload()
    assert (await client.post("/api/v1/users/", json=payload)).status_code == 201

    login = await client.post(
        "/api/v1/auth/login", data={"username": payload["username"], "password": PASSWORD}
    )
    assert login.status_code == 200

    response = await client.get("/api/v1/users/")

    assert response.status_code == 403


async def test_signup_saves_nothing_when_the_role_cannot_be_granted(client: AsyncClient, db_session: AsyncSession):
    await db_session.execute(delete(Role).where(Role.name == "customer"))
    await db_session.commit()
    payload = _signup_payload()

    response = await client.post("/api/v1/users/", json=payload)

    assert response.status_code == 404
    assert await db_session.scalar(select(User.id).where(User.username == payload["username"])) is None


async def test_oauth_registration_grants_the_customer_role(db_session: AsyncSession, test_user: dict):
    """crudauth calls the after-register hook for accounts it creates (e.g. Google sign-in)."""
    await auth.hooks.run_after_register(test_user, db=db_session, context=HookContext(transport="oauth"))

    assert await load_permissions(db_session, test_user["id"]) == DEFAULT_ROLES["customer"].permissions
