import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def notify(*usernames: str) -> None:
    """Best effort: the 5-minute TTL of the Next.js cache is the fallback if this fails."""
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.post(
                f"{settings.frontend_internal_url}/api/revalidate",
                headers={"X-Revalidate-Secret": settings.revalidate_secret},
                json={"usernames": list(usernames)},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("revalidate_failed", extra={"error": repr(exc)})
