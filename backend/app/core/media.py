import io
import logging
from dataclasses import dataclass

import cloudinary
import cloudinary.uploader
import cloudinary.exceptions
from fastapi import HTTPException, UploadFile

from app.core.config import settings

logger = logging.getLogger(__name__)

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)

ALLOWED_FORMATS = ["jpg", "png", "webp"]
MAX_IMAGE_BYTES = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024


@dataclass
class UploadedImage:
    url: str
    public_id: str


def detect_image_format(data: bytes) -> str | None:
    """Identify the image type from its first bytes ("magic numbers").

    The client-supplied filename and Content-Type are not trusted.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def read_image(file: UploadFile) -> bytes:
    """Read an uploaded file and check that it is a small JPEG/PNG/WebP."""
    # read at most one byte past the limit, so huge files aren't loaded fully
    data = file.file.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Image file is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image is larger than {settings.MAX_IMAGE_SIZE_MB} MB",
        )
    if detect_image_format(data) is None:
        raise HTTPException(
            status_code=415, detail="Only JPEG, PNG and WebP images are allowed"
        )
    return data


def upload_image(data: bytes, user_id: int) -> UploadedImage:
    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(data),
            folder=f"posts/{user_id}",
            resource_type="image",
            allowed_formats=ALLOWED_FORMATS,
            unique_filename=True,
            overwrite=False,
            timeout=30,
        )
    except cloudinary.exceptions.BadRequest:
        # Cloudinary could not decode it (e.g. valid header, corrupt body)
        raise HTTPException(status_code=400, detail="Invalid image file")
    except Exception:
        logger.exception("Cloudinary upload failed")
        raise HTTPException(status_code=502, detail="Image upload failed, try again")

    return UploadedImage(url=result["secure_url"], public_id=result["public_id"])


def delete_image(public_id: str | None) -> None:
    """Best-effort delete; a failure only leaves an orphaned file behind."""
    if not public_id:
        return
    try:
        cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
    except Exception:
        logger.exception("Failed to delete Cloudinary image %s", public_id)
