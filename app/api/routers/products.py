from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import SessionDep
from app.services import ProductService
from app.exceptions import PRODUCT_NOT_FOUND_EXCEPTION
from app.schemas import ProductCreateSchema, ProductUpdateSchema


products_router = APIRouter(prefix="/products", tags=["products"])


@products_router.get("")
async def get_all_products(session: SessionDep):
    products = await ProductService.get_all_products(session)
    return [ProductService.serialize_product(product) for product in products]


@products_router.post("")
async def create_product(session: SessionDep, user_data: ProductCreateSchema):
    product = await ProductService.create_product(session, user_data)
    return product


@products_router.post("/stock")
async def check_product_stock(session: SessionDep, order_data: dict):
    return await ProductService.check_product_stock(session, order_data)


@products_router.post("/photos/upload")
async def upload_product_photos(
    files: list[UploadFile] = File(...),
    product_uuid: str = Form(...),
):
    photo_urls = await ProductService.upload_product_photos(files, product_uuid)
    return {"photo_urls": photo_urls}


@products_router.get("/{product_id}")
async def get_product_by_id(session: SessionDep, product_id: int):
    product = await ProductService.get_product_by_id(session, product_id)
    if product is None:
        raise PRODUCT_NOT_FOUND_EXCEPTION
    return ProductService.serialize_product(product)


@products_router.patch("/{product_id}")
async def update_product(
    session: SessionDep, user_data: ProductUpdateSchema, product_id: int
):
    product = await ProductService.update_product(session, user_data, product_id)
    return product


@products_router.delete("/{product_id}")
async def delete_product(session: SessionDep, product_id: int):
    product = await ProductService.delete_product(session, product_id)
    return product


@products_router.get("/{product_id}/quantity")
async def get_product_quantity(session: SessionDep, product_id: int):
    quantity = await ProductService.get_product_quantity(session, product_id)
    return {"quantity": quantity}
