"""Authentication endpoints: login, logout, refresh, current user, registration."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select

from app.config import settings
from app.deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    CsrfProtected,
    CurrentUser,
    DbSession,
    require_roles,
)
from app.limiter import limiter
from app.models import Role, User
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserPublic
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_csrf_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _cookie_kwargs() -> dict:
    return {
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/",
        "domain": settings.cookie_domain or None,
    }


def _issue_session(response: Response, user: User) -> TokenResponse:
    access = create_access_token(user.id, user.role.value)
    refresh = create_refresh_token(user.id)
    csrf = generate_csrf_token()
    base = _cookie_kwargs()

    # httpOnly so JavaScript can never read the tokens (XSS containment)
    response.set_cookie(
        ACCESS_COOKIE, access,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True, **base,
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True, **base,
    )
    # Readable by JS on purpose — the frontend echoes it back in a header.
    response.set_cookie(
        CSRF_COOKIE, csrf,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=False, **base,
    )

    return TokenResponse(
        access_token=access,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def _clear_session(response: Response) -> None:
    base = _cookie_kwargs()
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", domain=base.get("domain"))


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@router.post("/login", response_model=TokenResponse, summary="Sign in")
@limiter.limit("5/minute")
def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    user = db.scalar(
        select(User).where(
            or_(User.username == payload.username, User.email == payload.username)
        )
    )

    # Same message and same code path whether the user exists or not.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been disabled.",
        )

    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    return _issue_session(response, user)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh session")
@limiter.limit("20/hour")
def refresh(request: Request, response: Response, db: DbSession) -> TokenResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token supplied.")

    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired.")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type.")

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account not found or disabled.")

    return _issue_session(response, user)


@router.post("/logout", status_code=204, summary="Sign out")
def logout(response: Response, _csrf: CsrfProtected) -> Response:
    _clear_session(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserPublic, summary="Current signed-in user")
def me(user: CurrentUser) -> User:
    return user


@router.get("/csrf", summary="Get a CSRF token")
def csrf_token(response: Response) -> dict[str, str]:
    token = generate_csrf_token()
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=False,
        **_cookie_kwargs(),
    )
    return {"csrf_token": token}


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a staff account (admin only)",
)
def register(
    payload: UserCreate,
    db: DbSession,
    _csrf: CsrfProtected,
    _admin: Annotated[User, Depends(require_roles(Role.ADMIN))],
) -> User:
    exists = db.scalar(
        select(User).where(
            or_(User.username == payload.username, User.email == payload.email)
        )
    )
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That username or email is already registered.",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user