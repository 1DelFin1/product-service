from fastapi import APIRouter

from app.api.deps import SessionDep, AdminDep
from app.schemas import CategoryCreateSchema, CategoryUpdateSchema
from app.services import ProductService


categories_router = APIRouter(prefix="/categories", tags=["categories"])


@categories_router.get("")
async def get_all_categories(session: SessionDep):
    categories = await ProductService.get_all_categories(session)
    return categories


@categories_router.post("")
async def create_category(session: SessionDep, category_data: CategoryCreateSchema, _: AdminDep):
    category = await ProductService.create_category(session, category_data)
    return category


@categories_router.patch("/{category_id}")
async def update_category(
    session: SessionDep,
    category_id: int,
    category_data: CategoryUpdateSchema,
    _: AdminDep,
):
    category = await ProductService.update_category(
        session=session,
        category_id=category_id,
        category_data=category_data,
    )
    return category


@categories_router.delete("/{category_id}")
async def delete_category(session: SessionDep, category_id: int, _: AdminDep):
    return await ProductService.delete_category(session=session, category_id=category_id)
