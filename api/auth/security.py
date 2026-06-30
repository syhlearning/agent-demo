from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from jose import jwt
from pwdlib import PasswordHash

from api.settings import settings

# pwdlib 会使用推荐的密码哈希策略；当前会走 Argon2。
# 这里只用于用户密码，refresh token 不使用这种慢哈希。
password_hash = PasswordHash.recommended()


def utc_now() -> datetime:
    """统一返回带 UTC 时区的当前时间，避免 naive datetime 比较问题。"""

    return datetime.now(timezone.utc)


def ensure_aware_utc(value: datetime) -> datetime:
    """把数据库读出的时间规范成 UTC aware datetime。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_password(password: str) -> str:
    """把用户明文密码转换成不可逆哈希后再入库。"""

    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """登录时校验明文密码是否匹配数据库中的密码哈希。"""

    return password_hash.verify(password, hashed_password)


def hash_token(token: str) -> str:
    """对 refresh token 做 SHA-256 哈希。

    refresh token 本身已经是高熵随机 JWT，这里用快速哈希是为了避免数据库保存明文 token。
    """

    return sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: UUID | str, username: str) -> tuple[str, datetime]:
    """签发短期 access token。

    access token 用于访问受保护接口，不入库；过期后需要通过 refresh token 换新。
    """

    expires_at = utc_now() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        # JWT 标准字段 subject，这里放用户 ID。
        "sub": str(user_id),
        "username": username,
        # 区分 access/refresh，避免 refresh token 被拿去访问业务接口。
        "type": "access",
        "iat": utc_now(),
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


def create_refresh_token(user_id: UUID | str, username: str) -> tuple[str, str, datetime]:
    """签发长期 refresh token。

    refresh token 会入库保存哈希和 jti，用来支持退出登录、撤销和轮换。
    """

    expires_at = utc_now() + timedelta(days=settings.refresh_token_expire_days)
    # jti 是 JWT ID，每个 refresh token 都有唯一标识，方便数据库追踪状态。
    jti = uuid4().hex
    payload = {
        "sub": str(user_id),
        "username": username,
        "type": "refresh",
        "jti": jti,
        "iat": utc_now(),
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def decode_token(token: str) -> dict:
    """校验 JWT 签名和过期时间，并返回 payload。

    python-jose 会在签名无效或过期时抛出 JWTError。
    """

    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
