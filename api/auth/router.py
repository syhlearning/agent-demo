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

router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_user_by_login(session: AsyncSession, login: str) -> User | None:
    value = login.strip()
    stmt = select(User).where(or_(User.username == value, User.email == value.lower()))
    return await session.scalar(stmt)


async def _issue_token_pair(session: AsyncSession, user: User) -> TokenResponse:
    access_token, access_expires_at = create_access_token(user.id, user.username)
    refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(user.id, user.username)

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
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=max(0, int((access_expires_at - now).total_seconds())),
        refresh_expires_in=max(0, int((refresh_expires_at - now).total_seconds())),
        user=UserRead.model_validate(user),
    )


def _decode_refresh_payload(refresh_token: str) -> tuple[UUID, str]:
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise credentials_exception()
        user_id = UUID(str(payload.get("sub")))
        jti = str(payload.get("jti") or "")
        if not jti:
            raise credentials_exception()
        return user_id, jti
    except (JWTError, TypeError, ValueError):
        raise credentials_exception() from None


def _is_expired(expires_at: datetime) -> bool:
    return ensure_aware_utc(expires_at) <= utc_now()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    stmt = select(User).where(User.username == payload.username)
    if payload.email:
        stmt = select(User).where(or_(User.username == payload.username, User.email == payload.email))

    existing_user = await session.scalar(stmt)
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists") from None

    await session.refresh(user)
    return await _issue_token_pair(session, user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
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
    user_id, jti = _decode_refresh_payload(payload.refresh_token)
    token_hash = hash_token(payload.refresh_token)

    stmt = select(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.jti == jti,
        RefreshToken.token_hash == token_hash,
    ).with_for_update()
    stored_token = await session.scalar(stmt)
    if stored_token is None or stored_token.revoked_at is not None or _is_expired(stored_token.expires_at):
        raise credentials_exception()

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception()

    access_token, access_expires_at = create_access_token(user.id, user.username)
    new_refresh_token, new_refresh_jti, new_refresh_expires_at = create_refresh_token(user.id, user.username)
    now = utc_now()

    stored_token.revoked_at = now
    stored_token.replaced_by_jti = new_refresh_jti
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
    now = utc_now()

    if payload.refresh_token:
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
    return current_user


@router.get("/config")
async def auth_config() -> dict[str, int | str]:
    return {
        "token_type": "bearer",
        "access_token_expire_minutes": settings.access_token_expire_minutes,
        "refresh_token_expire_days": settings.refresh_token_expire_days,
    }
