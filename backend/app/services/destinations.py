import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

import idna
from fastapi import HTTPException

from app.core.config import settings

MAX_LENGTH = 2048
DNS_TIMEOUT_SECONDS = 3
_LOCAL_SUFFIXES = ("localhost", "local", "internal", "intranet", "lan", "home.arpa")
_INSTAGRAM_HOSTS = ("instagram.com", "www.instagram.com")


def _invalid() -> HTTPException:
    return HTTPException(422, "invalid_destination")


def _has_unsafe_characters(url: str) -> bool:
    # urlsplit silently drops tabs and newlines, and browsers read a backslash as a slash.
    return any(c <= " " or c in "\x7f\\" for c in url)


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:
        # inet_aton also reads what browsers accept: 2130706433, 0x7f.1, 0177.0.0.1, 127.1
        return ipaddress.ip_address(socket.inet_aton(host))
    except OSError:
        return None


def _is_own_or_local(host: str) -> bool:
    domains = (*_LOCAL_SUFFIXES, settings.site_domain)
    return any(host == d or host.endswith(f".{d}") for d in domains)


async def resolve_host(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


async def validate(raw: str) -> str:
    """Return the normalised URL or refuse it. The API itself never requests the destination."""
    url = raw.strip()
    if not url or len(url) > MAX_LENGTH or _has_unsafe_characters(url):
        raise _invalid()
    try:
        parts = urlsplit(url)
        port = parts.port
        hostname = (parts.hostname or "").rstrip(".").lower()
        host = hostname if hostname.isascii() else idna.encode(hostname, uts46=True).decode()
    except (ValueError, idna.IDNAError) as exc:
        raise _invalid() from exc

    if parts.scheme.lower() not in ("http", "https") or not host:
        raise _invalid()
    if parts.username is not None or parts.password is not None:
        raise _invalid()

    ip = _parse_ip(host)
    if ip is not None:
        if not _is_public(ip):
            raise _invalid()
    else:
        if "." not in host or _is_own_or_local(host):
            raise _invalid()
        try:
            async with asyncio.timeout(DNS_TIMEOUT_SECONDS):
                addresses = await resolve_host(host, port or 443)
        except (OSError, TimeoutError) as exc:
            raise _invalid() from exc
        if not addresses or not all(_is_public(ipaddress.ip_address(a)) for a in addresses):
            raise _invalid()

    if hostname == host:
        return url
    netloc = f"{host}:{port}" if port else host
    return urlunsplit(parts._replace(netloc=netloc))


def validate_instagram(raw: str) -> str:
    """Parses the host instead of matching text: instagram.com@evil.test is a real trap."""
    url = raw.strip()
    invalid = HTTPException(422, "invalid_instagram")
    if len(url) > MAX_LENGTH or _has_unsafe_characters(url):
        raise invalid
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise invalid from exc
    if (
        parts.scheme.lower() not in ("http", "https")
        or (parts.hostname or "").lower() not in _INSTAGRAM_HOSTS
        or parts.username is not None
        or parts.password is not None
        or port is not None
        or not parts.path.strip("/")
    ):
        raise invalid
    return url
