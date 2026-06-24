from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.security import decode_token
from db.models import User
from db.session import get_async_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception()
        user_id = UUID(str(payload.get("sub")))
    except (JWTError, TypeError, ValueError):
        raise credentials_exception() from None

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception()
    return user
