from uuid import UUID
from pydantic import BaseModel, Field


class ProductBaseSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=255)
    price: float
    quantity: int
    seller_id: UUID
    category_id: int


class ProductCreateSchema(ProductBaseSchema):
    pass


class ProductUpdateSchema(BaseModel):
    name: str | None = Field(max_length=255)
    description: str | None = Field(max_length=255)
    price: float | None


class OrderBaseSchema(BaseModel):
    product_id: int
    quantity: int


class CategoryBaseSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CategoryCreateSchema(CategoryBaseSchema):
    pass
