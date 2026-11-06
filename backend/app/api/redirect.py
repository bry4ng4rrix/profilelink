import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import Db, event_context
from app.core.config import settings
from app.core.usernames import normalize_username
from app.models import ClickEvent
from app.repositories.profiles import get_redirect_target

router = APIRouter(tags=["redirect"])
logger = logging.getLogger(__name__)

_HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}


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

    context = event_context(request, ref)
    db.add(
        ClickEvent(
            profile_id=target.id,
            referer_domain=context.referer_domain,
            user_agent=context.user_agent,
            ip_hash=context.ip_hash,
        )
    )
    try:
        await db.commit()
    except (SQLAlchemyError, OSError):
        # A lost statistic must never block the visitor.
        await db.rollback()
        logger.exception("click_not_recorded")
    return RedirectResponse(target.destination_url, status_code=302, headers=_HEADERS)
