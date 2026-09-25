"""Evidence store.

`BlobStore` is content-addressed and write-once: a later "corrected" file can
never overwrite bytes we already hold, it can only be added next to them.
`EvidenceStore` is in-memory for V1; the Postgres + pgvector schema replaces it
in V2 without changing this interface.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from caligula.hashing import sha256_bytes, text_sha256
from caligula.models import Document, SourceKind


class BlobStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest

    def put(self, data: bytes) -> str:
        digest = sha256_bytes(data)
        path = self._path(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return digest

    def get(self, digest: str) -> bytes:
        return self._path(digest).read_bytes()

    def verify(self, digest: str) -> bool:
        path = self._path(digest)
        return path.exists() and sha256_bytes(path.read_bytes()) == digest


class EvidenceStore:
    def __init__(self, blobs: BlobStore):
        self.blobs = blobs
        self.documents: dict[str, Document] = {}
        self._by_canonical: dict[str, list[str]] = defaultdict(list)

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
    ) -> Document:
        if doc_id in self.documents:
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
            cites=cites or [],
            derived_from=derived_from or [],
        )
        self.documents[doc_id] = doc
        self._by_canonical[canonical_url].append(doc_id)
        return doc

    def get(self, doc_id: str) -> Document | None:
        return self.documents.get(doc_id)

    def versions(self, canonical_url: str) -> list[Document]:
        """All stored versions of one logical document, oldest observation first."""
        docs = [self.documents[i] for i in self._by_canonical[canonical_url]]
        return sorted(docs, key=lambda d: d.observed_at)

    def canonical_urls(self) -> list[str]:
        return list(self._by_canonical)
