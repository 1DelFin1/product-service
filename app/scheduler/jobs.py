from datetime import datetime, timedelta, timezone


from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.reserved_products import ReservedProductModel


async def check_reserved_products():
    time = datetime.now(timezone.utc) + timedelta(hours=3) - timedelta(minutes=15)

    async with async_session_factory() as session:
        stmt = (
            select(ReservedProductModel)
            .where(ReservedProductModel.created_at <= time)
            .order_by(ReservedProductModel.order_id)
        )

        reserved_products = (await session.scalars(stmt)).all()
