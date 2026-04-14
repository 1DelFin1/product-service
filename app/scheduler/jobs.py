import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, delete, select, update

from app.core.database import async_session_factory
from app.models.products import ProductModel
from app.models.reserved_products import ReservedProductModel


logger = logging.getLogger(__name__)

RESERVATION_TTL_MINUTES = 10


async def release_expired_reservations() -> None:
    expired_before = datetime.now(timezone.utc) - timedelta(minutes=RESERVATION_TTL_MINUTES)

    async with async_session_factory() as session:
        async with session.begin():
            expired_stmt = (
                select(ReservedProductModel)
                .where(ReservedProductModel.created_at <= expired_before)
                .with_for_update(skip_locked=True)
            )
            expired_rows = list((await session.scalars(expired_stmt)).all())

            if not expired_rows:
                return

            quantity_by_product_id: dict[int, int] = defaultdict(int)
            reserved_ids: list[int] = []

            for row in expired_rows:
                quantity_by_product_id[row.product_id] += row.quantity
                reserved_ids.append(row.id)

            increment_case = case(quantity_by_product_id, value=ProductModel.id, else_=0)
            restore_stmt = (
                update(ProductModel)
                .where(ProductModel.id.in_(tuple(quantity_by_product_id.keys())))
                .values({"quantity": ProductModel.quantity + increment_case})
            )
            await session.execute(restore_stmt)

            delete_stmt = delete(ReservedProductModel).where(
                ReservedProductModel.id.in_(tuple(reserved_ids))
            )
            await session.execute(delete_stmt)

    logger.info(
        "Released expired reservations: rows=%s, products=%s",
        len(expired_rows),
        len(quantity_by_product_id),
    )
