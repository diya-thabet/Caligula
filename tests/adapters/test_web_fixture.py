"""The data the interface's tests run on, taken from the real API on the synthetic case.

web/src/test/steg.json holds each view the interface reads. The interface's
tests use it as their fake server, so if a view changes shape this test fails
first: regenerate with `UPDATE_GOLDEN=1 pytest tests/adapters/test_web_fixture.py`,
then run the interface's tests (`cd web && npm test`).
"""

import json
import os
import re
from pathlib import Path

from fastapi.testclient import TestClient

from caligula.adapters.api.app import create_app
from caligula.adapters.fixtures.case_directory import case_workspace
from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.application.cases.service import CaseService
from conftest import FIXTURE
from support import scripted_cases

OUT = Path(__file__).parents[2] / "web" / "src" / "test" / "steg.json"
REVIEW = ("The award was made by direct agreement [E13]. It was worth 120 million TND [E19]. "
          "The contract was signed by Karim Ben Salah [E13]. More collection is needed on the price.")
PATHS = ["/health", "/cases", "/approvals", "/cases/{id}", "/cases/{id}/analysis", "/cases/{id}/claims",
         "/cases/{id}/evidence", "/cases/{id}/documents", "/cases/{id}/documents/jort_award_v1",
         "/cases/{id}/documents/jort_award_v1/versions", "/cases/{id}/documents/jort_award_v2/versions",
         "/cases/{id}/timeline", "/cases/{id}/suspicions",
         "/cases/{id}/audit", "/cases/{id}/summary", "/cases/{id}/history", "/cases/{id}/plan",
         "/cases/{id}/events"]


def _stable(text: str) -> str:
    """Mask what changes between runs: timestamps and hashes of the ledger."""
    text = re.sub(r'"(at|created_at|last_activity)": "[^"]+"', r'"\1": "2026-09-26T10:00:00+00:00"', text)
    return re.sub(r'"(hash|head)": "[0-9a-f]{64}"', r'"\1": "' + "0" * 64 + '"', text)


CLAIM = "Le marché 2026-017 a été attribué sans appel d'offres."
AMIRA = {"X-Caligula-User": "Amira"}


def live_cases(store) -> dict:
    """Cases at the other checkpoints, from the scripted service: a plan awaiting approval, a claim
    held for a lawyer, and a finished scripted run (for the activity tracker)."""
    scripts = {}
    service, _ = scripted_cases(store, scripts)
    client = TestClient(create_app(service))
    client.post("/api/cases", json={"claim": CLAIM, "case_id": "C-PLAN"}, headers=AMIRA)
    client.post("/api/cases", json={"claim": "Commissions went offshore.", "case_id": "C-LEGAL", "poc": False},
                headers=AMIRA)
    client.post("/api/cases", json={"claim": CLAIM, "case_id": "C-RAN"}, headers=AMIRA)
    ws = lambda: service.get("C-RAN").workspace
    scripts[("official", 1)] = [
        ("search_evidence", {"query": "marché 2026-017", "purpose": "support", "subclaim_id": "C3"}),
        ("record_evidence", {"doc_id": "jort_award_v1", "subclaim_id": "C3", "relation": "supports",
                             "quote": "extension de 450 MW", "rationale": "r"}),
        ("record_evidence", {"doc_id": "jort_award_v1", "subclaim_id": "C3", "relation": "supports",
                             "quote": "an invented sentence", "rationale": "r"}),
        ("report", {"summary": "award notice found"})]
    scripts[("reviewer", 1)] = [
        ("__expand__", lambda: [("review_proposal", {"proposal_id": p.id, "decision": "accept", "note": "ok"})
                                for p in ws().proposals if p.status == "pending"]),
        ("complete_review", {"summary": "The award concerned a 450 MW extension [E1]."})]
    client.post("/api/cases/C-RAN/plan/approve", headers=AMIRA)
    return {
        "C-PLAN": {p: client.get("/api/cases/C-PLAN" + p).json() for p in ("", "/plan")},
        "C-LEGAL": {p: client.get("/api/cases/C-LEGAL" + p).json() for p in ("", "/analysis")},
        "C-RAN": {p: client.get("/api/cases/C-RAN" + p).json() for p in ("", "/events", "/history", "/plan")},
    }


def build(store) -> str:
    service = CaseService(None, new_ledger=lambda case_id: JsonlLedger())
    ws = case_workspace(FIXTURE, store)
    case = service.add_reviewed(ws, ws.allegation.text, by="replay", review=REVIEW)
    client = TestClient(create_app(service))
    views = {p: client.get("/api" + p.replace("{id}", case.id)).json() for p in PATHS}
    data = {"case_id": case.id, "views": views, "live": live_cases(store)}
    return _stable(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True))


def test_the_interface_fixture_matches_the_api(store):
    data = build(store) + "\n"
    if os.environ.get("UPDATE_GOLDEN"):
        OUT.write_text(data, encoding="utf-8")
    assert OUT.read_text(encoding="utf-8") == data, "the API changed: regenerate web/src/test/steg.json"
