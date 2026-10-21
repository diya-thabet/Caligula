"""A case survives a restart, exactly as it stood.

Every assertion here compares what the API returned before and after the service was
thrown away and rebuilt from PostgreSQL. If a restored case answers differently from
the live one, this file fails -- which is the point: a case that comes back subtly
different would quietly change what an investigator reads.
"""

import os
from importlib.resources import files

import pytest
from fastapi.testclient import TestClient

from caligula.adapters.api.app import create_app
from caligula.adapters.persistence.cases_pg import PostgresCaseRepository
from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.adapters.persistence.ledger_postgres import PostgresLedger
from caligula.adapters.persistence.postgres import PostgresDocumentRepository
from caligula.application.cases.service import CaseError, CaseService
from caligula.application.cases.snapshot import as_datetime
from caligula.application.evidence_store import EvidenceStore
from support import scripted_cases

pytestmark = pytest.mark.skipif(not os.environ.get("CALIGULA_TEST_DSN"),
                                reason="set CALIGULA_TEST_DSN for the Postgres tests")

CLAIM = "Le marché 2026-017 a été attribué sans appel d'offres et rien n'a été construit."
VIEWS = ("", "/claims", "/evidence", "/documents", "/suspicions", "/timeline",
         "/analysis", "/summary", "/history", "/audit")
VOLATILE = {"last_activity", "note"}


@pytest.fixture
def pg(tmp_path):
    import psycopg
    from psycopg.rows import dict_row

    dsn = os.environ["CALIGULA_TEST_DSN"]
    connection = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
    for table in ("custody_records", "case_ledger", "cases", "investigations", "documents"):
        connection.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    connection.execute(files("caligula.adapters.persistence").joinpath("schema.sql").read_text())
    yield connection
    connection.close()


@pytest.fixture
def blobs(tmp_path):
    from caligula.adapters.persistence.blob_fs import FileBlobStorage

    return FileBlobStorage(tmp_path / "blobs")


def make_store(pg, blobs) -> EvidenceStore:
    return EvidenceStore(PostgresDocumentRepository(os.environ["CALIGULA_TEST_DSN"]), blobs)


def make_repository(pg) -> PostgresCaseRepository:
    return PostgresCaseRepository(lambda: pg)


def new_ledger(pg):
    """One ledger object per case id, as the composition root does."""
    held: dict[str, PostgresLedger] = {}

    def factory(case_id: str) -> PostgresLedger:
        if case_id not in held:
            held[case_id] = PostgresLedger(case_id, lambda: pg)
        return held[case_id]

    return factory


def run_to_review(store, repository, pg, scripts=None):
    """Drive a scripted case from a claim to a signed-off case file."""
    scripts = {} if scripts is None else scripts
    service, _ = scripted_cases(store, scripts, repository=repository)
    service.new_ledger = new_ledger(pg)
    service.open(CLAIM, by="Amira (investigator)", case_id="C-1")

    scripts[("official", 1)] = [("record_evidence", {"doc_id": "jort_award_v1", "subclaim_id": "C1",
                                                    "relation": "supports", "quote": "450 MW",
                                                    "rationale": "the notice names the works"}),
                               ("report", {"summary": "award notice found"})]
    scripts[("reviewer", 1)] = _accept_all_then_summarise(service, "C-1",
                                                          "The award concerned a 450 MW extension [E1].")
    service.approve_plan("C-1", by="Amira (investigator)")
    service.sign_off("C-1", by="Sonia (editor)", note="checked against the annexes")
    return service


def _accept_all_then_summarise(service, case_id, summary):
    ws = lambda: service.get(case_id).workspace  # noqa: E731
    return [("__expand__", lambda: [("review_proposal", {"proposal_id": p.id, "decision": "accept",
                                                         "note": "ok"})
                                    for p in ws().proposals if p.status == "pending"]),
            ("complete_review", {"summary": summary})]


def _restored_service(pg, blobs, engine=True):
    """A second service over the same database: nothing replayed, only restored."""
    if engine:
        service, _ = scripted_cases(make_store(pg, blobs), {}, repository=make_repository(pg))
        service.cases.clear()
    else:
        service = CaseService(None, new_ledger=new_ledger(pg), repository=make_repository(pg))
    service.new_ledger = new_ledger(pg)
    service.hydrate(make_repository(pg).list(), make_store(pg, blobs))
    return service


def payloads(service, case_id="C-1"):
    client = TestClient(create_app(service))
    out = {view: client.get(f"/api/cases/{case_id}{view}").json() for view in VIEWS}
    out["/report"] = client.get(f"/api/cases/{case_id}/report").text
    return out


def without_volatile(body):
    if isinstance(body, dict):
        return {k: without_volatile(v) for k, v in body.items() if k not in VOLATILE}
    if isinstance(body, list):
        return [without_volatile(v) for v in body]
    return body


def test_a_signed_off_case_comes_back_identically(pg, blobs):
    store = make_store(pg, blobs)
    repository = make_repository(pg)
    before = run_to_review(store, repository, pg)

    # A new process: new store, new service, nothing replayed.
    restored_store = make_store(pg, blobs)
    after = CaseService(None, new_ledger=new_ledger(pg), repository=make_repository(pg))
    after.hydrate(make_repository(pg).list(), restored_store)

    assert [c.id for c in after.list()] == ["C-1"]
    case = after.get("C-1")
    assert case.status == before.get("C-1").status == after.get("C-1").status
    assert case.sign_off.by == "Sonia (editor)"
    assert case.restored is True

    live, back = payloads(before), payloads(after)
    for view in VIEWS:
        assert without_volatile(back[view]) == without_volatile(live[view]), f"{view} differs after restore"
    assert back["/report"] == live["/report"], "the case file changed across a restart"
    assert case.ledger.verify() is None


def test_evidence_ids_keep_their_meaning(pg, blobs):
    store = make_store(pg, blobs)
    run_to_review(store, make_repository(pg), pg)
    live_ids = list(make_store(pg, blobs).documents)  # documents untouched; ids are on the workspace

    after = CaseService(None, new_ledger=new_ledger(pg))
    after.hydrate(make_repository(pg).list(), make_store(pg, blobs))
    restored = after.get("C-1")
    stored = make_repository(pg).get("C-1")
    assert stored is not None
    stored_ids = [row["id"] for row in stored.workspace["evidence"]]
    assert stored_ids == sorted(stored_ids, key=lambda i: int(i[1:]))
    assert restored.workspace.counted().keys() == dict.fromkeys(stored_ids).keys()
    assert live_ids  # the corpus itself was never rebuilt


def test_the_stored_verdict_and_the_recomputed_one_agree(pg, blobs):
    store = make_store(pg, blobs)
    run_to_review(store, make_repository(pg), pg)
    stored = make_repository(pg).get("C-1")

    after = CaseService(None, new_ledger=new_ledger(pg))
    after.hydrate(make_repository(pg).list(), make_store(pg, blobs))
    recomputed = after.get("C-1").verdict

    assert stored.verdict["verdict"] == recomputed.verdict
    assert stored.verdict["confidence"] == recomputed.confidence
    assert [s["id"] for s in stored.verdict["by_subclaim"]] == [s.id for s in recomputed.by_subclaim]
    assert [s["status"] for s in stored.verdict["by_subclaim"]] == [s.status for s in recomputed.by_subclaim]


def test_an_id_already_in_storage_cannot_be_opened_again(pg, blobs):
    store = make_store(pg, blobs)
    run_to_review(store, make_repository(pg), pg)

    after = _restored_service(pg, blobs)
    with pytest.raises(CaseError, match="already exists"):
        after.open(CLAIM, by="Amira (investigator)", case_id="C-1")


def test_a_restored_case_refuses_to_change_its_record(pg, blobs):
    store = make_store(pg, blobs)
    run_to_review(store, make_repository(pg), pg)
    after = _restored_service(pg, blobs)

    for act in (lambda: after.sign_off("C-1", by="Sonia"),
                lambda: after.pause("C-1", by="Amira"),
                lambda: after.resume("C-1", by="Amira"),
                lambda: after.stop("C-1", by="Amira"),
                lambda: after.decide_scope("C-1", "S1", True, by="Amira")):
        with pytest.raises(CaseError, match="read-only"):
            act()


def test_a_run_interrupted_by_a_restart_is_recorded_as_failed(pg, blobs):
    store = make_store(pg, blobs)
    service, _ = scripted_cases(store, {}, repository=make_repository(pg))
    service.new_ledger = new_ledger(pg)
    service.open(CLAIM, by="Amira (investigator)", case_id="C-2")
    pg.execute("UPDATE cases SET status = 'running', note = '' WHERE id = 'C-2'")

    after = CaseService(None, new_ledger=new_ledger(pg))
    after.hydrate(make_repository(pg).list(), make_store(pg, blobs))
    case = after.get("C-2")
    assert case.status.value == "failed"
    assert "interrupted by a restart" in case.note
    assert [e.action for e in case.ledger.entries][-1] == "failure"


def test_one_unreadable_snapshot_does_not_stop_the_others(pg, blobs):
    store = make_store(pg, blobs)
    run_to_review(store, make_repository(pg), pg)
    pg.execute("INSERT INTO cases (id, claim, mode, poc, created_by, created_at, status, allegation) "
               "VALUES ('C-broken', 'x', 'investigate', true, 'Amira', now(), 'in_review', %s::jsonb)",
               ('{"not": "an allegation"}',))

    after = CaseService(None, new_ledger=new_ledger(pg))
    after.hydrate(make_repository(pg).list(), make_store(pg, blobs))
    assert after.get("C-1").status.value == "approved"
    broken = after.get("C-broken")
    assert broken.status.value == "failed"
    assert "could not be read" in broken.note


def test_restoring_twice_gives_the_same_answers(pg, blobs):
    store = make_store(pg, blobs)
    run_to_review(store, make_repository(pg), pg)
    repository = make_repository(pg)
    snapshots = repository.list()

    first = CaseService(None, new_ledger=new_ledger(pg))
    first.hydrate(snapshots, make_store(pg, blobs))
    second = CaseService(None, new_ledger=new_ledger(pg))
    second.hydrate(repository.list(), make_store(pg, blobs))

    assert payloads(first) == payloads(second)


def test_last_activity_is_the_moment_it_was_written(pg, blobs):
    store = make_store(pg, blobs)
    run_to_review(store, make_repository(pg), pg)
    written = make_repository(pg).get("C-1").updated_at

    after = CaseService(None, new_ledger=new_ledger(pg))
    after.hydrate(make_repository(pg).list(), make_store(pg, blobs))
    case = after.get("C-1")
    assert case.last_activity == as_datetime(written)
    assert case.events.last_at is not None


def test_with_no_repository_the_service_writes_nothing(pg, blobs):
    store = make_store(pg, blobs)
    service, _ = scripted_cases(store, {})
    service.open(CLAIM, by="Amira (investigator)", case_id="C-9")
    assert make_repository(pg).get("C-9") is None
    assert isinstance(service.new_ledger("C-9"), JsonlLedger)

def test_replaying_a_case_already_in_storage_leaves_the_stored_one(pg, blobs):
    """`serve --replay` runs on every start; hydration must win, not collide."""
    from caligula.adapters.fixtures.case_directory import case_workspace
    from conftest import FIXTURE

    store = make_store(pg, blobs)
    first = CaseService(None, new_ledger=new_ledger(pg), repository=make_repository(pg))
    replayed = case_workspace(FIXTURE, store)
    imported = first.add_reviewed(replayed, replayed.allegation.text, by="replay")

    # A second process: hydrates what was stored, then replays the same directory.
    after = CaseService(None, new_ledger=new_ledger(pg), repository=make_repository(pg))
    after.hydrate(make_repository(pg).list(), make_store(pg, blobs))
    restored = after.get(imported.id)
    assert restored.restored is True

    again = after.add_reviewed(case_workspace(FIXTURE, make_store(pg, blobs)), replayed.allegation.text, by="replay")
    assert again is restored
    assert [c.id for c in after.list()].count(imported.id) == 1


def test_a_replayed_case_keeps_its_recorded_chain_after_a_restart(pg, blobs):
    """A replay is re-offered on every start; the stored copy must not lose its audit."""
    from caligula.adapters.fixtures.case_directory import case_workspace
    from conftest import FIXTURE

    first = CaseService(None, new_ledger=new_ledger(pg), repository=make_repository(pg))
    ws = case_workspace(FIXTURE, make_store(pg, blobs))
    # What a replay offers is the fixture's own recorded chain, measured before the service
    # adds its `case_opened` entry on top of it.
    recorded = len(ws.ledger.entries)
    assert recorded > 0
    imported = first.add_reviewed(ws, ws.allegation.text, by="replay")
    assert len(imported.ledger.entries) == recorded + 1

    second = CaseService(None, new_ledger=new_ledger(pg), repository=make_repository(pg))
    second.hydrate(make_repository(pg).list(), make_store(pg, blobs))
    restored = second.get(imported.id)
    assert len(restored.ledger.entries) == 0  # hydrate alone does not invent history

    second.add_reviewed(case_workspace(FIXTURE, make_store(pg, blobs)), ws.allegation.text, by="replay")
    assert len(restored.ledger.entries) == recorded
    assert restored.ledger.verify() is None

    # A third start imports nothing more.
    third = CaseService(None, new_ledger=new_ledger(pg), repository=make_repository(pg))
    third.hydrate(make_repository(pg).list(), make_store(pg, blobs))
    third.add_reviewed(case_workspace(FIXTURE, make_store(pg, blobs)), ws.allegation.text, by="replay")
    assert len(third.get(imported.id).ledger.entries) == recorded
