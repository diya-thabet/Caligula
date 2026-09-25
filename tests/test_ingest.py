import io
import json
from datetime import UTC, datetime

import httpx
from PIL import Image

from caligula.ingest.contributor import sanitize_upload
from caligula.ingest.wayback import WaybackClient


def geotagged_jpeg() -> bytes:
    img = Image.new("RGB", (4, 4), (200, 10, 10))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif.get_ifd(0x8825)[2] = (36.0, 48.0, 0.0)  # GPSLatitude
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_upload_is_hashed_before_stripping_and_gps_kept_out_of_evidence():
    original = geotagged_jpeg()
    up = sanitize_upload(original, datetime(2026, 8, 10, tzinfo=UTC))
    assert up.stripped
    assert up.custody.gps is not None
    assert up.custody.original_sha256 != ""
    clean = Image.open(io.BytesIO(up.data))
    assert len(clean.getexif()) == 0
    assert clean.size == (4, 4)


def test_unknown_format_is_kept_but_marked_unstripped():
    up = sanitize_upload(b"%PDF-1.7 fake", datetime(2026, 8, 10, tzinfo=UTC))
    assert not up.stripped
    assert up.data == b"%PDF-1.7 fake"


def test_wayback_lists_captures_and_fetches_raw_mode():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        if request.url.path == "/cdx/search/cdx":
            rows = [["timestamp", "original", "digest", "mimetype"],
                    ["20260301100000", "https://jort.example/a", "ABC", "application/pdf"]]
            return httpx.Response(200, content=json.dumps(rows))
        return httpx.Response(200, content=b"raw pdf bytes")

    client = WaybackClient(httpx.Client(transport=httpx.MockTransport(handler)))
    [cap] = client.captures("https://jort.example/a", since="2026")
    assert cap.captured_at == datetime(2026, 3, 1, 10, tzinfo=UTC)
    assert client.fetch(cap) == b"raw pdf bytes"
    assert seen[0].params["collapse"] == "digest"
    assert str(seen[1]) == "https://web.archive.org/web/20260301100000id_/https://jort.example/a"


def test_wayback_empty_response():
    client = WaybackClient(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b""))))
    assert client.captures("https://nothing.example") == []
