"""`WebSearch` adapters, so agents can search the web whatever the model provider.

- SearXNG: open-source metasearch you can host yourself (no key; the
  instance must allow `format=json`). Queries then stay on your server.
- Brave Search API: hosted, needs a subscription token.
"""

from __future__ import annotations

import re

import httpx

from caligula.application.ports.sources import SearchResult

_TAGS = re.compile(r"<[^>]+>")


def _clean(text: str | None) -> str:
    return _TAGS.sub("", text or "").strip()


class SearxngSearch:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.http = client or httpx.Client(timeout=30.0)

    def search(self, query: str, k: int = 8, language: str | None = None) -> list[SearchResult]:
        params = {"q": query, "format": "json"} | ({"language": language} if language else {})
        resp = self.http.get(f"{self.base_url}/search", params=params)
        resp.raise_for_status()
        return [SearchResult(r["url"], _clean(r.get("title")), _clean(r.get("content")))
                for r in resp.json().get("results", [])[:k] if r.get("url")]


class BraveSearch:
    URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.http = client or httpx.Client(timeout=30.0)

    def search(self, query: str, k: int = 8, language: str | None = None) -> list[SearchResult]:
        params = {"q": query, "count": min(k, 20)} | ({"search_lang": language} if language else {})
        resp = self.http.get(self.URL, params=params,
                             headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"})
        resp.raise_for_status()
        results = resp.json().get("web", {}).get("results", [])
        return [SearchResult(r["url"], _clean(r.get("title")), _clean(r.get("description")))
                for r in results[:k] if r.get("url")]
