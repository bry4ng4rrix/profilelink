from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import ClickEvent, VaExternalLink, VaProfile
from tests.conftest import (
    ADMIN,
    DESTINATION,
    INSTAGRAM,
    create_va,
    image_bytes,
    photo_file,
    post_va,
)


def stored(url: str) -> Path:
    return settings.media_dir / Path(url).name


async def va_rows() -> list[VaProfile]:
    async with SessionLocal() as db:
        return list((await db.scalars(select(VaProfile))).all())


async def test_create_returns_the_full_va(admin, revalidated):
    va = await create_va(admin, first_name=" Bryan ", instagram_url=f"  {INSTAGRAM}  ")

    assert va["username"] == "bryan"
    assert va["first_name"] == "Bryan"
    assert va["last_name"] == "Rakoto"
    assert va["age"] == 27
    assert va["instagram_url"] == INSTAGRAM
    assert va["is_active"] is True
    assert va["public_url"] == f"{settings.frontend_origin}/bryan"
    assert va["link"] == {"destination_url": DESTINATION, "is_active": True}
    assert va["photo_url"].startswith(f"{settings.api_public_url}/media/")
    assert revalidated[-1] == ("bryan",)


@pytest.mark.parametrize(
    "field,value",
    [
        ("first_name", ""),
        ("first_name", "   "),
        ("first_name", "x" * 101),
        ("last_name", ""),
        ("age", 0),
        ("age", -1),
        ("age", 121),
        ("age", "vingt"),
    ],
)
async def test_create_rejects_invalid_fields(admin, field, value):
    response = await post_va(admin, **{field: value})

    assert response.status_code == 422
    assert await va_rows() == []


@pytest.mark.parametrize(
    "field", ["first_name", "last_name", "age", "instagram_url", "destination_url"]
)
async def test_every_field_is_required(admin, field):
    data = {
        "first_name": "Bryan",
        "last_name": "Rakoto",
        "age": 27,
        "instagram_url": INSTAGRAM,
        "destination_url": DESTINATION,
    }
    del data[field]

    response = await admin.post(ADMIN, data=data, files={"photo": photo_file()})

    assert response.status_code == 422


async def test_photo_is_required(admin):
    response = await admin.post(
        ADMIN,
        data={
            "first_name": "Bryan",
            "last_name": "Rakoto",
            "age": 27,
            "instagram_url": INSTAGRAM,
            "destination_url": DESTINATION,
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize("age", [1, 17, 18, 120])
async def test_no_minimum_age_is_enforced(admin, age):
    assert (await post_va(admin, age=age)).status_code == 201


async def test_creation_with_a_bad_destination_leaves_nothing(admin):
    before = set(settings.media_dir.iterdir())

    response = await post_va(admin, destination_url="http://127.0.0.1/")

    assert response.json()["detail"] == "invalid_destination"
    assert await va_rows() == []
    assert set(settings.media_dir.iterdir()) == before


async def test_creation_with_a_bad_photo_leaves_nothing(admin):
    response = await post_va(admin, photo=b"not an image")

    assert (response.status_code, response.json()["detail"]) == (415, "unsupported_image")
    assert await va_rows() == []


async def test_list_shows_all_vas_newest_first(admin):
    await create_va(admin, first_name="Bryan")
    await create_va(admin, first_name="Marie")

    body = (await admin.get(ADMIN)).json()

    assert [va["username"] for va in body] == ["marie", "bryan"]
    assert set(body[0]) >= {"photo_url", "instagram_url", "public_url", "link"}


async def test_read_a_va(admin):
    va = await create_va(admin)

    assert (await admin.get(f"{ADMIN}/{va['id']}")).json()["id"] == va["id"]


async def test_update_fields(admin, revalidated):
    va = await create_va(admin)

    response = await admin.put(
        f"{ADMIN}/{va['id']}",
        json={
            "first_name": "Brian",
            "last_name": "Rabe",
            "age": 28,
            "instagram_url": "https://instagram.com/brian",
        },
    )

    body = response.json()
    assert (body["first_name"], body["last_name"]) == ("Brian", "Rabe")
    assert (body["age"], body["instagram_url"]) == (28, "https://instagram.com/brian")
    assert body["link"]["destination_url"] == DESTINATION
    assert revalidated[-1] == ("bryan",)


async def test_update_rejects_invalid_fields(admin):
    va = await create_va(admin)

    response = await admin.put(
        f"{ADMIN}/{va['id']}",
        json={"first_name": "", "last_name": "Rabe", "age": 28, "instagram_url": INSTAGRAM},
    )

    assert response.status_code == 422
    assert (await admin.get(f"{ADMIN}/{va['id']}")).json()["first_name"] == "Bryan"


async def test_update_cannot_change_protected_fields(admin):
    va = await create_va(admin)

    await admin.put(
        f"{ADMIN}/{va['id']}",
        json={
            "first_name": "Bryan",
            "last_name": "Rakoto",
            "age": 27,
            "instagram_url": INSTAGRAM,
            "username": "hacked",
            "is_active": False,
            "photo_url": "https://evil.test/x.png",
        },
    )

    body = (await admin.get(f"{ADMIN}/{va['id']}")).json()
    assert body["username"] == "bryan"
    assert body["is_active"] is True
    assert body["photo_url"] == va["photo_url"]


async def test_status(admin, revalidated):
    va = await create_va(admin)

    response = await admin.patch(f"{ADMIN}/{va['id']}/status", json={"is_active": False})

    assert response.json()["is_active"] is False
    assert revalidated[-1] == ("bryan",)


async def test_link_can_be_changed_and_disabled(admin, revalidated):
    va = await create_va(admin)

    changed = await admin.put(
        f"{ADMIN}/{va['id']}/link", json={"destination_url": "https://other.example.com/"}
    )
    disabled = await admin.patch(f"{ADMIN}/{va['id']}/link/status", json={"is_active": False})

    assert changed.json()["link"]["destination_url"] == "https://other.example.com/"
    assert disabled.json()["link"]["is_active"] is False
    assert len(revalidated) == 3


async def test_photo_is_reencoded_to_a_square_webp(admin):
    with Image.open(stored((await create_va(admin))["photo_url"])) as image:
        assert (image.format, image.size) == ("WEBP", (800, 800))


async def test_photo_loses_its_exif_metadata(admin):
    exif = Image.Exif()
    exif[0x010F] = "SECRET-CAMERA"
    data = image_bytes("JPEG", exif=exif)
    assert b"SECRET-CAMERA" in data

    va = await create_va(admin, photo=data)

    assert b"SECRET-CAMERA" not in stored(va["photo_url"]).read_bytes()


async def test_replacing_a_photo_deletes_the_previous_file(admin, revalidated):
    va = await create_va(admin)

    response = await admin.post(f"{ADMIN}/{va['id']}/photo", files={"file": photo_file()})

    assert response.json()["photo_url"] != va["photo_url"]
    assert not stored(va["photo_url"]).exists()
    assert stored(response.json()["photo_url"]).exists()
    assert revalidated[-1] == ("bryan",)


@pytest.mark.parametrize(
    "data",
    [
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        b"<?php echo 1; ?>",
        b"GIF89a" + b"\x00" * 100,
        b"",
    ],
)
async def test_photo_is_judged_by_content_not_by_declared_type(admin, data):
    va = await create_va(admin)

    response = await admin.post(f"{ADMIN}/{va['id']}/photo", files={"file": photo_file(data)})

    assert (response.status_code, response.json()["detail"]) == (415, "unsupported_image")
    assert stored(va["photo_url"]).exists()


async def test_photo_size_limit(admin):
    va = await create_va(admin)

    response = await admin.post(
        f"{ADMIN}/{va['id']}/photo", files={"file": photo_file(b"x" * (5 * 1024 * 1024 + 1))}
    )

    assert (response.status_code, response.json()["detail"]) == (413, "file_too_large")


async def test_delete_removes_the_va_its_link_its_stats_and_its_photo(admin, visitor, revalidated):
    va = await create_va(admin)
    await visitor.get("/r/bryan")

    assert (await admin.delete(f"{ADMIN}/{va['id']}")).status_code == 204

    assert await va_rows() == []
    async with SessionLocal() as db:
        assert await db.scalar(select(VaExternalLink)) is None
        assert await db.scalar(select(ClickEvent)) is None
    assert not stored(va["photo_url"]).exists()
    assert revalidated[-1] == ("bryan",)
    assert (await visitor.get("/api/v1/public/profiles/bryan")).status_code == 404


async def test_deleted_address_can_be_reused(admin):
    va = await create_va(admin)
    await admin.delete(f"{ADMIN}/{va['id']}")

    assert (await create_va(admin))["username"] == "bryan"


@pytest.mark.parametrize(
    "method,suffix",
    [("GET", ""), ("DELETE", ""), ("PATCH", "/status"), ("PATCH", "/link/status")],
)
async def test_unknown_va_is_404(admin, method, suffix):
    response = await admin.request(method, f"{ADMIN}/{uuid4()}{suffix}", json={"is_active": True})

    assert response.status_code == 404
