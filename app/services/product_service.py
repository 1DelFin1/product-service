import logging
from random import randint
from uuid import uuid4, UUID

import httpx
from fastapi import HTTPException, status, UploadFile
from sqlalchemy import case, delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.rabbit_config import rabbit_broker
from app.schemas import (
    ProductUpdateSchema,
    ProductCreateSchema,
    CategoryCreateSchema,
    CategoryUpdateSchema,
)
from app.services.minio_service import MinioService
from app.models.categories import CategoryModel
from app.models.reserved_products import ReservedProductModel
from app.models.products import ProductModel, ProductStatus

logger = logging.getLogger(__name__)


class ProductService:
    @staticmethod
    def _extract_review_product_ids(event: dict) -> list[int]:
        if not isinstance(event, dict):
            return []

        product_ids: set[int] = set()

        raw_product_ids = event.get("product_ids")
        if isinstance(raw_product_ids, list):
            for value in raw_product_ids:
                if isinstance(value, int) and value > 0:
                    product_ids.add(value)
                elif isinstance(value, str) and value.isdigit():
                    product_ids.add(int(value))

        raw_product_id = event.get("product_id")
        if isinstance(raw_product_id, int) and raw_product_id > 0:
            product_ids.add(raw_product_id)
        elif isinstance(raw_product_id, str) and raw_product_id.isdigit():
            product_ids.add(int(raw_product_id))

        return sorted(product_ids)

    @staticmethod
    def _extract_reviews(payload: object) -> list[dict]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            for key in ("reviews", "items", "results", "data", "content"):
                maybe_list = payload.get(key)
                if isinstance(maybe_list, list):
                    return [item for item in maybe_list if isinstance(item, dict)]

        return []

    @classmethod
    async def _fetch_reviews_stats(cls, product_id: int) -> tuple[int, float] | None:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{settings.urls.NGINX_URL}/reviews/product/{product_id}",
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
                response.raise_for_status()
                reviews = cls._extract_reviews(response.json())
            except Exception:
                logger.exception(
                    "Failed to load reviews for rating recalculation: product_id=%s",
                    product_id,
                )
                return None

        ratings: list[float] = []
        for review in reviews:
            rating = review.get("rating")
            if isinstance(rating, (int, float)):
                ratings.append(float(rating))
            elif isinstance(rating, str):
                try:
                    ratings.append(float(rating))
                except ValueError:
                    continue

        if not ratings:
            return 0, 0.0

        total_reviews = len(ratings)
        average_rating = sum(ratings) / total_reviews
        return total_reviews, average_rating

    @classmethod
    async def handle_review_changed(cls, event: dict) -> None:
        product_ids = cls._extract_review_product_ids(event)
        if not product_ids:
            return

        async with async_session_factory() as session:
            for product_id in product_ids:
                stats = await cls._fetch_reviews_stats(product_id)
                if stats is None:
                    continue

                total_reviews, average_rating = stats
                stmt = (
                    update(ProductModel)
                    .where(ProductModel.id == product_id)
                    .values(
                        {
                            "rating": average_rating,
                            "total_reviews": total_reviews,
                        }
                    )
                )
                await session.execute(stmt)

            await session.commit()

    @staticmethod
    def _normalize_status(
        raw_status: ProductStatus | str | None,
    ) -> ProductStatus | None:
        if isinstance(raw_status, ProductStatus):
            return raw_status

        if isinstance(raw_status, str):
            normalized_status = raw_status.strip().lower()
            if normalized_status == ProductStatus.PENDING.value:
                return ProductStatus.PENDING
            if normalized_status == ProductStatus.APPROVED.value:
                return ProductStatus.APPROVED
            if normalized_status == ProductStatus.REJECTED.value:
                return ProductStatus.REJECTED

        return None

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
        normalized_status = cls._normalize_status(product.status)
        status_value = (
            normalized_status.value if normalized_status else ProductStatus.APPROVED.value
        )

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
            "status": status_value,
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
        product["status"] = ProductStatus.PENDING
        product["is_active"] = False
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
    async def update_category(
        cls,
        session: AsyncSession,
        category_id: int,
        category_data: CategoryUpdateSchema,
    ) -> CategoryModel:
        category = await session.get(CategoryModel, category_id)
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )

        normalized_name = category_data.name.strip()
        if not normalized_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name cannot be empty",
            )

        existing_stmt = select(CategoryModel).where(
            func.lower(CategoryModel.name) == normalized_name.lower(),
            CategoryModel.id != category_id,
        )
        existing_category = await session.scalar(existing_stmt)
        if existing_category is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category with this name already exists",
            )

        category.name = normalized_name
        session.add(category)
        await session.commit()
        await session.refresh(category)
        return category

    @classmethod
    async def delete_category(cls, session: AsyncSession, category_id: int) -> dict[str, bool]:
        category = await session.get(CategoryModel, category_id)
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )

        products_count_stmt = (
            select(func.count(ProductModel.id))
            .where(ProductModel.category_id == category_id)
        )
        products_count = await session.scalar(products_count_stmt)
        if (products_count or 0) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete category linked to products",
            )

        await session.delete(category)
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
            if not current_product:
                return {"ok": False}

            if current_product.is_active is False:
                return {"ok": False}

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
                    .where(
                        ProductModel.id.in_(tuple(quantity_by_product_id.keys())),
                        ProductModel.quantity >= decrement_case,
                    )
                    .values({"quantity": ProductModel.quantity - decrement_case})
                )
                update_result = await session.execute(update_stmt)

                if (update_result.rowcount or 0) != len(quantity_by_product_id):
                    await session.rollback()
                    logger.warning(
                        "Reserve rejected due to insufficient quantity: order_id=%s",
                        order_data.get("order_id"),
                    )
                    return

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
        cls, session: AsyncSession, product_id: int, include_unapproved: bool = False
    ) -> ProductModel | None:
        stmt = select(ProductModel).where(ProductModel.id == product_id)
        product = await session.scalar(stmt)
        if not product:
            return None

        if include_unapproved:
            return product

        normalized_status = cls._normalize_status(product.status)
        if normalized_status in (None, ProductStatus.APPROVED):
            return product

        return None

    @classmethod
    async def get_pending_products(cls, session: AsyncSession) -> list[ProductModel]:
        stmt = (
            select(ProductModel)
            .where(ProductModel.status == ProductStatus.PENDING)
            .order_by(ProductModel.created_at.desc())
        )
        products = list((await session.scalars(stmt)).all())
        return products

    @classmethod
    async def moderate_product(
        cls,
        session: AsyncSession,
        product_id: int,
        next_status: ProductStatus,
    ) -> ProductModel:
        product = await cls.get_product_by_id(session, product_id, include_unapproved=True)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        if cls._normalize_status(product.status) != ProductStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only pending products can be moderated",
            )

        product.status = next_status
        product.is_active = next_status == ProductStatus.APPROVED
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product

    @classmethod
    async def get_all_products(
        cls,
        session: AsyncSession,
        seller_id: UUID | None = None,
    ) -> list[ProductModel]:
        stmt = select(ProductModel)

        if seller_id is not None:
            stmt = stmt.where(ProductModel.seller_id == seller_id)
        else:
            stmt = stmt.where(
                or_(
                    ProductModel.status == ProductStatus.APPROVED,
                    ProductModel.status.is_(None),
                )
            )

        stmt = stmt.order_by(ProductModel.created_at.desc())
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
