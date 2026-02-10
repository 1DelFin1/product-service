from faststream.rabbit import RabbitBroker

from app.core.config import settings


BrokerMQ = RabbitBroker(settings.RABBITMQ_URL)
