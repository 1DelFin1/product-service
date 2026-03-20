from typing import Annotated, AsyncGenerator, Any

import jwt
from jwt.exceptions import InvalidTokenError

from fastapi import Depends, HTTPException, Request, status

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory


async def get_session() -> AsyncGenerator:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_active_auth_admin(request: Request) -> dict[str, Any]:
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        payload = jwt.decode(
            token,
            settings.jwt.JWT_SECRET_KEY,
            algorithms=[settings.jwt.JWT_ALGORITHM],
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    if payload.get("account_type") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return payload


AdminDep = Annotated[dict[str, Any], Depends(get_current_active_auth_admin)]
