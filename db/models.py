from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """系统用户表。

    保存登录账号的基础信息。密码只保存哈希值，不保存明文密码。
    """

    __tablename__ = "users"

    # 用户主键，使用 UUID 避免暴露自增 ID。
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # 登录用户名；当前登录接口支持用 username 登录。
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    # 邮箱可选；如果填写，也可以作为登录标识使用。
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)

    # Argon2 哈希后的密码，永远不要保存明文密码。
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # 账号是否可用；禁用后不能登录，也不能通过 access token 访问受保护接口。
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # 账号创建时间，由数据库自动写入。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # 账号资料更新时间；通过 SQLAlchemy 更新该行时会自动刷新。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 一个用户可以有多个 refresh token，例如多设备登录或多次登录。
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RefreshToken(Base):
    """Refresh token 状态表。

    access token 不入库；refresh token 只保存哈希和状态，用来支持续签、退出登录和 token 轮换。
    """

    __tablename__ = "refresh_tokens"

    # token 记录主键。
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # 归属用户；用户删除时，数据库会级联删除该用户的所有 refresh token。
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # JWT ID，用来唯一标识某一个 refresh token。
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    # refresh token 的 SHA-256 哈希；数据库不保存 refresh token 明文。
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    # refresh token 过期时间。
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 撤销时间；不为空表示这个 refresh token 已退出或已被轮换失效。
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # refresh token 轮换后，新 token 的 jti，便于追踪替换关系。
    replaced_by_jti: Mapped[str | None] = mapped_column(String(64))

    # token 记录创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # 反向关联到用户，可通过 refresh_token.user 访问所属用户。
    user: Mapped[User] = relationship(back_populates="refresh_tokens")
