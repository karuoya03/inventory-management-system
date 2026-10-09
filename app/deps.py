"""Reusable FastAPI dependencies: DB session, current user, role gates, CSRF."""
from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, User
from app.security import csrf_tokens_match, decode_token

ACCESS_COOKIE = "ims_access"
REFRESH_COOKIE = "ims_refresh"
CSRF_COOKIE = "ims_csrf"
CSRF_HEADER = "X-CSRF-Token"

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str = "Not authenticated.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_token(request: Request) -> str | None:
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        return token
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def get_current_user(request: Request, db: DbSession) -> User:
    token = _extract_token(request)
    if not token:
        raise _unauthorized()

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Session expired. Please sign in again.")
    except jwt.PyJWTError:
        raise _unauthorized("Invalid session token.")

    if payload.get("type") != "access":
        raise _unauthorized("Invalid token type.")

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise _unauthorized()

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Account not found or disabled.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role):
    """Authorization enforced on the server, on every request."""
    allowed = set(roles)

    def _checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return _checker


def verify_csrf(request: Request) -> None:
    """Double-submit cookie check for every state-changing request."""
    if request.method in SAFE_METHODS:
        return
    if not csrf_tokens_match(request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed. Refresh the page and try again.",
        )


CsrfProtected = Annotated[None, Depends(verify_csrf)]