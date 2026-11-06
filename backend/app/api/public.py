from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import Db, event_context
from app.core.usernames import normalize_username
from app.models import ProfileVisit
from app.repositories import vas as repository
from app.schemas.va import PublicProfileOut
from app.services import vas

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.get("/profiles/{username}")
async def get_profile(username: str, db: Db) -> PublicProfileOut:
    normalized = normalize_username(username)
    row = await repository.get_public(db, normalized) if normalized else None
    if row is None:
        raise HTTPException(404, "not_found")
    return vas.public_view(row)


@router.post("/profiles/{username}/visit", status_code=status.HTTP_204_NO_CONTENT)
async def record_visit(username: str, request: Request, db: Db, ref: str | None = None) -> None:
    normalized = normalize_username(username)
    va_id = await repository.get_active_id(db, normalized) if normalized else None
    if va_id:
        context = event_context(request, ref)
        db.add(
            ProfileVisit(
                va_profile_id=va_id,
                referer_domain=context.referer_domain,
                user_agent=context.user_agent,
                ip_hash=context.ip_hash,
            )
        )
        await db.commit()
