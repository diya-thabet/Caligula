"""Evidence store: turns captured bytes into hashed documents.

It is the only way documents enter a repository, so every document carries
the SHA-256 of the exact bytes captured (kept in blob storage) and of its
normalized text. Storage itself is behind the `DocumentRepository` and
`BlobStorage` ports.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from caligula.application.ports.storage import BlobStorage, DocumentRepository, SearchHit
from caligula.domain.model.documents import Corpus, Document, SourceKind
from caligula.domain.services.text import text_sha256


class EvidenceStore:
    def __init__(self, repository: DocumentRepository, blobs: BlobStorage):
        self.repository = repository
        self.blobs = blobs

    def add(
        self,
        *,
        doc_id: str,
        raw: bytes,
        text: str,
        canonical_url: str,
        url: str,
        source_kind: SourceKind,
        publisher: str,
        observed_at: datetime,
        title: str = "",
        published_at: datetime | None = None,
        cites: list[str] | None = None,
        derived_from: list[str] | None = None,
        extraction: str = "plain",
    ) -> Document:
        if self.repository.get(doc_id) is not None:
            raise ValueError(f"document {doc_id!r} already stored; add a new version instead")
        doc = Document(
            id=doc_id,
            canonical_url=canonical_url,
            url=url,
            source_kind=source_kind,
            publisher=publisher,
            title=title,
            published_at=published_at,
            observed_at=observed_at,
            raw_sha256=self.blobs.put(raw),
            text_sha256=text_sha256(text),
            text=text,
            extraction=extraction,
            cites=cites or [],
            derived_from=derived_from or [],
        )
        self.repository.add(doc)
        return doc

    def get(self, doc_id: str) -> Document | None:
        return self.repository.get(doc_id)

    @property
    def documents(self) -> Mapping[str, Document]:
        return self.repository.documents

    def versions(self, canonical_url: str) -> list[Document]:
        return self.repository.versions(canonical_url)

    def canonical_urls(self) -> list[str]:
        return self.repository.canonical_urls()

    def search(
        self,
        query: str,
        k: int = 10,
        kinds: list[SourceKind] | None = None,
        observed_after: datetime | None = None,
        observed_before: datetime | None = None,
    ) -> list[SearchHit]:
        return self.repository.search(query, k, kinds, observed_after, observed_before)

    def corpus(self) -> Corpus:
        """Snapshot of the stored documents, with a blob-integrity check."""
        return Corpus(dict(self.repository.documents), lambda d: self.blobs.verify(d.raw_sha256))
