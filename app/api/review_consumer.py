from sqlalchemy import update

from app.core.clients import BrokerMQ
from app.core.database import async_session_factory
from app.models.products import ProductModel


@BrokerMQ.subscriber(queue="reviews")
async def handle_review_created(review_data: dict):
    try:
        async with async_session_factory() as session:
            new_rating = review_data.get("new_rating")
            product_id = review_data.get("product_id")

            stmt = (
                update(ProductModel)
                .where(ProductModel.id == product_id)
                .values(
                    rating=(ProductModel.rating * ProductModel.total_reviews + new_rating) /
                    (ProductModel.total_reviews + 1),
                    total_reviews=ProductModel.total_reviews + 1
                )
            )
            await session.execute(stmt)
            await session.commit()

    except Exception as e:
        pass


@BrokerMQ.subscriber(queue="orders")
async def handle_order_created(order_data: dict):
    try:
        async with async_session_factory() as session:
            stmt = (
                update(ProductModel)
                .where(
                    ProductModel.id == order_data["product_id"],
                    ProductModel.quantity >= order_data["quantity"]
                )
                .values(quantity=ProductModel.quantity - order_data["quantity"])
                .returning(ProductModel.id)
            )

            result = await session.execute(stmt)
            await session.commit()
            updated_product = result.scalar_one_or_none()

            if not updated_product:
                await BrokerMQ.publish({
                    "order_data": order_data,
                    "status": "failed",
                    "reason": "insufficient_stock"
                }, queue="order_errors")
            else:
                await BrokerMQ.publish({
                    "order_data": order_data,
                    "status": "confirmed"
                }, queue="order_confirmations")

    except Exception as e:
        await BrokerMQ.publish({
            "order_data": order_data,
            "status": "failed",
            "reason": "processing_error",
            "error": str(e)
        }, queue="order_errors")
