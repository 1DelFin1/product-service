from faststream.rabbit import RabbitRouter

from app.core.rabbit_config import products_queue
from app.services import ProductService

products_router = RabbitRouter()


@products_router.subscriber(products_queue)
async def reserve_products(data: dict):
    await ProductService.reserve_product(data)
