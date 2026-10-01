from typing import Annotated

from fastapi import Depends

from ...infrastructure.dependencies import AsyncSessionDep, CurrentPrincipalDep
from ..common.exceptions import ShopNotFoundError
from .models import Shop
from .service import ShopService


def get_shop_service() -> ShopService:
    return ShopService()


ShopServiceDep = Annotated[ShopService, Depends(get_shop_service)]


async def get_owner_shop(principal: CurrentPrincipalDep, db: AsyncSessionDep, service: ShopServiceDep) -> Shop:
    """The shop owned by the logged-in user. Every /owner/shop route works on this shop only.

    The shop is found from the session's user id, never from the URL or the request body,
    so there is no way to point an owner route at somebody else's shop.
    """
    shop = await service.get_owned_by(principal.user_id, db)
    if shop is None:
        raise ShopNotFoundError("You don't have a shop yet.")
    return shop


CurrentOwnerShopDep = Annotated[Shop, Depends(get_owner_shop)]
