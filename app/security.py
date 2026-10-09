"""Password hashing, JWT issuing/decoding and CSRF token helpers."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import settings

BCRYPT_MAX_BYTES = 72
BCRYPT_ROUNDS = 12


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES:
        raise ValueError("Password exceeds the maximum supported length.")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
def _encode(subject: str, token_type: str, expires: timedelta, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
        "jti": secrets.token_urlsafe(16),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(user_id: int, role: str) -> str:
    return _encode(
        str(user_id),
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        {"role": role},
    )


def create_refresh_token(user_id: int) -> str:
    return _encode(str(user_id), "refresh", timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError on invalid/expired tokens."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


# --------------------------------------------------------------------------
# CSRF (double-submit cookie pattern)
# --------------------------------------------------------------------------
def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_tokens_match(cookie_value: str | None, header_value: str | None) -> bool:
    if not cookie_value or not header_value:
        return False
    return secrets.compare_digest(cookie_value, header_value)