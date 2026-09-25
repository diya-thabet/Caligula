"""Evidence store.

`BlobStore` is content-addressed and write-once: a later "corrected" file can
never overwrite bytes we already hold, it can only be added next to them.
`EvidenceStore` is the interface the engine uses; `MemoryEvidenceStore` backs
offline runs and tests, `caligula.pg.PostgresEvidenceStore` backs deployments.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from caligula.domain.model.documents import Document, SourceKind
from caligula.domain.services.text import sha256_bytes, text_sha256
from caligula.retrieval import BM25, Embedder, HashingEmbedder, SearchHit, cosine, rrf, snippet


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


class EvidenceStore(ABC):
    def __init__(self, blobs: BlobStore, embedder: Embedder | None = None):
        self.blobs = blobs
        self.embedder = embedder or HashingEmbedder()

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
        if self.get(doc_id) is not None:
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
        self._insert(doc)
        return doc

    @abstractmethod
    def _insert(self, doc: Document) -> None: ...

    @abstractmethod
    def get(self, doc_id: str) -> Document | None: ...

    @property
    @abstractmethod
    def documents(self) -> Mapping[str, Document]: ...

    @abstractmethod
    def versions(self, canonical_url: str) -> list[Document]:
        """All stored versions of one logical document, oldest observation first."""

    @abstractmethod
    def canonical_urls(self) -> list[str]: ...

    @abstractmethod
    def search(
        self,
        query: str,
        k: int = 10,
        kinds: list[SourceKind] | None = None,
        observed_after: datetime | None = None,
        observed_before: datetime | None = None,
    ) -> list[SearchHit]: ...


def matches_filters(
    doc: Document,
    kinds: list[SourceKind] | None,
    observed_after: datetime | None,
    observed_before: datetime | None,
) -> bool:
    return (
        (not kinds or doc.source_kind in kinds)
        and (observed_after is None or doc.observed_at >= observed_after)
        and (observed_before is None or doc.observed_at <= observed_before)
    )


class MemoryEvidenceStore(EvidenceStore):
    def __init__(self, blobs: BlobStore, embedder: Embedder | None = None):
        super().__init__(blobs, embedder)
        self._docs: dict[str, Document] = {}
        self._by_canonical: dict[str, list[str]] = defaultdict(list)
        self._vectors: dict[str, list[float]] = {}

    def _insert(self, doc: Document) -> None:
        self._docs[doc.id] = doc
        self._by_canonical[doc.canonical_url].append(doc.id)
        self._vectors[doc.id] = self.embedder.embed(f"{doc.title} {doc.text}")

    def get(self, doc_id: str) -> Document | None:
        return self._docs.get(doc_id)

    @property
    def documents(self) -> Mapping[str, Document]:
        return self._docs

    def versions(self, canonical_url: str) -> list[Document]:
        docs = [self._docs[i] for i in self._by_canonical[canonical_url]]
        return sorted(docs, key=lambda d: d.observed_at)

    def canonical_urls(self) -> list[str]:
        return list(self._by_canonical)

    def search(self, query, k=10, kinds=None, observed_after=None, observed_before=None):
        pool = {
            d.id: f"{d.title} {d.text}"
            for d in self._docs.values()
            if matches_filters(d, kinds, observed_after, observed_before)
        }
        if not pool:
            return []
        lexical = BM25(pool).scores(query)
        qvec = self.embedder.embed(query)
        semantic = {doc_id: cosine(qvec, self._vectors[doc_id]) for doc_id in pool}
        fused = rrf([
            sorted(lexical, key=lexical.get, reverse=True),
            [d for d in sorted(semantic, key=semantic.get, reverse=True) if semantic[d] > 0],
        ])
        top = sorted(fused, key=fused.get, reverse=True)[:k]
        return [SearchHit(doc_id=d, score=round(fused[d], 5), snippet=snippet(self._docs[d].text, query)) for d in top]
