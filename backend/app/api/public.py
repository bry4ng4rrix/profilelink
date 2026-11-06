from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import Db, event_context
from app.core.usernames import normalize_username
from app.models import ProfileVisit
from app.repositories import profiles as repository
from app.schemas.profile import PublicProfileOut, SitemapEntry
from app.services import profiles

router = APIRouter(prefix="/api/v1/public", tags=["public"])

SITEMAP_LIMIT = 50_000  # shortcut: one sitemap file only, split into an index beyond this.


@router.get("/profiles/{username}")
async def get_profile(username: str, db: Db) -> PublicProfileOut:
    normalized = normalize_username(username)
    row = await repository.get_public(db, normalized) if normalized else None
    if row is None:
        raise HTTPException(404, "not_found")
    return profiles.public_view(row)


@router.post("/profiles/{username}/visit", status_code=status.HTTP_204_NO_CONTENT)
async def record_visit(username: str, request: Request, db: Db, ref: str | None = None) -> None:
    normalized = normalize_username(username)
    profile_id = await repository.get_active_id(db, normalized) if normalized else None
    if profile_id:
        context = event_context(request, ref)
        db.add(
            ProfileVisit(
                profile_id=profile_id,
                referer_domain=context.referer_domain,
                user_agent=context.user_agent,
                ip_hash=context.ip_hash,
            )
        )
        await db.commit()


@router.get("/sitemap")
async def sitemap(db: Db) -> list[SitemapEntry]:
    rows = await repository.list_for_sitemap(db, SITEMAP_LIMIT)
    return [SitemapEntry(username=r.username, updated_at=r.updated_at) for r in rows]
