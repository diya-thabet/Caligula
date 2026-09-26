"""The HTTP API, end to end through FastAPI's test client, on scripted agents."""

import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from caligula.adapters.api.app import USER_HEADER, create_app
from caligula.adapters.fixtures.case_directory import case_workspace
from caligula.application.cases.service import CaseService
from conftest import FIXTURE
from support import scripted_cases

CLAIM = "Le marché 2026-017 a été attribué sans appel d'offres."
AMIRA = {USER_HEADER: "Amira (investigator)"}


def live(store, scripts=None):
    service, record = scripted_cases(store, scripts)
    return TestClient(create_app(service)), service


def test_a_case_from_claim_to_sign_off(store):
    scripts = {}
    client, service = live(store, scripts)
    r = client.post("/api/cases", json={"claim": CLAIM, "case_id": "C-1"}, headers=AMIRA)
    assert r.status_code == 202 and r.json()["status"] == "awaiting_plan_approval"
    [waiting] = client.get("/api/approvals").json()
    assert (waiting["case_id"], waiting["kind"], waiting["role"]) == ("C-1", "plan_approval", "investigator")

    plan = client.get("/api/cases/C-1/plan").json()
    assert plan["editable"] and plan["tasks"]
    edited = client.put("/api/cases/C-1/plan", headers=AMIRA, json={"tasks": [
        {"specialist": "official", "objective": "Award notice and its archived versions", "subclaim_ids": ["C3"],
         "purpose": "support", "queries": ["marché 2026-017"], "urls": []}]}).json()
    assert edited["tasks"][0]["objective"] == "Award notice and its archived versions"

    ws = lambda: service.get("C-1").workspace
    scripts[("official", 1)] = [("record_evidence", {"doc_id": "jort_award_v1", "subclaim_id": "C3",
                                                     "relation": "supports", "quote": "extension de 450 MW",
                                                     "rationale": "r"}),
                                ("report", {"summary": "found"})]
    scripts[("reviewer", 1)] = [
        ("__expand__", lambda: [("review_proposal", {"proposal_id": p.id, "decision": "accept", "note": "ok"})
                                for p in ws().proposals if p.status == "pending"]),
        ("complete_review", {"summary": "The award concerned a 450 MW extension [E1]."})]
    assert client.post("/api/cases/C-1/plan/approve", headers=AMIRA).status_code == 202
    header = client.get("/api/cases/C-1").json()
    assert header["status"] == "in_review" and header["stop_reason"] == "round_limit"

    claims = client.get("/api/cases/C-1/claims").json()
    assert next(c for c in claims["subclaims"] if c["id"] == "C3")["evidence"]["supports"] == ["E1"]
    [item] = client.get("/api/cases/C-1/evidence").json()["items"]
    assert (item["evidence_id"], item["proposal_id"], item["status"]) == ("E1", "P1", "accepted")
    assert client.get("/api/cases/C-1/summary").json()["published"] == "The award concerned a 450 MW extension [E1]."
    report = client.get("/api/cases/C-1/report")
    assert report.headers["content-type"].startswith("text/markdown") and "## Bottom line" in report.text

    signed = client.post("/api/cases/C-1/sign-off", headers={USER_HEADER: "Sonia (editor)"},
                         json={"note": "checked"}).json()
    assert signed["status"] == "approved" and signed["sign_off"]["by"] == "Sonia (editor)"
    audit = client.get("/api/cases/C-1/audit", params={"action": "sign_off"}).json()
    assert audit["integrity"]["intact"] and audit["entries"][0]["actor"] == "Sonia (editor)"


def test_errors_say_what_is_wrong(store):
    client, _ = live(store)
    assert client.post("/api/cases", json={"claim": CLAIM}).status_code == 401  # nobody said who acts
    assert client.get("/api/cases/nope").status_code == 404
    client.post("/api/cases", json={"claim": CLAIM, "case_id": "C-2"}, headers=AMIRA)
    r = client.post("/api/cases/C-2/sign-off", headers=AMIRA, json={})
    assert r.status_code == 409 and "not in_review" in r.json()["detail"]
    assert client.post("/api/cases", json={"claim": ""}, headers=AMIRA).status_code == 422
    assert client.get("/api/cases/C-2/documents/nope").status_code == 404


def test_refused_claims_and_legal_review(store):
    client, _ = live(store)
    refused = client.post("/api/cases", json={"claim": "The minister is a spy."}, headers=AMIRA).json()
    assert refused["status"] == "refused"
    held = client.post("/api/cases", json={"claim": "Money went offshore.", "poc": False, "case_id": "C-3"},
                       headers=AMIRA).json()
    assert held["pending_approvals"][0]["kind"] == "legal_review"
    approved = client.post("/api/cases/C-3/legal-approval", headers={USER_HEADER: quote("Maître Fictive")},
                           json={"note": "public contract"}).json()
    assert approved["status"] == "awaiting_plan_approval"
    entries = client.get("/api/cases/C-3/audit", params={"action": "legal_approval"}).json()["entries"]
    assert [e["actor"] for e in entries] == ["Maître Fictive"]  # names travel URL-encoded


def test_events_can_be_polled_or_streamed(store):
    client, _ = live(store)
    client.post("/api/cases", json={"claim": CLAIM, "case_id": "C-4"}, headers=AMIRA)
    polled = client.get("/api/cases/C-4/events").json()
    assert polled[0]["kind"] == "audit" and polled[0]["data"]["action"] == "case_opened"
    assert [e["seq"] for e in client.get("/api/cases/C-4/events", params={"after": 2}).json()][0] == 3

    with client.stream("GET", "/api/cases/C-4/events/stream", params={"idle": 0.05}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    frames = [f for f in body.split("\n\n") if f.startswith("id: ")]
    assert len(frames) == len(polled)
    first = json.loads(frames[0].split("data: ", 1)[1])
    assert first == polled[0]
    # A reconnecting client resumes after the last event it saw.
    with client.stream("GET", "/api/cases/C-4/events/stream", params={"idle": 0.05},
                       headers={"Last-Event-ID": str(len(polled) - 1)}) as r:
        assert "".join(r.iter_text()).count("id: ") == 1


def test_without_a_model_the_api_serves_imported_cases(store):
    service = CaseService(None, new_ledger=lambda case_id: None)
    service.add_reviewed(case_workspace(FIXTURE, store), CLAIM, by="replay")
    client = TestClient(create_app(service, cors_origins=["http://localhost:5173"]))
    assert client.get("/api/health").json() == {"status": "ok", "can_investigate": False, "cases": 1}
    [case] = client.get("/api/cases").json()
    assert case["assessment"]["verdict"] == "high_suspicion"
    r = client.post("/api/cases", json={"claim": CLAIM}, headers=AMIRA)
    assert r.status_code == 409 and "no model" in r.json()["detail"]
    r = client.options("/api/cases", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize("path", ["claims", "evidence", "documents", "timeline", "suspicions", "audit", "summary",
                                  "report", "plan"])
def test_every_surface_answers_on_an_imported_case(store, path):
    service = CaseService(None, new_ledger=lambda case_id: None)
    case = service.add_reviewed(case_workspace(FIXTURE, store), CLAIM, by="replay")
    assert TestClient(create_app(service)).get(f"/api/cases/{case.id}/{path}").status_code == 200
