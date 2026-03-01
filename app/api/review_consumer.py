from sqlalchemy import update

from app.core.rabbit_config import rabbit_broker, products_reserved_queue
from app.core.database import async_session_factory
from app.models.products import ProductModel


# @rabbit_broker.subscriber(queue="reviews")
# async def handle_review_created(review_data: dict):
#     try:
#         async with async_session_factory() as session:
#             new_rating = review_data.get("new_rating")
#             product_id = review_data.get("product_id")
#
#             stmt = (
#                 update(ProductModel)
#                 .where(ProductModel.id == product_id)
#                 .values(
#                     rating=(ProductModel.rating * ProductModel.total_reviews + new_rating) /
#                     (ProductModel.total_reviews + 1),
#                     total_reviews=ProductModel.total_reviews + 1
#                 )
#             )
#             await session.execute(stmt)
#             await session.commit()
#
#     except Exception as e:
#         pass


# @rabbit_broker.subscriber(queue="orders")
# async def handle_order_created(order_data: dict):
#     try:
#         async with async_session_factory() as session:
#             stmt = (
#                 update(ProductModel)
#                 .where(
#                     ProductModel.id == order_data["product_id"],
#                     ProductModel.quantity >= order_data["quantity"]
#                 )
#                 .values(quantity=ProductModel.quantity - order_data["quantity"])
#                 .returning(ProductModel.id)
#             )
#
#             result = await session.execute(stmt)
#             await session.commit()
#             updated_product = result.scalar_one_or_none()
#
#             if not updated_product:
#                 await rabbit_broker.publish({
#                     "order_data": order_data,
#                     "status": "failed",
#                     "reason": "insufficient_stock"
#                 }, queue="order_errors")
#             else:
#                 await rabbit_broker.publish({
#                     "order_data": order_data,
#                     "status": "confirmed"
#                 }, queue="order_confirmations")
#
#     except Exception as e:
#         await rabbit_broker.publish({
#             "order_data": order_data,
#             "status": "failed",
#             "reason": "processing_error",
#             "error": str(e)
#         }, queue="order_errors")

#
# @rabbit_broker.subscriber(queue=products_queue)
# async def handle_reserve_products(message: dict):
#     payload = message.get("payload") or {}
#     items = payload.get("items") or []
#     if not items:
#         return
#
#     try:
#         async with async_session_factory() as session:
#             async with session.begin():
#                 for item in items:
#                     product_id = item.get("product_id")
#                     quantity = item.get("quantity")
#                     if product_id is None or quantity is None:
#                         raise ValueError("missing product_id or quantity")
#
#                     stmt = (
#                         update(ProductModel)
#                         .where(
#                             ProductModel.id == product_id,
#                             ProductModel.quantity >= quantity,
#                         )
#                         .values(quantity=ProductModel.quantity - quantity)
#                     )
#
#                     result = await session.execute(stmt)
#                     if result.rowcount == 0:
#                         raise ValueError("insufficient_stock")
#
#         await rabbit_broker.publish(
#             {
#                 "order_id": payload.get("order_id"),
#                 "status": "confirmed",
#             },
#             queue="order_confirmations",
#         )
#     except Exception as e:
#         await rabbit_broker.publish(
#             {
#                 "order_id": payload.get("order_id"),
#                 "status": "failed",
#                 "reason": str(e),
#             },
#             queue="order_errors",
#         )
