import uvicorn
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import products_router
# from app.api.review_consumer import handle_review_created # noqa
from app.core.config import settings
from app.core.rabbit_config import rabbit_broker, products_queue, products_exchange


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)

    await rabbit_broker.start()

    exchange = await rabbit_broker.declare_exchange(
        products_exchange
    )
    queue = await rabbit_broker.declare_queue(
        products_queue
    )

    await queue.bind(
        exchange=exchange,
        routing_key=settings.rabbitmq.PRODUCTS_RESERVE_ROUTING_KEY,
    )
    yield
    await rabbit_broker.close()


app = FastAPI(title="product-service", lifespan=lifespan)
app.include_router(products_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.cors.CORS_METHODS,
    allow_headers=settings.cors.CORS_HEADERS,
)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
