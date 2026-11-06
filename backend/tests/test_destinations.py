import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import VaProfile
from tests.conftest import ADMIN, create_va, post_va

REFUSED = [
    # Dangerous schemes
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "file:///etc/passwd",
    "ftp://example.com/",
    "gopher://example.com/",
    "vbscript:msgbox(1)",
    # Malformed
    "   ",
    "not a url",
    "example.com",
    "//example.com/path",
    "http://",
    "https:///path",
    "https://example.com:99999/",
    "https://example.com:port/",
    "https://exa mple.com/",
    "https://example.com/a\nb",
    "https://example.com/\ttab",
    "https://example.com\\@evil.test/",
    "https://" + "a" * 2050 + ".com/",
    # Credentials in the URL
    "https://paypal.com@evil.test/",
    "https://user:pass@example.com/",
    # Local names
    "http://localhost/",
    "http://localhost:8000/",
    "http://LOCALHOST/",
    "http://foo.localhost/",
    "http://printer.local/",
    "http://db.internal/",
    "http://intranet/",
    "http://localhost./",
    # Private, reserved and metadata addresses
    "http://127.0.0.1/",
    "http://127.1/",
    "http://10.0.0.1/",
    "http://172.16.0.1/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://100.64.0.1/",
    "http://0.0.0.0/",
    "http://224.0.0.1/",
    "http://240.0.0.1/",
    "http://255.255.255.255/",
    "http://[::1]/",
    "http://[::]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[::ffff:10.0.0.1]/",
    "http://[fe80::1]/",
    "http://[fc00::1]/",
    # Obfuscated forms of 127.0.0.1
    "http://2130706433/",
    "http://0x7f000001/",
    "http://0x7f.1/",
    "http://0177.0.0.1/",
    # The service itself (redirect loop)
    "https://profil.test/bryan",
    "https://api.profil.test/r/bryan",
    # DNS answers
    "https://internal.example.com/",
    "https://metadata.example.com/",
    "https://missing.example.com/",
]

ACCEPTED = [
    "https://example.com/",
    "http://example.com/",
    "HTTPS://Example.com/Path?q=1#frag",
    "https://example.com:8443/path",
    "https://sub.domain.example.com/a/b?x=1&y=2",
    "https://example.com/caf%C3%A9",
    "http://8.8.8.8/",
    "http://[2606:4700:4700::1111]/",
    "https://my_site.example.com/",
]


@pytest.mark.parametrize("url", REFUSED)
async def test_refused_on_create(admin, url):
    response = await post_va(admin, destination_url=url)

    assert response.status_code == 422, url
    assert response.json()["detail"] == "invalid_destination"
    async with SessionLocal() as db:
        assert await db.scalar(select(VaProfile)) is None


@pytest.mark.parametrize("url", ["javascript:alert(1)", "http://127.0.0.1/", "http://localhost/"])
async def test_refused_on_update(admin, url):
    va = await create_va(admin)

    response = await admin.put(f"{ADMIN}/{va['id']}/link", json={"destination_url": url})

    assert response.status_code == 422
    body = (await admin.get(f"{ADMIN}/{va['id']}")).json()
    assert body["link"]["destination_url"] == va["link"]["destination_url"]


@pytest.mark.parametrize("url", ACCEPTED)
async def test_accepted(admin, url):
    va = await create_va(admin, destination_url=url)

    assert va["link"]["destination_url"] == url


async def test_international_domain_is_stored_as_punycode(admin):
    va = await create_va(admin, destination_url="https://bücher.example.com:8443/livre?x=1#y")

    assert va["link"]["destination_url"] == "https://xn--bcher-kva.example.com:8443/livre?x=1#y"


async def test_surrounding_spaces_are_removed(admin):
    va = await create_va(admin, destination_url="  https://example.com/  ")

    assert va["link"]["destination_url"] == "https://example.com/"
