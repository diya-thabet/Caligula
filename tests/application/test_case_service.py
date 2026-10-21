"""A case's lifecycle, with a person deciding at each checkpoint: intake, legal
review, plan approval (after edits), the run, scope decisions and sign-off."""

import threading

import pytest

from caligula.application.cases.service import CaseError, CaseService, CaseStatus, NotFound
from caligula.application.investigation.plan import PlannedTask
from support import assert_invariants, scripted_cases

CLAIM = "Le marché 2026-017 a été attribué sans appel d'offres et rien n'a été construit."


def official_collects():
    return [("record_evidence", {"doc_id": "jort_award_v1", "subclaim_id": "C3", "relation": "supports",
                                 "quote": "extension de 450 MW", "rationale": "r"}),
            ("report", {"summary": "award notice found"})]


def reviewer_accepts(service, case_id):
    ws = lambda: service.get(case_id).workspace
    return [("__expand__", lambda: [("review_proposal", {"proposal_id": p.id, "decision": "accept", "note": "ok"})
                                    for p in ws().proposals if p.status == "pending"]),
            ("complete_review", {"summary": "The award concerned a 450 MW extension [E1]."})]


def test_from_claim_to_signed_off_case_file(store):
    scripts = {}
    service, _ = scripted_cases(store, scripts)
    case = service.open(CLAIM, by="Amira (investigator)", case_id="C-1")
    # Intake accepted, claim decomposed, innocent explanations completed, plan drafted: now a person decides.
    assert case.status == CaseStatus.AWAITING_PLAN_APPROVAL
    assert case.added_by_code and [t.specialist for t in case.plan.tasks][0] == "official"
    with pytest.raises(CaseError, match="not in_review"):
        service.sign_off("C-1", by="Editor")

    scripts[("official", 1)] = official_collects()
    scripts[("reviewer", 1)] = reviewer_accepts(service, "C-1")
    service.approve_plan("C-1", by="Amira (investigator)")
    assert case.status == CaseStatus.IN_REVIEW and case.note == "round_limit"
    assert case.review == "The award concerned a 450 MW extension [E1]."
    assert case.result.attribution.published() == case.review

    service.sign_off("C-1", by="Sonia (editor)", note="checked against the annexes")
    assert case.status == CaseStatus.APPROVED and case.sign_off.by == "Sonia (editor)"
    actions = [(e.action, e.actor) for e in case.ledger.entries]
    for expected in [("case_opened", "Amira (investigator)"), ("intake", "caligula"),
                     ("plan_approved", "Amira (investigator)"), ("stop", "caligula"),
                     ("sign_off", "Sonia (editor)")]:
        assert expected in actions
    assert case.ledger.verify() is None
    # Everything was published as it happened, in order.
    kinds = [e.kind for e in case.events.since(0)]
    assert {"status", "phase", "tool", "audit"} <= set(kinds)
    statuses = [e.data["status"] for e in case.events.since(0) if e.kind == "status"]
    assert statuses == ["preparing", "awaiting_plan_approval", "running", "in_review", "approved"]
    assert_invariants(case.workspace, case.verdict)


def test_refused_and_legal_review_claims(store):
    service, _ = scripted_cases(store)
    refused = service.open("The director is a foreign spy.", by="a")
    assert refused.status == CaseStatus.REFUSED and refused.workspace is None
    held = service.open("Commissions were paid offshore on the 2026-017 contract.", by="a", poc=False)
    assert held.status == CaseStatus.AWAITING_LEGAL_REVIEW
    service.approve_legal(held.id, by="Maître Fictive")
    assert held.status == CaseStatus.AWAITING_PLAN_APPROVAL
    assert ("legal_approval", "Maître Fictive") in [(e.action, e.actor) for e in held.ledger.entries]
    with pytest.raises(NotFound):
        service.get("nope")


def test_an_edited_plan_is_checked_like_the_planner_s(store):
    service, _ = scripted_cases(store)
    case = service.open(CLAIM, by="a")
    only = PlannedTask(specialist="web_news", objective="press coverage of the award", subclaim_ids=["C3"],
                       purpose="support", queries=["Rades-Fictive"], urls=[])
    service.edit_plan(case.id, [only], by="Amira")
    tasks = case.plan.tasks
    assert tasks[0].objective == "press coverage of the award"
    # Code put back what the investigator removed but the engine requires.
    assert any(t.purpose == "challenge" for t in tasks) and case.plan.fixes
    assert [e.data["fixes"] for e in case.ledger.entries if e.action == "plan_edited"] == [case.plan.fixes]


def test_pause_resume_and_stop_a_running_case(store):
    gate = threading.Event()
    scripts = {}
    service, _ = scripted_cases(store, scripts, background=lambda work: threading.Thread(target=work).start())
    case = service.open(CLAIM, by="a", case_id="C-2")
    for _ in range(100):
        if case.status == CaseStatus.AWAITING_PLAN_APPROVAL:
            break
        threading.Event().wait(0.02)
    scripts[("official", 1)] = [("__expand__", lambda: gate.wait(2) and []),
                                ("search_evidence", {"query": "held", "purpose": "support", "subclaim_id": "C3"}),
                                ("report", {"summary": "x"})]
    service.approve_plan("C-2", by="a")
    service.pause("C-2", by="a")
    assert case.status == CaseStatus.PAUSED
    service.resume("C-2", by="a")
    service.pause("C-2", by="a")
    gate.set()  # the agent reaches its next tool call and waits there
    service.stop("C-2", by="a")
    for _ in range(100):
        if case.status == CaseStatus.IN_REVIEW:
            break
        threading.Event().wait(0.02)
    assert case.status == CaseStatus.IN_REVIEW and case.note == "stopped"
    actions = [e.action for e in case.ledger.entries]
    assert actions.count("paused") == 2 and "resumed" in actions and "stop_requested" in actions


def test_failures_are_kept_on_the_case(store):
    service, _ = scripted_cases(store)
    service.engine.analyst.plan = lambda allegation: 1 / 0
    case = service.open(CLAIM, by="a")
    assert case.status == CaseStatus.FAILED and "ZeroDivisionError" in case.note
    assert [e.kind for e in case.events.since(0)].count("error") == 1


def test_without_a_model_cases_can_only_be_imported(store):
    from caligula.adapters.fixtures.case_directory import case_workspace
    from conftest import FIXTURE

    service = CaseService(None, new_ledger=lambda case_id: None)
    with pytest.raises(CaseError, match="no model"):
        service.open(CLAIM, by="a")
    ws = case_workspace(FIXTURE, store)
    case = service.add_reviewed(ws, CLAIM, by="replay")
    assert case.status == CaseStatus.IN_REVIEW and case.verdict.verdict == "high_suspicion"
    assert service.list() == [case]
