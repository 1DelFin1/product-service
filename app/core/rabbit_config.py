from faststream.rabbit import RabbitExchange, RabbitQueue, ExchangeType, RabbitBroker

from app.core.config import settings


rabbit_broker = RabbitBroker(settings.rabbitmq.RABBITMQ_URL)

products_exchange = RabbitExchange(
    name=settings.rabbitmq.PRODUCTS_ROUTING_KEY,
    type=ExchangeType.DIRECT,
    durable=True,
)

products_reserved_queue = RabbitQueue(
    name=settings.rabbitmq.PRODUCTS_RESERVE_ROUTING_KEY,
    durable=True,
)

products_delete_queue = RabbitQueue(
    name=settings.rabbitmq.PRODUCTS_DELETE_ROUTING_KEY,
    durable=True,
)
