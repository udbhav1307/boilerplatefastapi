"""The shop API over HTTP: public pages, the owner's own shop, and isolation between owners."""

import pytest
from httpx import AsyncClient

from src.infrastructure.auth.dependencies import get_current_principal, get_current_user
from src.interfaces.main import app
from tests.conftest import _principal_for

pytestmark = pytest.mark.asyncio

OWNER = "/api/v1/owner/shop"
PUBLIC = "/api/v1/shops"

WEEK = {
    "days": [
        {"weekday": 0, "open_time": "09:00", "close_time": "20:00"},
        {"weekday": 5, "open_time": "08:00", "close_time": "22:00"},
    ]
}


def act_as(user: dict | None) -> None:
    """Make the following requests come from this user (None = logged out)."""
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_principal, None)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_principal] = lambda: _principal_for(user)


async def _open_shop(client: AsyncClient, user: dict, name: str = "Fade Factory") -> dict:
    act_as(user)
    response = await client.post(OWNER, json={"name": name, "timezone": "Asia/Kolkata"})
    assert response.status_code == 201, response.text
    return response.json()


# --- opening a shop -------------------------------------------------------------------


async def test_a_logged_in_user_opens_a_shop(client: AsyncClient, test_user: dict):
    shop = await _open_shop(client, test_user)

    assert shop["slug"] == "fade-factory"
    assert "owner_user_id" not in shop
    assert (await client.get(OWNER)).json()["id"] == shop["id"]


async def test_opening_a_shop_needs_a_login(client: AsyncClient):
    act_as(None)

    response = await client.post(OWNER, json={"name": "Fade Factory", "timezone": "Asia/Kolkata"})

    assert response.status_code == 401


async def test_a_second_shop_is_a_conflict_with_a_readable_message(client: AsyncClient, test_user: dict):
    await _open_shop(client, test_user)

    response = await client.post(OWNER, json={"name": "Second", "timezone": "Asia/Kolkata"})

    assert response.status_code == 409
    assert "already have a shop" in response.json()["detail"]


async def test_bad_input_is_a_422(client: AsyncClient, test_user: dict):
    act_as(test_user)

    response = await client.post(OWNER, json={"name": "Fade Factory", "timezone": "Mars/Base"})

    assert response.status_code == 422


# --- public pages -----------------------------------------------------------------------


async def test_anyone_can_see_a_shop_and_its_hours(client: AsyncClient, test_user: dict):
    await _open_shop(client, test_user)
    assert (await client.put(f"{OWNER}/hours", json=WEEK)).status_code == 200

    act_as(None)
    shop = await client.get(f"{PUBLIC}/fade-factory")
    hours = await client.get(f"{PUBLIC}/fade-factory/hours")

    assert shop.status_code == 200
    assert shop.json()["name"] == "Fade Factory"
    assert [day["weekday"] for day in hours.json()] == [0, 5]


async def test_an_unknown_shop_is_a_404(client: AsyncClient):
    act_as(None)

    assert (await client.get(f"{PUBLIC}/no-such-shop")).status_code == 404


# --- the owner's own shop ------------------------------------------------------------


async def test_the_owner_edits_their_shop(client: AsyncClient, test_user: dict):
    await _open_shop(client, test_user)

    response = await client.patch(OWNER, json={"phone": "+91 98765 43210", "slot_step_minutes": 30})

    assert response.status_code == 200
    assert response.json()["slot_step_minutes"] == 30


async def test_the_owner_manages_closures(client: AsyncClient, test_user: dict):
    await _open_shop(client, test_user)

    created = await client.post(f"{OWNER}/closures", json={"closed_on": "2099-12-25", "reason": "Christmas"})
    listed = await client.get(f"{OWNER}/closures")
    removed = await client.delete(f"{OWNER}/closures/{created.json()['id']}")

    assert created.status_code == 201
    assert [c["closed_on"] for c in listed.json()] == ["2099-12-25"]
    assert removed.status_code == 204
    assert (await client.get(f"{OWNER}/closures")).json() == []


async def test_a_past_closure_is_a_422_with_a_readable_message(client: AsyncClient, test_user: dict):
    await _open_shop(client, test_user)

    response = await client.post(f"{OWNER}/closures", json={"closed_on": "2020-01-01"})

    assert response.status_code == 422
    assert "past" in response.json()["detail"]


# --- who may do what -----------------------------------------------------------------


async def test_a_customer_cannot_use_owner_routes(client: AsyncClient, test_user: dict):
    """A plain sign-up is a customer: no shop.manage permission."""
    signup = await client.post(
        "/api/v1/users/",
        json={"name": "Ravi", "username": "ravicust", "email": "ravi.cust@example.com", "password": "Password123!"},
    )
    customer = {**signup.json(), "is_superuser": False}
    act_as(customer)

    for method, path in [("GET", OWNER), ("PATCH", OWNER), ("PUT", f"{OWNER}/hours"), ("GET", f"{OWNER}/closures")]:
        response = await client.request(method, path, json={} if method != "GET" else None)
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}"


async def test_owners_only_ever_see_and_change_their_own_shop(
    client: AsyncClient, test_user: dict, test_user_2: dict
):
    mine = await _open_shop(client, test_user, "Fade Factory")
    my_closure = (await client.post(f"{OWNER}/closures", json={"closed_on": "2099-12-25"})).json()
    theirs = await _open_shop(client, test_user_2, "Sharp Edge")

    # Logged in as the second owner, every /owner/shop route resolves to *their* shop...
    assert (await client.get(OWNER)).json()["id"] == theirs["id"]
    await client.patch(OWNER, json={"name": "Renamed"})
    # ...and the first owner's closure id is simply not found.
    assert (await client.delete(f"{OWNER}/closures/{my_closure['id']}")).status_code == 404

    act_as(test_user)
    assert (await client.get(OWNER)).json()["name"] == "Fade Factory" == mine["name"]
    assert [c["id"] for c in (await client.get(f"{OWNER}/closures")).json()] == [my_closure["id"]]
