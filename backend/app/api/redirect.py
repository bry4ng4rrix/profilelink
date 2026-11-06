import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Db, EventContext, event_context
from app.core.config import settings
from app.core.security import hash_token, new_session_token
from app.core.usernames import normalize_username
from app.models import ClickEvent
from app.repositories import events
from app.repositories.vas import get_redirect_target

router = APIRouter(tags=["redirect"])
logger = logging.getLogger(__name__)

_HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}
VISITOR_COOKIE = "pl_visitor"
VISITOR_COOKIE_SECONDS = 365 * 24 * 3600


async def _count_click(
    db: AsyncSession, va_id: UUID, context: EventContext, visitor_hash: str
) -> None:
    """Counts one click per person for each VA. A lost statistic never blocks the visitor."""
    try:
        if await events.click_seen(db, va_id, context.ip_hash, visitor_hash):
            return
        db.add(
            ClickEvent(
                va_profile_id=va_id,
                referer_domain=context.referer_domain,
                user_agent=context.user_agent,
                ip_hash=context.ip_hash,
                visitor_hash=visitor_hash,
            )
        )
        await db.commit()
    except (SQLAlchemyError, OSError):
        await db.rollback()
        logger.exception("click_not_recorded")


@router.get("/r/{username}", include_in_schema=False)
async def redirect(username: str, request: Request, db: Db, ref: str | None = None):
    normalized = normalize_username(username)
    if normalized is None:
        raise HTTPException(404, "not_found")

    target = await get_redirect_target(db, normalized)
    if target is None:
        return RedirectResponse(
            f"{settings.frontend_origin}/{normalized}", status_code=302, headers=_HEADERS
        )

    visitor_id = request.cookies.get(VISITOR_COOKIE) or new_session_token()
    await _count_click(db, target.id, event_context(request, ref), hash_token(visitor_id))

    response = RedirectResponse(target.destination_url, status_code=302, headers=_HEADERS)
    response.set_cookie(
        VISITOR_COOKIE,
        visitor_id,
        max_age=VISITOR_COOKIE_SECONDS,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    return response
