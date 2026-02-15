import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import ProductUpdateSchema, ProductCreateSchema, OrderBaseSchema
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
