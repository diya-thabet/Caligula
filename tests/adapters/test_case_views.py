"""The JSON views the web interface reads, on the offline case and on a scripted live one."""

import json

from caligula.adapters.fixtures.case_directory import case_workspace
from caligula.adapters.presenters import case_views as views
from caligula.application.cases.service import CaseService
from conftest import FIXTURE
from support import scripted_cases

CLAIM = "Le marché 2026-017 a été attribué sans appel d'offres."


def offline(store, review=None):
    service = CaseService(None, new_ledger=lambda case_id: None)
    return service.add_reviewed(case_workspace(FIXTURE, store), CLAIM, by="replay", review=review)


def test_every_view_is_plain_json(store):
    case = offline(store, review="The award was made by direct agreement [E13].")
    for view in (views.overview, views.plan, views.claims, views.evidence, views.documents, views.timeline,
                 views.suspicions, views.audit, views.summary):
        json.dumps(view(case))  # serialisable as is


def test_the_header_and_what_waits_for_a_person(store):
    o = views.overview(offline(store))
    assert (o["status"], o["assessment"]["verdict"], o["assessment"]["confidence"]) == (
        "in_review", "high_suspicion", "moderate")
    assert o["assessment"]["likelihood_term"] == "very likely" and o["assessment"]["final"]
    assert o["pending_approvals"] == [{"kind": "sign_off", "role": "editor", "about": "case file ready for review"}]
    assert o["counts"]["evidence"] == 23 and o["parties"][0]["name"] == "STEG"


def test_claim_cards_carry_their_judgment_and_evidence_ids(store):
    c = views.claims(offline(store))
    c5 = next(s for s in c["subclaims"] if s["id"] == "C5")
    assert (c5["status"], c5["likelihood_term"], c5["confidence"]) == ("supported", "almost certain", "moderate")
    assert c5["evidence"] == {"supports": ["E13", "E14", "E15"], "contradicts": [], "qualifies": ["E16"]}
    assert c5["confidence_reasons"] == ["C5 supported but never challenged"]
    h4 = next(h for h in c["hypotheses"] if h["id"] == "H4")
    assert (h4["kind"], h4["status"], h4["untested"]) == ("innocent", "falsified", False)
    assert c["ruled_out"][0]["explanation_id"] == "sole_supplier"


def test_evidence_opens_on_its_exact_quote_and_source(store):
    items = {i["evidence_id"]: i for i in views.evidence(offline(store))["items"]}
    e16 = items["E16"]
    assert (e16["type"], e16["relation"], e16["publisher_interest"]) == ("quote", "qualifies", "self_serving")
    assert e16["source"]["reliability"] == "live official page (editable by its publisher)"
    assert e16["weight"] == 0.25  # official live 0.5, halved: the party speaks in its own favour
    assert items["E23"]["type"] == "absence" and items["E23"]["register"] == "jort"
    assert items["E20"]["used_by_financial_check"] is False  # the rewritten amount


def test_documents_show_their_chain_of_custody(store):
    case = offline(store)
    doc = views.document(case, "jort_award_v2")
    assert doc["custody"]["bytes_intact"] and len(doc["custody"]["raw_sha256"]) == 64
    assert doc["used_by"] == ["E20"] and doc["highlights"] == [
        {"evidence_id": "E20", "quote": "pour un montant de 80 000 000 TND"}]
    assert "80 000 000" in doc["text"] and views.document(case, "nope") is None


def test_the_timeline_flags_rewritten_records(store):
    events = views.timeline(offline(store))["events"]
    assert events == sorted(events, key=lambda e: (e["date"], e["type"], e["text"]))
    [rewrite] = [e for e in events if e["type"] == "rewrite"]
    assert rewrite["text"] == "amount_tnd ['120000000'] → ['80000000']"


def test_the_summary_view_shows_what_was_removed_and_why(store):
    s = views.summary(offline(store, review="It was made by direct agreement [E13]. Karim Ben Salah signed [E13]."))
    assert s["published"] == "It was made by direct agreement [E13]."
    assert [x["status"] for x in s["sentences"]] == ["unjudged", "unsupported"]


def test_a_live_case_waiting_for_plan_approval(store):
    service, _ = scripted_cases(store)
    case = service.open(CLAIM, by="Amira", case_id="C-9")
    o = views.overview(case)
    assert o["status"] == "awaiting_plan_approval" and o["assessment"]["final"] is False
    assert [a["kind"] for a in o["pending_approvals"]] == ["plan_approval"]
    p = views.plan(case)
    assert p["editable"] and p["tasks"][0]["objective"] == "Find the award notice"
    audit = views.audit(case, action="case_opened")
    assert audit["integrity"]["intact"] and [e["actor"] for e in audit["entries"]] == ["Amira"]
