import re
import unicodedata
from collections.abc import Iterator
from itertools import count

USERNAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{2,29}$"
_USERNAME_RE = re.compile(USERNAME_PATTERN)
MAX_LENGTH = 30

# Every first-level route of the site must be listed here, or a profile could shadow it.
RESERVED_USERNAMES = frozenset(
    {
        "about", "admin", "api", "backend", "conditions", "contact", "dashboard", "help", "login",
        "media", "privacy", "profil", "profilelink", "register", "settings", "static",
        "support", "terms", "www",
    }
)


def normalize_username(raw: str) -> str | None:
    username = raw.lower()
    return username if _USERNAME_RE.fullmatch(username) else None


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:MAX_LENGTH].strip("-")


def _usable(username: str) -> bool:
    return bool(_USERNAME_RE.fullmatch(username)) and username not in RESERVED_USERNAMES


def username_candidates(first_name: str, last_name: str) -> Iterator[str]:
    """bryan, then bryan-rakoto, then bryan-rakoto-2, -3…"""
    first = _slug(first_name)
    full = _slug(f"{first_name} {last_name}")
    if _usable(first):
        yield first
    if _usable(full):
        yield full
    # "va" covers names with no Latin letters, which leave nothing to build a slug from.
    base = full[: MAX_LENGTH - 7].strip("-") if _usable(full) else "va"
    for number in count(2):
        yield f"{base}-{number}"
