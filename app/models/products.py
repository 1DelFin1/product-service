from uuid import UUID

from sqlalchemy import Integer, String, Float, ForeignKey, JSON, text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.core.database import Base
from app.models.mixins import TimestampMixin


class ProductModel(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_urls: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'::json")
    )
    name: Mapped[str] = mapped_column(String(255))
    article: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255))
    price: Mapped[float] = mapped_column(Float)
    price_discount: Mapped[float] = mapped_column(Float)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    rating: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    total_reviews: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    quantity: Mapped[int] = mapped_column(Integer)
    seller_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=True)
