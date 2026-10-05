"""Live web fetching (`WebFetcher` adapter).

Every fetched response is hashed and stored before an agent reads it, so the
evidence cited in a verdict is the exact bytes we saw, whatever the site shows
later.
"""

from __future__ import annotations

import httpx

from caligula.application.ports.sources import Fetched


class LiveFetcher:
    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=30.0, follow_redirects=True)

    def fetch(self, url: str) -> Fetched:
        resp = self.http.get(url)
        resp.raise_for_status()
        return Fetched(str(resp.url), resp.content, resp.headers.get("content-type", ""))
