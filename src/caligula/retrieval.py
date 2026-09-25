"""Hybrid retrieval: lexical (BM25) + semantic (vector) fused by reciprocal rank.

Lexical search is what finds an exact decree or market number; vector search
finds paraphrases. Neither is allowed to decide relevance alone: "resigned" and
"denies resigning" are close in vector space, which is why the reading step
and quote validation come after retrieval.

`HashingEmbedder` is a dependency-free baseline (character n-gram hashing) that
works across French, Arabic and transliterations. Swap in a neural embedder
behind the same `Embedder` protocol when one is chosen.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from caligula.domain.services.text import normalize_text

_TOKEN = re.compile(r"[\w؀-ۿ]+(?:[-/]\w+)*")
RRF_K = 60


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(normalize_text(text))


@dataclass(frozen=True)
class SearchHit:
    doc_id: str
    score: float
    snippet: str


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    def __init__(self, dim: int = 256, n: int = 3):
        self.dim, self.n = dim, n

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in tokenize(text):
            padded = f" {token} "
            for i in range(max(1, len(padded) - self.n + 1)):
                h = int.from_bytes(hashlib.blake2b(padded[i : i + self.n].encode(), digest_size=4).digest())
                vec[h % self.dim] += 1.0 if h & 1 << 31 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class BM25:
    def __init__(self, docs: dict[str, str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = {doc_id: Counter(tokenize(text)) for doc_id, text in docs.items()}
        self.len = {doc_id: sum(tf.values()) for doc_id, tf in self.tf.items()}
        self.avg = sum(self.len.values()) / max(1, len(self.len))
        df = Counter(t for tf in self.tf.values() for t in tf)
        n = len(self.tf)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> dict[str, float]:
        terms = tokenize(query)
        out = {}
        for doc_id, tf in self.tf.items():
            s = 0.0
            for t in terms:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[doc_id] / self.avg))
            if s > 0:
                out[doc_id] = s
        return out


def rrf(rankings: Iterable[list[str]], k: int = RRF_K) -> dict[str, float]:
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return fused


def snippet(text: str, query: str, width: int = 240) -> str:
    """The window of `text` that shares the most query tokens."""
    terms = set(tokenize(query))
    words = text.split()
    if not words:
        return ""
    step = max(1, width // 8)
    best, best_hits = 0, -1
    for i in range(0, len(words), max(1, step // 2)):
        hits = sum(1 for w in words[i : i + step] if set(tokenize(w)) & terms)
        if hits > best_hits:
            best, best_hits = i, hits
    return " ".join(words[best : best + step])[:width]
