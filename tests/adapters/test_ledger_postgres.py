"""The ledger in PostgreSQL: the same chain the JSON-lines ledger keeps.

The `at` column is text, not timestamptz, because it is an input to the entry hash.
These tests exist mainly to prove that round-tripping through the database does not
change any of the hashed values.
"""

import threading
from datetime import UTC, datetime

import pytest

from caligula.adapters.persistence.ledger_postgres import PostgresLedger
from caligula.domain.services.ledger_chain import GENESIS

DSN = pytest.importorskip("psycopg")
DSN_ENV = "CALIGULA_TEST_DSN"

pytestmark = pytest.mark.skipif(not __import__("os").environ.get(DSN_ENV),
                                reason="set CALIGULA_TEST_DSN for the Postgres tests")


@pytest.fixture
def conn():
    import psycopg
    from psycopg.rows import dict_row

    dsn = __import__("os").environ[DSN_ENV]
    connection = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
    connection.execute("DROP TABLE IF EXISTS case_ledger CASCADE")
    yield connection
    connection.execute("DROP TABLE IF EXISTS case_ledger CASCADE")
    connection.close()


@pytest.fixture
def schema(conn):
    from importlib.resources import files

    conn.execute(files("caligula.adapters.persistence").joinpath("schema.sql").read_text())
    return conn


def ledger(schema, case_id="C-1", clock=None):
    return PostgresLedger(case_id, lambda: schema, clock=clock or (lambda: datetime.now(UTC).isoformat()))


def test_an_empty_chain_has_no_head_but_the_genesis_hash(schema):
    empty = ledger(schema)
    assert empty.entries == [] and empty.verify() is None
    assert empty.head == GENESIS


def test_an_appended_chain_verifies_and_survives_a_reopen(schema):
    first = ledger(schema)
    entry = first.append("case_opened", "Amira", case_id="C-1", mode="investigate")
    assert entry.seq == 0 and entry.prev == GENESIS
    first.append("intake", "caligula", decision="accept", reasons=[])
    assert first.verify() is None

    reopened = ledger(schema)
    assert [e.seq for e in reopened.entries] == [0, 1]
    assert reopened.head == first.head
    assert reopened.verify() is None


def test_the_hashed_timestamp_comes_back_exactly_as_written(schema):
    """A timestamptz would fold "T" to a space and the chain would read as tampered."""
    stamp = "2026-10-07T05:19:03.250296+00:00"
    written = ledger(schema, clock=lambda: stamp).append("capture", "official", doc_id="news-1")
    stored = ledger(schema).entries[0]
    assert stored.at == stamp == written.at
    assert ledger(schema).verify() is None


def test_a_tampered_row_is_reported_with_its_index(schema):
    good = ledger(schema)
    good.append("capture", "official", doc_id="news-1")
    good.append("review", "reviewer", id="P1", status="accepted")
    schema.execute("DROP TRIGGER case_ledger_no_update ON case_ledger")
    schema.execute("UPDATE case_ledger SET data = %s::jsonb WHERE case_id = %s AND seq = 0",
                   ('{"doc_id": "news-forged"}', "C-1"))

    tampered = ledger(schema)
    assert tampered.verify() == 0


def test_data_survives_the_round_trip(schema):
    payload = {"quote": "gré à gré", "amount": 120000000.0, "seen": datetime(2026, 7, 21, tzinfo=UTC),
               "tags": ["a", "b"], "nested": {"x": [1, 2]}}
    ledger(schema).append("evidence", "official", **payload)
    stored = ledger(schema).entries[0].data
    assert stored["quote"] == "gré à gré"
    assert stored["amount"] == 120000000.0
    assert stored["seen"].startswith("2026-07-21")
    assert stored["nested"] == {"x": [1, 2]}
    assert ledger(schema).verify() is None


def test_the_past_cannot_be_edited(schema):
    chain = ledger(schema)
    chain.append("capture", "official", doc_id="news-1")
    with pytest.raises(DSN.errors.RaiseException):
        schema.execute("UPDATE case_ledger SET action = 'other' WHERE case_id = 'C-1'")
    with pytest.raises(DSN.errors.RaiseException):
        schema.execute("DELETE FROM case_ledger WHERE case_id = 'C-1'")


def test_chains_of_different_cases_do_not_interfere(schema):
    a, b = ledger(schema, "C-1"), ledger(schema, "C-2")
    a.append("case_opened", "Amira")
    b.append("case_opened", "Sonia")
    a.append("intake", "caligula", decision="accept")
    assert [e.action for e in ledger(schema, "C-1").entries] == ["case_opened", "intake"]
    assert [e.action for e in ledger(schema, "C-2").entries] == ["case_opened"]
    assert a.verify() is None and b.verify() is None


def test_concurrent_appends_keep_one_chain(schema):
    """Specialists append from several threads; the advisory lock keeps numbering whole."""
    shared = ledger(schema)
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for _ in range(10):
                shared.append("task", f"specialist-{n}", id=f"T{n}")
        except Exception as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    entries = ledger(schema).entries
    assert [e.seq for e in entries] == list(range(80))
    assert len({e.hash for e in entries}) == 80
    assert ledger(schema).verify() is None