"""Storage ports: documents, raw bytes, and the evidence ledger."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from caligula.domain.model.documents import Document, SourceKind
from caligula.domain.services.ledger_chain import Entry


@dataclass(frozen=True)
class SearchHit:
    doc_id: str
    score: float
    snippet: str


class DocumentRepository(Protocol):
    """Append-only store of documents. A changed page is a new document sharing
    the same canonical_url, never an update."""

    def add(self, doc: Document) -> None: ...

    def get(self, doc_id: str) -> Document | None: ...

    @property
    def documents(self) -> Mapping[str, Document]: ...

    def versions(self, canonical_url: str) -> list[Document]:
        """All versions of one logical document, oldest observation first."""
        ...

    def canonical_urls(self) -> list[str]: ...

    def search(
        self,
        query: str,
        k: int = 10,
        kinds: list[SourceKind] | None = None,
        observed_after: datetime | None = None,
        observed_before: datetime | None = None,
    ) -> list[SearchHit]: ...


class BlobStorage(Protocol):
    """Content-addressed, write-once storage of the exact bytes captured."""

    def put(self, data: bytes) -> str:
        """Store bytes; returns their SHA-256. Existing content is never overwritten."""
        ...

    def get(self, digest: str) -> bytes: ...

    def verify(self, digest: str) -> bool:
        """True if bytes with this digest are stored and still hash to it."""
        ...


class Ledger(Protocol):
    """Tamper-evident, append-only log of captures, proposals, decisions and approvals."""

    @property
    def entries(self) -> list[Entry]: ...

    @property
    def head(self) -> str: ...

    def append(self, action: str, actor: str, **data) -> Entry: ...

    def verify(self) -> int | None:
        """Index of the first broken entry, or None if the chain is intact."""
        ...
