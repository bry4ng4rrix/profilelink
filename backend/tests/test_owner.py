from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from app.core.config import settings
from tests.conftest import add_link

PROFILE = "/api/v1/owner/profile"
LINKS = "/api/v1/owner/links"


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (800, 600), **options) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, fmt, **options)
    return output.getvalue()


def photo(data: bytes, content_type: str = "image/png") -> dict:
    return {"file": ("photo.png", data, content_type)}


async def test_read_and_update_profile(owner, revalidated):
    assert (await owner.get(PROFILE)).json()["public_url"] == f"{settings.frontend_origin}/bryan"

    response = await owner.put(
        PROFILE,
        json={"username": "bryan2", "first_name": " Bryan ", "last_name": "", "bio": "Salut"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "bryan2"
    assert body["first_name"] == "Bryan"
    assert body["last_name"] is None
    assert body["public_url"].endswith("/bryan2")
    assert revalidated[-1] == ("bryan", "bryan2")


@pytest.mark.parametrize(
    "changes",
    [{"bio": "x" * 501}, {"first_name": "x" * 101}, {"username": "No Spaces"}, {"username": "ab"}],
)
async def test_update_rejects_invalid_values(owner, changes):
    response = await owner.put(PROFILE, json={"username": "bryan"} | changes)

    assert response.status_code == 422


async def test_update_rejects_reserved_and_taken_usernames(owner_factory):
    bryan = await owner_factory("bryan")
    await owner_factory("taken")

    reserved = await bryan.put(PROFILE, json={"username": "dashboard"})
    taken = await bryan.put(PROFILE, json={"username": "taken"})

    assert (reserved.status_code, reserved.json()["detail"]) == (422, "reserved_username")
    assert (taken.status_code, taken.json()["detail"]) == (409, "username_taken")
    assert (await bryan.get(PROFILE)).json()["username"] == "bryan"


async def test_profile_status(owner, revalidated):
    response = await owner.patch(f"{PROFILE}/status", json={"is_active": False})

    assert response.json()["is_active"] is False
    assert revalidated[-1] == ("bryan",)


async def test_photo_is_reencoded_to_a_square_webp(owner, revalidated):
    response = await owner.post(f"{PROFILE}/photo", files=photo(image_bytes()))

    assert response.status_code == 200
    url = response.json()["photo_url"]
    assert url.startswith(f"{settings.api_public_url}/media/") and url.endswith(".webp")
    stored = settings.media_dir / Path(url).name
    with Image.open(stored) as image:
        assert (image.format, image.size) == ("WEBP", (800, 800))
    assert revalidated[-1] == ("bryan",)


async def test_photo_loses_its_exif_metadata(owner):
    exif = Image.Exif()
    exif[0x010F] = "SECRET-CAMERA"
    data = image_bytes("JPEG", exif=exif)
    assert b"SECRET-CAMERA" in data

    url = (await owner.post(f"{PROFILE}/photo", files=photo(data))).json()["photo_url"]

    assert b"SECRET-CAMERA" not in (settings.media_dir / Path(url).name).read_bytes()


async def test_replacing_a_photo_deletes_the_previous_file(owner):
    first = (await owner.post(f"{PROFILE}/photo", files=photo(image_bytes()))).json()["photo_url"]
    await owner.post(f"{PROFILE}/photo", files=photo(image_bytes()))

    assert not (settings.media_dir / Path(first).name).exists()


@pytest.mark.parametrize(
    "data",
    [
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        b"<?php echo 1; ?>",
        b"GIF89a" + b"\x00" * 100,
        b"",
    ],
)
async def test_photo_is_judged_by_content_not_by_declared_type(owner, data):
    response = await owner.post(f"{PROFILE}/photo", files=photo(data, "image/png"))

    assert (response.status_code, response.json()["detail"]) == (415, "unsupported_image")


async def test_photo_size_limit(owner):
    response = await owner.post(f"{PROFILE}/photo", files=photo(b"x" * (5 * 1024 * 1024 + 1)))

    assert (response.status_code, response.json()["detail"]) == (413, "file_too_large")


async def test_link_crud(owner, revalidated):
    assert (await owner.get(LINKS)).json() == []

    link = await add_link(owner)
    assert link["is_active"] is True
    assert [item["id"] for item in (await owner.get(LINKS)).json()] == [link["id"]]

    updated = await owner.put(
        f"{LINKS}/{link['id']}", json={"destination_url": "https://other.example.com/"}
    )
    assert updated.json()["destination_url"] == "https://other.example.com/"

    disabled = await owner.patch(f"{LINKS}/{link['id']}/status", json={"is_active": False})
    assert disabled.json()["is_active"] is False

    assert (await owner.delete(f"{LINKS}/{link['id']}")).status_code == 204
    assert (await owner.get(LINKS)).json() == []
    assert len(revalidated) == 4


async def test_second_link_is_refused(owner):
    await add_link(owner)

    response = await owner.post(LINKS, json={"destination_url": "https://other.example.com/"})

    assert (response.status_code, response.json()["detail"]) == (409, "link_exists")


async def test_unknown_link_is_404(owner):
    assert (await owner.delete(f"{LINKS}/{uuid4()}")).status_code == 404
