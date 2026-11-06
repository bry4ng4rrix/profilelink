from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

MAX_BYTES = 5 * 1024 * 1024
SIZE = (800, 800)
Image.MAX_IMAGE_PIXELS = 40_000_000  # refuses decompression bombs


def _reencode(data: bytes) -> bytes:
    """Decoding then re-encoding drops EXIF (GPS included) and any payload hidden in the file."""
    try:
        with Image.open(BytesIO(data), formats=("JPEG", "PNG", "WEBP")) as source:
            image = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGBA"), SIZE)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise HTTPException(415, "unsupported_image") from exc
    output = BytesIO()
    image.save(output, "WEBP", quality=85)
    return output.getvalue()


async def store(upload: UploadFile) -> str:
    data = await upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file_too_large")
    webp = await run_in_threadpool(_reencode, data)
    name = f"{uuid4().hex}.webp"
    await run_in_threadpool((settings.media_dir / name).write_bytes, webp)
    return f"{settings.api_public_url}/media/{name}"


def remove(photo_url: str | None) -> None:
    if photo_url:
        (settings.media_dir / Path(photo_url).name).unlink(missing_ok=True)
