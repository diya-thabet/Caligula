"""Wayback Machine ingester.

Lists captures through the CDX API and fetches each one in raw mode (`id_`),
so we hash the bytes the site actually served rather than Wayback's rewritten
replay page. An archive capture proves the content existed at capture time; it
does not prove the content is true.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

CDX_URL = "https://web.archive.org/cdx/search/cdx"
RAW_URL = "https://web.archive.org/web/{timestamp}id_/{url}"


@dataclass(frozen=True)
class Capture:
    timestamp: str
    original: str
    digest: str  # Wayback's own SHA-1 (base32) of the payload
    mimetype: str

    @property
    def captured_at(self) -> datetime:
        return datetime.strptime(self.timestamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)

    @property
    def raw_url(self) -> str:
        return RAW_URL.format(timestamp=self.timestamp, url=self.original)


class WaybackClient:
    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=30.0, follow_redirects=True)

    def captures(self, url: str, since: str | None = None, until: str | None = None) -> list[Capture]:
        """Successful captures of `url`, one per distinct payload, oldest first."""
        params = {
            "url": url,
            "output": "json",
            "fl": "timestamp,original,digest,mimetype",
            "filter": "statuscode:200",
            "collapse": "digest",
        }
        if since:
            params["from"] = since
        if until:
            params["to"] = until
        resp = self.http.get(CDX_URL, params=params)
        resp.raise_for_status()
        rows = resp.json() if resp.content.strip() else []
        return [Capture(*row) for row in rows[1:]]  # first row is the header

    def fetch(self, capture: Capture) -> bytes:
        resp = self.http.get(capture.raw_url)
        resp.raise_for_status()
        return resp.content
