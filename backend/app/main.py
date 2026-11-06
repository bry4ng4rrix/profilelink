import logging
import time
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import admin_analytics, admin_vas, auth, public, redirect, register
from app.core.config import settings
from app.core.db import get_db
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger("app.request")
settings.media_dir.mkdir(parents=True, exist_ok=True)

_docs = {"docs_url": None, "redoc_url": None, "openapi_url": None} if settings.is_production else {}
app = FastAPI(title="ProfileLink API", **_docs)

_COOKIE_PATHS = ("/api/v1/auth/", "/api/v1/admin/")
_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin == settings.frontend_origin:
        return True
    # A same-origin request cannot be CSRF: this is how Swagger calls the API.
    return bool(origin) and urlsplit(origin).netloc == request.headers.get("host")


@app.middleware("http")
async def require_allowed_origin(request: Request, call_next) -> Response:
    # With SameSite=Lax this replaces a CSRF token, and also covers multipart uploads,
    # which browsers send without a CORS preflight.
    if (
        request.method not in _SAFE_METHODS
        and request.url.path.startswith(_COOKIE_PATHS)
        and not _origin_allowed(request)
    ):
        return JSONResponse({"detail": "origin_not_allowed"}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
    max_age=600,
)

for module in (auth, public, redirect, register, admin_vas, admin_analytics):
    app.include_router(module.router)


@app.get("/health", include_in_schema=False)
async def health(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})


# Nginx serves /media itself in production; this mount covers development.
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
