from faststream import FastStream

from app.core.config import settings
from app.core.rabbit_config import (
    rabbit_broker,
    products_exchange,
    products_reserved_queue,
)
from app.fs.routers import products_router

app = FastStream(rabbit_broker)

rabbit_broker.include_router(products_router)


@app.after_startup
async def after_startup():
    exchange = await rabbit_broker.declare_exchange(products_exchange)
    queue = await rabbit_broker.declare_queue(products_reserved_queue)

    await queue.bind(
        exchange=exchange,
        routing_key=settings.rabbitmq.PRODUCTS_RESERVE_ROUTING_KEY,
    )
