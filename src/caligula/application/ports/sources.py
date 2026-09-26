"""Ports for the outside sources agents collect from, and for text extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True)
class Capture:
    """One archived capture of a URL."""

    timestamp: str  # yyyymmddhhmmss
    original: str
    digest: str  # the archive's own digest of the payload
    mimetype: str

    @property
    def captured_at(self) -> datetime:
        return datetime.strptime(self.timestamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


@dataclass(frozen=True)
class ArchivedCopy:
    url: str  # where the raw bytes were fetched from
    content: bytes
    captured_at: datetime


class ArchiveSource(Protocol):
    """Independent timestamped copies of web pages (e.g. the Wayback Machine)."""

    def captures(self, url: str, since: str | None = None, until: str | None = None) -> list[Capture]:
        """Captures of `url`, one per distinct payload, oldest first."""
        ...

    def fetch(self, original: str, timestamp: str) -> ArchivedCopy:
        """The raw bytes of one capture, as the site served them."""
        ...


@dataclass(frozen=True)
class Fetched:
    url: str
    content: bytes
    content_type: str


class WebFetcher(Protocol):
    """Fetches publicly accessible URLs as they are now."""

    def fetch(self, url: str) -> Fetched: ...


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str


class WebSearch(Protocol):
    """A web search engine. Results are leads: a page counts only once fetched and stored."""

    def search(self, query: str, k: int = 8, language: str | None = None) -> list[SearchResult]: ...


class FunderRecords(Protocol):
    """Lenders' project records: an independent record of public money."""

    def search(self, query: str, country_code: str = "TN", rows: int = 5) -> tuple[str, bytes, list[dict]]:
        """Returns (request URL, raw response bytes, parsed project records)."""
        ...


class PrivateSourceError(ValueError):
    """Raised for private groups, invite links or anything behind an access control."""


@dataclass(frozen=True)
class TelegramPost:
    channel: str
    post_id: int
    url: str
    posted_at: datetime | None
    text: str
    forwarded_from: str | None


class TelegramChannels(Protocol):
    """Public Telegram channels only."""

    def fetch(self, ref: str, before: int | None = None) -> tuple[str, bytes, list[TelegramPost]]:
        """Returns (page URL, raw page bytes, posts). Raises PrivateSourceError for private refs."""
        ...


@dataclass(frozen=True)
class ExtractedText:
    text: str
    method: str  # plain | pdf_text | ocr


class TextExtractor(Protocol):
    def extract(self, raw: bytes, filename: str = "") -> ExtractedText: ...
