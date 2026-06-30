from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.security import decode_token
from db.models import User
from db.session import get_async_session

# 从 Authorization: Bearer <token> 里提取 token。
# tokenUrl 主要用于 OpenAPI/Swagger 文档展示登录地址。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def credentials_exception() -> HTTPException:
    """统一返回 401，并带上 Bearer 认证头。"""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """FastAPI 依赖：根据 access token 获取当前用户。

    路由里使用 Depends(get_current_user) 后，会自动完成：
    1. 从请求头提取 Bearer token
    2. 校验 JWT 签名、过期时间和 token 类型
    3. 从数据库查用户并确认账号可用
    """

    try:
        payload = decode_token(token)
        # 受保护接口只接受 access token，不接受 refresh token。
        if payload.get("type") != "access":
            raise credentials_exception()
        # sub 是 create_access_token 写入的用户 ID。
        user_id = UUID(str(payload.get("sub")))
    except (JWTError, TypeError, ValueError):
        raise credentials_exception() from None

    # JWT 有效还不够，还要确认用户仍存在且没有被禁用。
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception()
    return user
