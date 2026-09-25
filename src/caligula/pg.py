"""PostgreSQL + pgvector implementation of `EvidenceStore`."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from importlib.resources import files

import psycopg
from psycopg.rows import dict_row

from caligula.models import Document, SourceKind
from caligula.retrieval import Embedder, SearchHit, rrf, snippet
from caligula.store import BlobStore, EvidenceStore

_COLUMNS = (
    "id, canonical_url, url, source_kind, publisher, title, published_at, observed_at, "
    "raw_sha256, text_sha256, text, extraction, cites, derived_from"
)
_CANDIDATES = 50


def _vec(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


class PostgresEvidenceStore(EvidenceStore):
    def __init__(self, dsn: str, blobs: BlobStore, embedder: Embedder | None = None):
        super().__init__(blobs, embedder)
        self.conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)

    def init_schema(self) -> None:
        self.conn.execute(files("caligula").joinpath("schema.sql").read_text())

    def _insert(self, doc: Document) -> None:
        self.conn.execute(
            f"INSERT INTO documents ({_COLUMNS}, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)",
            (
                doc.id, doc.canonical_url, doc.url, doc.source_kind.value, doc.publisher, doc.title,
                doc.published_at, doc.observed_at, doc.raw_sha256, doc.text_sha256, doc.text,
                doc.extraction, doc.cites, doc.derived_from, _vec(self.embedder.embed(f"{doc.title} {doc.text}")),
            ),
        )

    def _rows(self, where: str = "TRUE", params: tuple = ()) -> list[Document]:
        rows = self.conn.execute(f"SELECT {_COLUMNS} FROM documents WHERE {where}", params).fetchall()
        return [Document.model_validate(r) for r in rows]

    def get(self, doc_id: str) -> Document | None:
        found = self._rows("id = %s", (doc_id,))
        return found[0] if found else None

    @property
    def documents(self) -> Mapping[str, Document]:
        return {d.id: d for d in self._rows()}

    def versions(self, canonical_url: str) -> list[Document]:
        return sorted(self._rows("canonical_url = %s", (canonical_url,)), key=lambda d: d.observed_at)

    def canonical_urls(self) -> list[str]:
        return [r["canonical_url"] for r in self.conn.execute("SELECT DISTINCT canonical_url FROM documents")]

    def search(
        self,
        query: str,
        k: int = 10,
        kinds: list[SourceKind] | None = None,
        observed_after: datetime | None = None,
        observed_before: datetime | None = None,
    ) -> list[SearchHit]:
        filters = "(%(kinds)s::text[] IS NULL OR source_kind = ANY(%(kinds)s)) " \
                  "AND (%(after)s::timestamptz IS NULL OR observed_at >= %(after)s) " \
                  "AND (%(before)s::timestamptz IS NULL OR observed_at <= %(before)s)"
        params = {
            "q": query,
            "kinds": [k_.value for k_ in kinds] if kinds else None,
            "after": observed_after,
            "before": observed_before,
            "vec": _vec(self.embedder.embed(query)),
            "n": _CANDIDATES,
        }
        # OR-ed terms: a lexical hit on any query token counts, ranked by ts_rank.
        lexical = self.conn.execute(
            f"""SELECT id FROM documents,
                   to_tsquery('simple', array_to_string(ARRAY(
                       SELECT quote_literal(t) FROM unnest(tsvector_to_array(to_tsvector('simple', %(q)s))) t
                   ), ' | ')) q
                WHERE tsv @@ q AND {filters}
                ORDER BY ts_rank(tsv, q) DESC LIMIT %(n)s""",
            params,
        ).fetchall()
        semantic = self.conn.execute(
            f"""SELECT id FROM documents WHERE {filters}
                AND 1 - (embedding <=> %(vec)s::vector) > 0
                ORDER BY embedding <=> %(vec)s::vector LIMIT %(n)s""",
            params,
        ).fetchall()
        fused = rrf([[r["id"] for r in lexical], [r["id"] for r in semantic]])
        top = sorted(fused, key=fused.get, reverse=True)[:k]
        docs = {d.id: d for d in self._rows("id = ANY(%s)", (top,))} if top else {}
        return [SearchHit(doc_id=i, score=round(fused[i], 5), snippet=snippet(docs[i].text, query)) for i in top]

    def save_investigation(self, inv_id: str, mode: str, allegation: dict, verdict: dict | None, trace: list) -> None:
        self.conn.execute(
            """INSERT INTO investigations (id, mode, allegation, verdict, trace)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET verdict = EXCLUDED.verdict, trace = EXCLUDED.trace, updated_at = now()""",
            (inv_id, mode, json.dumps(allegation), json.dumps(verdict) if verdict else None, json.dumps(trace)),
        )
