from uuid import UUID
from pydantic import BaseModel, Field


class ProductBaseSchema(BaseModel):
    photo_urls: dict[str, str] | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=255)
    price: float
    quantity: int
    seller_id: UUID
    category_id: int
    is_active: bool = True


class ProductCreateSchema(ProductBaseSchema):
    pass


class ProductUpdateSchema(BaseModel):
    photo_urls: dict[str, str] | None = None
    name: str | None = None
    description: str | None = None
    price: float | None = None
    quantity: int | None = None
    category_id: int | None = None
    is_active: bool | None = None


class OrderBaseSchema(BaseModel):
    product_id: int
    quantity: int


class CategoryBaseSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CategoryCreateSchema(CategoryBaseSchema):
    pass


class CategoryUpdateSchema(CategoryBaseSchema):
    pass
