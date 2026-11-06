import re

from fastapi import HTTPException

USERNAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{2,29}$"
_USERNAME_RE = re.compile(USERNAME_PATTERN)

# Every first-level route of the site must be listed here, or a profile could shadow it.
RESERVED_USERNAMES = frozenset(
    {
        "about", "admin", "api", "conditions", "contact", "dashboard", "help", "login",
        "media", "privacy", "profil", "profilelink", "register", "settings", "static",
        "support", "terms", "www",
    }
)


def normalize_username(raw: str) -> str | None:
    username = raw.lower()
    return username if _USERNAME_RE.fullmatch(username) else None


def ensure_allowed(username: str) -> None:
    if username in RESERVED_USERNAMES:
        raise HTTPException(422, "reserved_username")
