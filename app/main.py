"""Application entry point: middleware, security headers, routers, error pages."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

from app.config import settings
from app.database import Base, engine
from app.limiter import limiter
from app.routers import (
    auth,
    categories,
    pages,
    products,
    reports,
    suppliers,
    transactions,
    users,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("ims")

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Convenience for local development. In production, manage the schema
    # explicitly (Alembic migrations) and never create tables on boot.
    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
        logger.info("Development mode: schema ensured.")
    logger.info("%s starting up (env=%s)", settings.app_name, settings.environment)
    yield
    logger.info("%s shutting down.", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Web-based stock tracking system for small-scale vendors.",
    lifespan=lifespan,
    # Never expose interactive docs in production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Too many requests. Please slow down and try again shortly."},
    ),
)
app.add_middleware(SlowAPIMiddleware)


# --------------------------------------------------------------------------
# Security headers
# --------------------------------------------------------------------------
def _content_security_policy() -> str:
    directives = [
        "default-src 'self'",
        "img-src 'self' data:",
        "style-src 'self'",
        "script-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
    ]
    if not settings.is_production:
        # Swagger UI loads assets from jsdelivr and uses an inline init script,
        # so dev mode relaxes CSP just enough for /docs to work.
        # Production keeps the strict policy above.
        directives[1] = "img-src 'self' data: https://fastapi.tiangolo.com"
        directives[2] = "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
        directives[3] = "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
    return "; ".join(directives)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
        "Content-Security-Policy": _content_security_policy(),
        "Cross-Origin-Opener-Policy": "same-origin",
    }
    if settings.is_production:
        headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    for key, value in headers.items():
        response.headers.setdefault(key, value)
    return response


# --------------------------------------------------------------------------
# HTTPS enforcement (production only — local dev runs on http)
# --------------------------------------------------------------------------
if settings.is_production:
    app.add_middleware(HTTPSRedirectMiddleware)


# --------------------------------------------------------------------------
# CORS — registered last so it wraps every other middleware
# --------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    max_age=600,
)


# --------------------------------------------------------------------------
# Exception handlers
# --------------------------------------------------------------------------
def _wants_html(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return False
    return "text/html" in request.headers.get("accept", "")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == status.HTTP_404_NOT_FOUND and _wants_html(request):
        return templates.TemplateResponse(
            request=request, name="404.html", status_code=404
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    messages = []
    for err in exc.errors():
        loc = err.get("loc", [])
        # Drop the leading "body" element; keep the field name.
        field = ".".join(str(part) for part in loc[1:]) if len(loc) > 1 else "request"
        messages.append(f"{field}: {err.get('msg', 'invalid value')}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation failed.",
            "errors": messages,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    detail = str(exc) if settings.debug else "An unexpected error occurred."
    return JSONResponse(status_code=500, content={"detail": detail})


# --------------------------------------------------------------------------
# Static files
# --------------------------------------------------------------------------
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --------------------------------------------------------------------------
# Routers
# --------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(pages.router)
app.include_router(suppliers.router)
app.include_router(products.router)
app.include_router(transactions.router)
app.include_router(reports.router)
app.include_router(users.router)


# --------------------------------------------------------------------------
# Root & health
# --------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Send the bare root URL to the interactive docs."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["System"], summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}