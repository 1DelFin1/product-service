import logging
from random import randint
from uuid import uuid4, UUID

from fastapi import HTTPException, status, UploadFile
from sqlalchemy import select, update, insert, delete, case, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.rabbit_config import rabbit_broker
from app.schemas import ProductUpdateSchema, ProductCreateSchema, CategoryCreateSchema
from app.services.minio_service import MinioService
from app.models.categories import CategoryModel
from app.models.reserved_products import ReservedProductModel
from app.models.products import ProductModel

logger = logging.getLogger(__name__)


class ProductService:
    @staticmethod
    def _normalize_photo_urls(photo_urls: dict | None) -> dict[str, str]:
        if not isinstance(photo_urls, dict):
            return {}

        ordered_urls: list[str] = []
        for value in photo_urls.values():
            if isinstance(value, str) and value.strip():
                ordered_urls.append(value.strip())

        return {str(index): url for index, url in enumerate(ordered_urls, start=1)}

    @staticmethod
    def _get_primary_photo_url(photo_urls: dict | None) -> str | None:
        if not isinstance(photo_urls, dict) or not photo_urls:
            return None

        def _sort_key(key: str) -> tuple[int, str]:
            return (int(key), key) if key.isdigit() else (10**9, key)

        for key in sorted(photo_urls.keys(), key=_sort_key):
            value = photo_urls.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return None

    @classmethod
    def serialize_product(cls, product: ProductModel) -> dict:
        normalized_photo_urls = cls._normalize_photo_urls(product.photo_urls)

        return {
            "id": product.id,
            "photo_urls": normalized_photo_urls,
            "image_url": cls._get_primary_photo_url(normalized_photo_urls),
            "name": product.name,
            "article": product.article,
            "description": product.description,
            "price": product.price,
            "price_discount": product.price_discount,
            "category_id": product.category_id,
            "rating": product.rating,
            "total_reviews": product.total_reviews,
            "quantity": product.quantity,
            "seller_id": product.seller_id,
            "is_active": product.is_active,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }

    @staticmethod
    def _resolve_image_extension(filename: str, content_type: str) -> str:
        if "." in filename:
            extension = filename.rsplit(".", 1)[-1].lower().strip()
            if extension:
                return extension

        content_type_to_extension = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
            "image/bmp": "bmp",
        }
        return content_type_to_extension.get(content_type, "bin")

    @classmethod
    async def create_product(
        cls, session: AsyncSession, product_data: ProductCreateSchema
    ):
        product = product_data.model_dump()
        product["photo_urls"] = cls._normalize_photo_urls(product_data.photo_urls)
        product["article"] = randint(100000, 999999)
        product["price_discount"] = product_data.price
        new_product = ProductModel(**product)
        session.add(new_product)
        await session.commit()
        return {"ok": True}

    @classmethod
    async def get_all_categories(cls, session: AsyncSession) -> list[CategoryModel]:
        stmt = select(CategoryModel).order_by(CategoryModel.name.asc())
        categories = list((await session.scalars(stmt)).all())
        return categories

    @classmethod
    async def create_category(
        cls, session: AsyncSession, category_data: CategoryCreateSchema
    ) -> CategoryModel:
        normalized_name = category_data.name.strip()
        if not normalized_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name cannot be empty",
            )

        existing_stmt = select(CategoryModel).where(
            func.lower(CategoryModel.name) == normalized_name.lower()
        )
        existing_category = await session.scalar(existing_stmt)
        if existing_category:
            return existing_category

        new_category = CategoryModel(name=normalized_name)
        session.add(new_category)
        await session.commit()
        await session.refresh(new_category)
        return new_category

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
                "seller_id": str(current_product.seller_id),
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
    async def upload_product_photos(
        cls,
        files: list[UploadFile],
        product_uuid: str,
    ) -> dict[str, str]:
        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one file must be provided",
            )

        try:
            product_folder_uuid = str(UUID(product_uuid))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product_uuid",
            )

        minio_service = MinioService()
        photo_urls: dict[str, str] = {}

        for position, file in enumerate(files, start=1):
            content_type = file.content_type or "application/octet-stream"
            if not content_type.startswith("image/"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only image files are allowed",
                )

            file_data = await file.read()
            if not file_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded image is empty",
                )

            file_extension = cls._resolve_image_extension(file.filename or "", content_type)
            file_key = f"products/{product_folder_uuid}/{position}_{uuid4()}.{file_extension}"
            photo_urls[str(position)] = minio_service.upload_file(
                file_data=file_data,
                filename=file_key,
                content_type=content_type,
            )

        return photo_urls

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
            if key == "photo_urls":
                setattr(product, key, cls._normalize_photo_urls(value))
                continue
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
