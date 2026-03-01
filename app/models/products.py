from uuid import UUID

from sqlalchemy import Integer, String, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.core.database import Base
from app.models.mixins import TimestampMixin


class ProductModel(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255))
    price: Mapped[float] = mapped_column(Float)
    rating: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    total_reviews: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    quantity: Mapped[int] = mapped_column(Integer)
    seller_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
