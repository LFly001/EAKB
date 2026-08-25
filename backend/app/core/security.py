"""
JWT 鉴权 & 密码哈希工具
- JWT: 签发 / 校验 access_token + refresh_token
- 密码: bcrypt 哈希 & 校验
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# ==========================================
# bcrypt 密码哈希 (直接使用 bcrypt 库)
# ==========================================
# bcrypt 算法限制: 密码最长 72 字节，超出部分截断


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希"""
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配"""
    password_bytes = plain_password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except ValueError:
        return False


# ==========================================
# JWT Token 签发
# ==========================================


def create_access_token(
    user_id: int,
    username: str,
    role: str = "employee",
    expires_delta: timedelta | None = None,
) -> str:
    """
    签发 Access Token (短期有效)
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(
    user_id: int,
    username: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    签发 Refresh Token (长期有效，用于换取新 Access Token)
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "type": "refresh",
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


# ==========================================
# JWT Token 解码 & 校验
# ==========================================


def decode_access_token(token: str) -> dict[str, Any] | None:
    """
    解码并校验 Access Token，成功返回 payload，失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        # 验证 token 类型
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    """
    解码 Refresh Token，成功返回 payload，失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None
