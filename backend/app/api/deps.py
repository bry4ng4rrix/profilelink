import re
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import hash_ip, hash_token
from app.models import AuthSession, Profile
from app.repositories import profiles, sessions

COOKIE_NAME = "pl_session"
USER_AGENT_LIMIT = 512
_HOSTNAME_RE = re.compile(r"(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}")

Db = Annotated[AsyncSession, Depends(get_db)]


async def current_session(
    db: Db, token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None
) -> AuthSession:
    session = await sessions.get_valid(db, hash_token(token)) if token else None
    if session is None:
        raise HTTPException(401, "not_authenticated")
    return session


CurrentSession = Annotated[AuthSession, Depends(current_session)]


async def current_profile(db: Db, session: CurrentSession) -> Profile:
    return await profiles.get_by_user(db, session.user_id)


CurrentProfile = Annotated[Profile, Depends(current_profile)]


@dataclass(frozen=True)
class EventContext:
    referer_domain: str | None
    user_agent: str | None
    ip_hash: str | None


def event_context(request: Request, ref: str | None) -> EventContext:
    domain = ref.lower() if ref else None
    # Nginx overwrites X-Real-IP; the backend is unreachable except through it.
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")
    return EventContext(
        referer_domain=domain if domain and _HOSTNAME_RE.fullmatch(domain) else None,
        user_agent=user_agent[:USER_AGENT_LIMIT] if user_agent else None,
        ip_hash=hash_ip(ip) if ip else None,
    )
