from fastapi import APIRouter

from app.api.deps import SessionDep
from app.schemas import CategoryCreateSchema
from app.services import ProductService


categories_router = APIRouter(prefix="/categories", tags=["categories"])


@categories_router.get("")
async def get_all_categories(session: SessionDep):
    categories = await ProductService.get_all_categories(session)
    return categories


@categories_router.post("")
async def create_category(session: SessionDep, category_data: CategoryCreateSchema):
    category = await ProductService.create_category(session, category_data)
    return category
