import logging
from uuid import UUID

from sqlalchemy import select, update, insert, delete, case, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.rabbit_config import rabbit_broker
from app.schemas import ProductUpdateSchema, ProductCreateSchema
from app.models.reserved_products import ReservedProductModel
from app.models.products import ProductModel

logger = logging.getLogger(__name__)


class ProductService:
    @classmethod
    async def create_product(
        cls, session: AsyncSession, product_data: ProductCreateSchema
    ):
        product = product_data.model_dump()
        new_product = ProductModel(**product)
        session.add(new_product)
        await session.commit()
        return {"ok": True}

    @classmethod
    async def check_product_stock(cls, session: AsyncSession, order_data: dict) -> dict:
        res = {}
        res["total_amount"] = 0

        for order_item in order_data.get("items", []):
            current_product = await cls.get_product_by_id(
                session, order_item.get("product_id")
            )
            if current_product.quantity < order_item.get("quantity"):
                return {"ok": False}

            data = {
                "product_id": current_product.id,
                "quantity": order_item.get("quantity"),
                "price": current_product.price,
            }

            if not res.get("products", []):
                res["products"] = [data]
            else:
                res["products"].append(data)

            res["total_amount"] += order_item.get("quantity") * current_product.price

        res["ok"] = True
        return res

    @classmethod
    async def reserve_product(cls, order_data: dict):
        async with async_session_factory() as session:
            items = order_data.get("items", [])
            if items:
                quantity_by_product_id = {}
                for item in items:
                    product_id = item.get("product_id")
                    quantity_by_product_id[product_id] = quantity_by_product_id.get(
                        product_id, 0
                    ) + item.get("quantity")

                decrement_case = case(
                    quantity_by_product_id,
                    value=ProductModel.id,
                    else_=0,
                )
                update_stmt = (
                    update(ProductModel)
                    .where(ProductModel.id.in_(tuple(quantity_by_product_id.keys())))
                    .values(
                        {
                            "quantity": func.greatest(
                                ProductModel.quantity - decrement_case,
                                0,
                            )
                        }
                    )
                )
                await session.execute(update_stmt)

                reserved_stmt = insert(ReservedProductModel).values(
                    [
                        {
                            "product_id": item.get("product_id"),
                            "quantity": item.get("quantity"),
                            "order_id": order_data.get("order_id"),
                        }
                        for item in items
                    ]
                )
                await session.execute(reserved_stmt)

            await session.commit()

            payload = {"ok": True, "order_id": order_data.get("order_id")}
            await rabbit_broker.publish(
                payload, routing_key=settings.rabbitmq.ORDERS_RESERVED_ROUTING_KEY
            )

    @classmethod
    async def handle_paid_products(cls, order: dict):
        # TODO: сделать проверку статуса заказа
        async with async_session_factory() as session:
            stmt = delete(ReservedProductModel).where(
                ReservedProductModel.order_id == order.get("order_id")
            )
            await session.execute(stmt)
            await session.commit()

    @classmethod
    async def get_product_price_by_id(cls, session: AsyncSession, product_id: int):
        return await session.get(ProductModel.price, product_id)

    @classmethod
    async def get_product_by_id(
        cls, session: AsyncSession, product_id: int
    ) -> ProductModel | None:
        stmt = select(ProductModel).where(ProductModel.id == product_id)
        product = await session.scalar(stmt)
        if not product:
            return None

        return product

    @classmethod
    async def get_all_products(cls, session: AsyncSession) -> list[ProductModel]:
        stmt = select(ProductModel)
        products = list((await session.scalars(stmt)).all())
        return products

    @classmethod
    async def get_product_quantity(
        cls, session: AsyncSession, product_id: int
    ) -> int | None:
        stmt = select(ProductModel.quantity).where(ProductModel.id == product_id)
        return await session.scalar(stmt)

    @classmethod
    async def update_product(
        cls, session: AsyncSession, product_data: ProductUpdateSchema, product_id: int
    ):
        product = await cls.get_product_by_id(session, product_id)

        new_product = product_data.model_dump(exclude_unset=True)
        for key, value in new_product.items():
            if new_product[key] != "":
                setattr(product, key, value)

        session.add(product)
        await session.commit()
        await session.refresh(product)
        return {"ok": True}

    @classmethod
    async def delete_product(cls, session: AsyncSession, product_id: int):
        product = await cls.get_product_by_id(session, product_id)
        await session.delete(product)
        await session.commit()
        return {"ok": True}
