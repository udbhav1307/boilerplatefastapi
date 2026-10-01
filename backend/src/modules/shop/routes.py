"""Shop endpoints: public pages anyone can read, and the owner's own shop."""

from typing import Any

from fastapi import APIRouter, Response

from ...infrastructure.auth.dependencies import require_permissions
from ...infrastructure.dependencies import AsyncSessionDep, CurrentPrincipalDep
from .dependencies import CurrentOwnerShopDep, ShopServiceDep
from .permissions import ShopPermission
from .schemas import ClosureCreate, ClosureRead, DayHours, ShopCreate, ShopRead, ShopUpdate, WeeklyHoursSet

# --- public: mounted at /shops ----------------------------------------------------------

public_router = APIRouter(tags=["Shops"])


@public_router.get("/{slug}", response_model=ShopRead, summary="A shop's public details")
async def get_shop(slug: str, db: AsyncSessionDep, service: ShopServiceDep) -> dict[str, Any]:
    return await service.get_by_slug(slug, db)


@public_router.get("/{slug}/hours", response_model=list[DayHours], summary="A shop's weekly opening hours")
async def get_shop_hours(slug: str, db: AsyncSessionDep, service: ShopServiceDep) -> list[dict[str, Any]]:
    shop = await service.get_by_slug(slug, db)
    return await service.get_hours(shop["id"], db)


# --- owner: mounted at /owner -----------------------------------------------------------

owner_router = APIRouter(tags=["Owner: shop"])
manage_shop = [require_permissions(ShopPermission.MANAGE)]


@owner_router.post(
    "/shop",
    status_code=201,
    response_model=ShopRead,
    summary="Open your shop",
    description="Any logged-in user can open one shop and becomes its owner.",
    responses={401: {"description": "Not logged in"}, 409: {"description": "You already have a shop, or the slug is taken"}},
)
async def open_shop(
    data: ShopCreate, principal: CurrentPrincipalDep, db: AsyncSessionDep, service: ShopServiceDep
) -> dict[str, Any]:
    return await service.create(principal.user_id, data, db)


@owner_router.get("/shop", response_model=ShopRead, dependencies=manage_shop, summary="Your shop")
async def get_my_shop(shop: CurrentOwnerShopDep) -> ShopRead:
    return ShopRead.model_validate(shop)


@owner_router.patch("/shop", response_model=ShopRead, dependencies=manage_shop, summary="Edit your shop")
async def update_my_shop(
    data: ShopUpdate, shop: CurrentOwnerShopDep, db: AsyncSessionDep, service: ShopServiceDep
) -> dict[str, Any]:
    return await service.update(shop, data, db)


@owner_router.get("/shop/hours", response_model=list[DayHours], dependencies=manage_shop, summary="Your weekly hours")
async def get_my_hours(shop: CurrentOwnerShopDep, db: AsyncSessionDep, service: ShopServiceDep) -> list[dict[str, Any]]:
    return await service.get_hours(shop.id, db)


@owner_router.put(
    "/shop/hours",
    response_model=list[DayHours],
    dependencies=manage_shop,
    summary="Set your weekly hours",
    description="Replaces the whole week. Weekdays you leave out are closed.",
)
async def set_my_hours(
    week: WeeklyHoursSet, shop: CurrentOwnerShopDep, db: AsyncSessionDep, service: ShopServiceDep
) -> list[dict[str, Any]]:
    return await service.set_hours(shop, week, db)


@owner_router.get(
    "/shop/closures", response_model=list[ClosureRead], dependencies=manage_shop, summary="Your upcoming closures"
)
async def list_my_closures(
    shop: CurrentOwnerShopDep, db: AsyncSessionDep, service: ShopServiceDep
) -> list[dict[str, Any]]:
    return await service.list_closures(shop, db)


@owner_router.post(
    "/shop/closures",
    status_code=201,
    response_model=ClosureRead,
    dependencies=manage_shop,
    summary="Close your shop on a date",
)
async def add_my_closure(
    data: ClosureCreate, shop: CurrentOwnerShopDep, db: AsyncSessionDep, service: ShopServiceDep
) -> dict[str, Any]:
    return await service.add_closure(shop, data, db)


@owner_router.delete(
    "/shop/closures/{closure_id}", status_code=204, dependencies=manage_shop, summary="Remove a closure"
)
async def remove_my_closure(
    closure_id: int, shop: CurrentOwnerShopDep, db: AsyncSessionDep, service: ShopServiceDep
) -> Response:
    await service.remove_closure(shop, closure_id, db)
    return Response(status_code=204)
