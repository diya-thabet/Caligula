"""Collapse documents that share an origin into independent clusters.

Five articles that all cite one leaked JORT page are one confirmation, not
five. Documents are joined when one cites or derives from another, when they
are versions of the same logical document, or when their normalized text is
identical (copy-paste republication).
"""

from __future__ import annotations

from collections.abc import Iterable

from caligula.store import EvidenceStore


class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)


def origin_clusters(store: EvidenceStore) -> dict[str, str]:
    """Map every document id to the id of its cluster representative."""
    uf = _UnionFind()
    by_text: dict[str, str] = {}
    by_url: dict[str, str] = {}
    for doc in store.documents.values():
        uf.find(doc.id)
        for other in doc.cites + doc.derived_from:
            if other in store.documents:
                uf.union(doc.id, other)
        for key, seen in ((doc.text_sha256, by_text), (doc.canonical_url, by_url)):
            if key in seen:
                uf.union(doc.id, seen[key])
            seen.setdefault(key, doc.id)
    return {doc_id: uf.find(doc_id) for doc_id in store.documents}


def group_by_cluster(doc_ids: Iterable[str], clusters: dict[str, str]) -> list[list[str]]:
    groups: dict[str, list[str]] = {}
    for doc_id in doc_ids:
        groups.setdefault(clusters[doc_id], []).append(doc_id)
    return [sorted(g) for g in groups.values()]
