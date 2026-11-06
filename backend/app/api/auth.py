from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import COOKIE_NAME, CurrentSession, Db, require_registration_enabled
from app.core.config import settings
from app.schemas.auth import LoginIn, MeOut, RegisteredOut, RegisterIn
from app.services import admins, auth

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _cookie_scope() -> dict:
    return {
        "httponly": True,
        "secure": settings.is_production,
        "samesite": "lax",
        "domain": settings.cookie_domain or None,
        "path": "/",
    }


def _set_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(COOKIE_NAME, token, expires=expires_at, **_cookie_scope())


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_registration_enabled)],
)
async def register(data: RegisterIn) -> RegisteredOut:
    """Creates an administrator. Needs REGISTRATION_TOKEN and opens no session."""
    if not admins.registration_code_matches(data.registration_code):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid_registration_code")
    try:
        return RegisteredOut(email=await admins.create_admin(data.email, data.password))
    except admins.AdminError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.code) from exc


@router.post("/login")
async def login(data: LoginIn, response: Response, db: Db) -> MeOut:
    identity, token, expires_at = await auth.login(db, data)
    _set_cookie(response, token, expires_at)
    return identity


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(session: CurrentSession, response: Response, db: Db) -> None:
    await auth.logout(db, session)
    response.delete_cookie(COOKIE_NAME, **_cookie_scope())


@router.post("/refresh")
async def refresh(session: CurrentSession, response: Response, db: Db) -> MeOut:
    identity, token, expires_at = await auth.refresh(db, session)
    _set_cookie(response, token, expires_at)
    return identity


@router.get("/me")
async def me(session: CurrentSession, db: Db) -> MeOut:
    return await auth.me(db, session)
