"""In-memory `DocumentRepository`, for offline runs and tests."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime

from caligula.adapters.persistence.search import BM25, Embedder, HashingEmbedder, cosine, rrf, snippet
from caligula.application.ports.storage import SearchHit
from caligula.domain.model.documents import Document, SourceKind


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


class MemoryDocumentRepository:
    def __init__(self, embedder: Embedder | None = None):
        self.embedder = embedder or HashingEmbedder()
        self._docs: dict[str, Document] = {}
        self._by_canonical: dict[str, list[str]] = defaultdict(list)
        self._vectors: dict[str, list[float]] = {}

    def add(self, doc: Document) -> None:
        if doc.id in self._docs:
            raise ValueError(f"document {doc.id!r} already stored")
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

    def search(
        self,
        query: str,
        k: int = 10,
        kinds: list[SourceKind] | None = None,
        observed_after: datetime | None = None,
        observed_before: datetime | None = None,
    ) -> list[SearchHit]:
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
