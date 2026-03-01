from faststream.rabbit import RabbitRouter

from app.core.rabbit_config import products_reserved_queue, products_delete_queue
from app.services import ProductService

products_router = RabbitRouter()


@products_router.subscriber(products_reserved_queue)
async def reserve_products(products: dict):
    await ProductService.reserve_product(products)


@products_router.subscriber(products_delete_queue)
async def delete_products(order: dict):
    await ProductService.handle_paid_products(order)
