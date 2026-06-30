from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import credentials_exception, get_current_user
from api.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserRead,
)
from api.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    ensure_aware_utc,
    hash_password,
    hash_token,
    utc_now,
    verify_password,
)
from api.settings import settings
from db.models import RefreshToken, User
from db.session import get_async_session

# 所有认证接口都挂在 /auth 下，例如 /auth/login、/auth/refresh。
router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_user_by_login(session: AsyncSession, login: str) -> User | None:
    """根据登录标识查用户。

    当前允许用户用 username 或 email 登录；email 查询统一转小写，和注册时的规范化保持一致。
    """

    value = login.strip()
    stmt = select(User).where(or_(User.username == value, User.email == value.lower()))
    return await session.scalar(stmt)


async def _issue_token_pair(session: AsyncSession, user: User) -> TokenResponse:
    """签发一组 access token + refresh token。

    access token 是短期令牌，不入库；refresh token 是长期令牌，需要把哈希和状态写入数据库，
    后续刷新、退出登录、撤销 token 都依赖 refresh_tokens 表里的记录。
    """

    # access token 只返回给前端，用于访问 /auth/me 这类受保护接口。
    access_token, access_expires_at = create_access_token(user.id, user.username)

    # refresh token 返回给前端用于续签；jti 是这个 refresh token 的唯一 ID。
    refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(user.id, user.username)

    # 数据库只保存 refresh token 的 hash，不保存明文 token。
    # 这样即使数据库泄露，攻击者也不能直接拿 refresh token 去续签。
    session.add(
        RefreshToken(
            user_id=user.id,
            jti=refresh_jti,
            token_hash=hash_token(refresh_token),
            expires_at=refresh_expires_at,
        )
    )
    await session.commit()

    now = utc_now()
    return TokenResponse(
        # 前端拿 access_token 放进 Authorization: Bearer <token>。
        access_token=access_token,
        # 前端保存 refresh_token，在 access token 过期后调用 /auth/refresh 换新 token。
        refresh_token=refresh_token,
        # 剩余秒数，方便前端决定什么时候主动刷新。
        expires_in=max(0, int((access_expires_at - now).total_seconds())),
        refresh_expires_in=max(0, int((refresh_expires_at - now).total_seconds())),
        # 返回当前登录用户的公开信息，不包含密码哈希。
        user=UserRead.model_validate(user),
    )


def _decode_refresh_payload(refresh_token: str) -> tuple[UUID, str]:
    """解析并校验 refresh token 的 JWT payload。

    这里只检查 JWT 本身是否有效，以及它是不是 refresh 类型；
    token 是否已撤销、是否在数据库中存在，由调用方继续检查。
    """

    try:
        payload = decode_token(refresh_token)
        # refresh 接口只接受 refresh token，不接受 access token。
        if payload.get("type") != "refresh":
            raise credentials_exception()
        user_id = UUID(str(payload.get("sub")))
        # jti 用来和 refresh_tokens 表里的记录对应。
        jti = str(payload.get("jti") or "")
        if not jti:
            raise credentials_exception()
        return user_id, jti
    except (JWTError, TypeError, ValueError):
        raise credentials_exception() from None


def _is_expired(expires_at: datetime) -> bool:
    """判断数据库里的过期时间是否已经失效。"""

    return ensure_aware_utc(expires_at) <= utc_now()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """注册用户，并在注册成功后直接签发登录 token。"""

    # 先做一次业务层查重，给前端返回更明确的 409。
    stmt = select(User).where(User.username == payload.username)
    if payload.email:
        stmt = select(User).where(or_(User.username == payload.username, User.email == payload.email))

    existing_user = await session.scalar(stmt)
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists")

    # 入库前把明文密码哈希化。
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # 即使前面查过，数据库唯一索引仍然是最后一道并发保护。
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists") from None

    # commit 后刷新，拿到数据库生成的 id、created_at 等字段。
    await session.refresh(user)
    return await _issue_token_pair(session, user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """用户名/邮箱 + 密码登录，成功后签发 token 对。"""

    user = await _get_user_by_login(session, payload.username)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    return await _issue_token_pair(session, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """用 refresh token 换一组新的 access token + refresh token。

    这里采用 refresh token 轮换：旧 refresh token 使用一次后立即撤销，并写入新 token。
    """

    user_id, jti = _decode_refresh_payload(payload.refresh_token)
    token_hash = hash_token(payload.refresh_token)

    # FOR UPDATE 会锁住当前 refresh token 记录，避免并发请求重复刷新同一个 token。
    stmt = select(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.jti == jti,
        RefreshToken.token_hash == token_hash,
    ).with_for_update()
    stored_token = await session.scalar(stmt)
    if stored_token is None or stored_token.revoked_at is not None or _is_expired(stored_token.expires_at):
        raise credentials_exception()

    # JWT 有效且数据库 token 有效后，还要确认用户仍然存在并处于启用状态。
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception()

    # 签发新的 token 对。
    access_token, access_expires_at = create_access_token(user.id, user.username)
    new_refresh_token, new_refresh_jti, new_refresh_expires_at = create_refresh_token(user.id, user.username)
    now = utc_now()

    # 撤销旧 refresh token，并记录它被哪个新 token 替换。
    stored_token.revoked_at = now
    stored_token.replaced_by_jti = new_refresh_jti

    # 保存新 refresh token 的 hash。
    session.add(
        RefreshToken(
            user_id=user.id,
            jti=new_refresh_jti,
            token_hash=hash_token(new_refresh_token),
            expires_at=new_refresh_expires_at,
        )
    )
    await session.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=max(0, int((access_expires_at - now).total_seconds())),
        refresh_expires_in=max(0, int((new_refresh_expires_at - now).total_seconds())),
        user=UserRead.model_validate(user),
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: LogoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """退出登录。

    如果传入 refresh_token，只撤销这一个 token；如果不传，则撤销当前用户所有未撤销的 refresh token。
    """

    now = utc_now()

    if payload.refresh_token:
        # 防止用户拿自己的 access token 去撤销别人的 refresh token。
        user_id, jti = _decode_refresh_payload(payload.refresh_token)
        if user_id != current_user.id:
            raise credentials_exception()
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == current_user.id,
                RefreshToken.jti == jti,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
    else:
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    await session.execute(stmt)
    await session.commit()
    return MessageResponse(ok=True, message="Logged out")


@router.get("/me", response_model=UserRead)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """返回当前 access token 对应的用户信息。"""

    return current_user


@router.get("/config")
async def auth_config() -> dict[str, int | str]:
    """返回前端可能需要展示或调试的认证配置。"""

    return {
        "token_type": "bearer",
        "access_token_expire_minutes": settings.access_token_expire_minutes,
        "refresh_token_expire_days": settings.refresh_token_expire_days,
    }
