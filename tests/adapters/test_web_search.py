import httpx

from caligula.adapters.sources.web_search import BraveSearch, SearxngSearch
from caligula.application.ports.sources import SearchResult


def test_searxng_uses_json_api_and_keeps_k_results():
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json={"results": [
            {"url": "https://a.example/1", "title": "Marché <b>2026-017</b>", "content": "attribué"},
            {"url": "https://a.example/2", "title": "Deux", "content": ""},
            {"title": "no url"},
        ]})

    search = SearxngSearch("https://searx.local/", httpx.Client(transport=httpx.MockTransport(handler)))
    hits = search.search("marché 2026-017", k=1, language="fr")
    assert hits == [SearchResult("https://a.example/1", "Marché 2026-017", "attribué")]
    assert seen[0].path == "/search" and seen[0].params["format"] == "json" and seen[0].params["language"] == "fr"


def test_brave_sends_token_and_reads_web_results():
    def handler(request):
        assert request.headers["X-Subscription-Token"] == "key"
        assert request.url.params["search_lang"] == "en"
        return httpx.Response(200, json={"web": {"results": [
            {"url": "https://b.example", "title": "STEG", "description": "<strong>outage</strong> report"}]}})

    search = BraveSearch("key", httpx.Client(transport=httpx.MockTransport(handler)))
    assert search.search("STEG outage", language="en") == [
        SearchResult("https://b.example", "STEG", "outage report")]
