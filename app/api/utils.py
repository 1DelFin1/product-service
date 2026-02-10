from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.products import ProductModel


class RatingManager:
    @staticmethod
    async def update_product_rating(
        session: AsyncSession,
        product_id: str,
        rating: int,
    ) -> None:
        stmt = select(ProductModel).where(ProductModel.id == product_id)
        product = await session.scalar(stmt)

        if not product:
            print(f"Product {product_id} not found")
            return

        new_total = product.total_reviews + 1
        new_sum = product.total_reviews + rating

        new_avg = new_sum / new_total if new_total > 0 else 0.0

        update_stmt = (
            update(ProductModel)
            .where(ProductModel.id == product_id)
            .values(
                total_reviews=new_total,
                sum_ratings=new_sum,
                average_rating=new_avg
            )
        )
        await session.execute(update_stmt)
