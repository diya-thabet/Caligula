"""Contributor uploads (field photos, leaked invoices, delivery logs).

Two duties that pull in opposite directions:
- chain of custody: hash the exact bytes received, before anything else;
- source protection: a geotagged photo can locate the whistleblower.

So the original is hashed and its metadata split into a `CustodyRecord` that
stays in restricted storage, while only a metadata-stripped copy enters the
evidence store and can be cited.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image

from caligula.hashing import sha256_bytes

_GPS_IFD = 0x8825
_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "TIFF"}


@dataclass
class CustodyRecord:
    """Restricted: never published, never sent to an LLM."""

    original_sha256: str
    received_at: datetime
    metadata: dict = field(default_factory=dict)
    gps: dict | None = None


@dataclass
class SanitizedUpload:
    data: bytes  # safe to store and cite
    custody: CustodyRecord
    stripped: bool  # False when the format is not handled; needs manual review before publishing


def sanitize_upload(data: bytes, received_at: datetime) -> SanitizedUpload:
    custody = CustodyRecord(original_sha256=sha256_bytes(data), received_at=received_at)
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        return SanitizedUpload(data=data, custody=custody, stripped=False)
    if img.format not in _IMAGE_FORMATS:
        return SanitizedUpload(data=data, custody=custody, stripped=False)

    exif = img.getexif()
    custody.metadata = {str(k): str(v) for k, v in exif.items()}
    gps = exif.get_ifd(_GPS_IFD)
    custody.gps = {str(k): str(v) for k, v in gps.items()} or None

    # Re-encode pixels only: drops EXIF, XMP, ICC comments and thumbnails.
    clean = Image.frombytes(img.mode, img.size, img.tobytes())
    if img.mode == "P":
        clean.putpalette(img.getpalette())
    out = io.BytesIO()
    clean.save(out, format=img.format)
    return SanitizedUpload(data=out.getvalue(), custody=custody, stripped=True)
