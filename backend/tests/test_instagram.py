import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import VaProfile
from tests.conftest import ADMIN, INSTAGRAM, create_va, post_va

REFUSED = [
    "",
    "   ",
    "pas un lien",
    "instagram.com/bryan",
    "@bryan",
    "bryan",
    "javascript:alert(1)",
    "ftp://instagram.com/bryan",
    "https://instagram.com",
    "https://instagram.com/",
    "https://www.instagram.com/",
    "https://evil.test/instagram.com/bryan",
    "https://instagram.com.evil.test/bryan",
    "https://fakeinstagram.com/bryan",
    "https://instagram.com@evil.test/bryan",
    "https://user:pass@instagram.com/bryan",
    "https://instagram.com:8443/bryan",
    "https://instagram.com\\@evil.test/bryan",
    "https://instagram.com/bry an",
    "https://instagram.com/bryan\nX: 1",
    "https://instagram.com:port/bryan",
]

ACCEPTED = [
    "https://instagram.com/bryan",
    "https://www.instagram.com/bryan",
    "https://www.instagram.com/bryan/",
    "http://instagram.com/bryan",
    "HTTPS://WWW.INSTAGRAM.COM/bryan.rakoto",
    "https://www.instagram.com/bryan_rakoto/?hl=fr",
]


@pytest.mark.parametrize("url", REFUSED)
async def test_refused_on_create(admin, url):
    response = await post_va(admin, instagram_url=url)

    assert response.status_code == 422, url
    if url:  # an empty form field is already refused by FastAPI as missing
        assert response.json()["detail"] == "invalid_instagram"
    async with SessionLocal() as db:
        assert await db.scalar(select(VaProfile)) is None


@pytest.mark.parametrize("url", ["https://evil.test/x", "javascript:alert(1)"])
async def test_refused_on_update_without_changing_anything(admin, url):
    va = await create_va(admin)

    response = await admin.put(
        f"{ADMIN}/{va['id']}",
        json={"first_name": "Autre", "last_name": "Nom", "age": 30, "instagram_url": url},
    )

    assert (response.status_code, response.json()["detail"]) == (422, "invalid_instagram")
    body = (await admin.get(f"{ADMIN}/{va['id']}")).json()
    assert body["first_name"] == "Bryan"
    assert body["instagram_url"] == INSTAGRAM


@pytest.mark.parametrize("url", ACCEPTED)
async def test_accepted(admin, url):
    va = await create_va(admin, instagram_url=url)

    assert va["instagram_url"] == url


async def test_a_bad_instagram_link_leaves_no_photo_behind(admin):
    before = set(settings.media_dir.iterdir())

    await post_va(admin, instagram_url="https://evil.test/x")

    assert set(settings.media_dir.iterdir()) == before


async def test_two_vas_can_share_a_link(admin):
    await create_va(admin, first_name="Bryan")

    assert (await post_va(admin, first_name="Marie")).status_code == 201
