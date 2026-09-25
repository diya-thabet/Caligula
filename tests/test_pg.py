"""Runs against a real PostgreSQL + pgvector when CALIGULA_TEST_DSN is set."""

import os

import psycopg
import pytest

from caligula.case import run_case
from caligula.models import SourceKind

from conftest import FIXTURE, add_doc

DSN = os.environ.get("CALIGULA_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="CALIGULA_TEST_DSN not set")


@pytest.fixture
def pg(blobs):
    from caligula.pg import PostgresEvidenceStore

    store = PostgresEvidenceStore(DSN, blobs)
    store.conn.execute("DROP TABLE IF EXISTS custody_records, investigations, documents CASCADE")
    store.init_schema()
    yield store
    store.conn.close()


def test_fixture_verdict_matches_memory_store(pg, store):
    assert run_case(FIXTURE, pg).model_dump() == run_case(FIXTURE, store).model_dump()


def test_documents_are_append_only(pg):
    add_doc(pg, "a", "montant 120 TND")
    with pytest.raises(psycopg.errors.RaiseException):
        pg.conn.execute("UPDATE documents SET text = 'montant 80 TND' WHERE id = 'a'")
    with pytest.raises(ValueError):
        add_doc(pg, "a", "again")


def test_hybrid_search_with_filters(pg):
    add_doc(pg, "award", "Marché n° 2026-017 attribué par gré à gré", kind=SourceKind.ARCHIVE, day=1)
    add_doc(pg, "other", "Rapport sur la pluviométrie", kind=SourceKind.OSINT, day=2)
    add_doc(pg, "late", "Marché n° 2026-017 : rectificatif", kind=SourceKind.OFFICIAL_LIVE, day=20)
    hits = pg.search("marché 2026-017", k=5)
    assert {h.doc_id for h in hits[:2]} == {"award", "late"}
    only_archive = pg.search("marché 2026-017", kinds=[SourceKind.ARCHIVE])
    assert [h.doc_id for h in only_archive] == ["award"]
    before = pg.search("marché 2026-017", observed_before=pg.get("other").observed_at)
    assert [h.doc_id for h in before] == ["award"]
