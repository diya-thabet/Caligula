"""Documents and where they come from."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceKind(StrEnum):
    """Where a document came from. Trust is inverse to how easily the
    publisher can silently change it (see `scoring.SOURCE_WEIGHTS`)."""

    OFFICIAL_LIVE = "official_live"  # current ministry / JORT / TUNEPS page: mutable by the accused
    ARCHIVE = "archive"  # Wayback / archive.today / Common Crawl snapshot
    FOREIGN_MIRROR = "foreign_mirror"  # World Bank, EU TED, EBRD records of the same money
    AUDIT = "audit"  # Cour des comptes, IMF/EBRD reviews
    STATISTICS = "statistics"  # INS, grid operator datasets
    CONTRIBUTOR = "contributor"  # hashed upload from a field contributor
    OSINT = "osint"  # satellite, night lights, weather
    NEWS = "news"
    SOCIAL = "social"


class Document(BaseModel):
    id: str
    # Versions of the same logical document share a canonical_url
    # (e.g. the live JORT page and its Wayback snapshot).
    canonical_url: str
    url: str
    source_kind: SourceKind
    publisher: str
    title: str = ""
    published_at: datetime | None = None
    # When the content is attested to have existed: archive capture time,
    # contributor upload time, or our own first fetch.
    observed_at: datetime
    raw_sha256: str
    text_sha256: str
    text: str
    extraction: str = "plain"  # plain | pdf_text | ocr
    cites: list[str] = Field(default_factory=list)  # document ids this one cites
    derived_from: list[str] = Field(default_factory=list)  # document ids this one copies/rewrites
