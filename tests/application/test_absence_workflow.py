"""A task that searches for an expected record and finds nothing becomes
scored absence evidence, reviewed like any other proposal."""

import json
import typing
from datetime import UTC, datetime

import pytest

from caligula.adapters.presenters.markdown_report import build_report
from caligula.application.investigation.plan import PlanDraft, PlannedTask, normalize_plan
from caligula.application.investigation.toolkit import RegisterName, build_tools
from caligula.application.investigation.workspace import AgentContext
from caligula.application.ports.llm import ToolRefusal
from caligula.domain.model.claims import ExpectedRecord
from caligula.domain.model.evidence import Relation
from caligula.domain.model.registers import REGISTERS
from support import assert_invariants, workspace

NAMES = ["complete_task", "record_absence", "list_proposals", "review_proposal", "search_evidence"]


def tools(ws, name):
    return {t.__name__: t for t in build_tools(ws, AgentContext(name=name, budget=20), NAMES)}


def search_hard(agent_tools, task=None, subclaim="C5"):
    """Three different searches, as the persistence rule requires before "not found"."""
    for q in ("appel d'offres Rades-Fictive", "avis TUNEPS extension centrale", "tender notice 2026-017"):
        agent_tools["search_evidence"](query=q, purpose="support", subclaim_id=subclaim,
                                       task_id=task.id if task else None)


def expect_tender_notice(ws):
    c5 = next(c for c in ws.allegation.subclaims if c.id == "C5")
    c5.expected_records = [ExpectedRecord(description="TUNEPS tender notice for the Rades-Fictive extension",
                                          register_id="tuneps", absence_means=Relation.SUPPORTS)]


def test_register_literal_matches_catalogue():
    assert set(typing.get_args(RegisterName)) == set(REGISTERS)


def test_not_found_on_expected_record_is_proposed_as_absence(store):
    ws = workspace(store, review_required=True)
    expect_tender_notice(ws)
    ws.window = (datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 2, 15, tzinfo=UTC))
    task = ws.add_task(specialist="official", objective="Find the tender notice", subclaim_ids=["C5"],
                       queries=["extension centrale Rades-Fictive"], expectation_id="C5.E1")
    official = tools(ws, "official")
    search_hard(official, task)
    out = official["complete_task"](task_id=task.id, outcome="not_found", note="TUNEPS search empty",
                                    doc_ids=["tuneps_search"])
    assert "Absence recorded: Proposed as P1" in out

    reviewer = tools(ws, "reviewer")
    [row] = json.loads(reviewer["list_proposals"]())
    assert row["absence"]["register_id"] == "tuneps" and row["register_completeness"] == 0.8
    reviewer["review_proposal"](proposal_id="P1", decision="accept", note="search covered the award period")
    [item] = ws.verdict().weighed
    assert (item.kind, item.subclaim_id, item.weight, item.doc_id) == ("absence", "C5", 0.8, "tuneps_search")
    report = build_report(ws, ws.verdict())
    assert ("✓ **E1** absence (supports) · TUNEPS: public procurement notices and awards: nothing found for "
            "« extension centrale Rades-Fictive » (capture `tuneps_search`)") in report
    assert "| C5.E1 TUNEPS tender notice for the Rades-Fictive extension | tuneps | supports C5 | T1 not_found | yes |" \
        in report
    assert_invariants(ws)


def test_plan_searches_every_expected_record_once(store):
    ws = workspace(store)
    expect_tender_notice(ws)
    mine = PlannedTask(specialist="official", objective="TUNEPS notice", subclaim_ids=["C5"], purpose="support",
                       queries=["Rades-Fictive"], urls=[], expectation_id="C5.E1")
    bogus = mine.model_copy(update={"objective": "made up", "expectation_id": "C5.E9"})
    plan = normalize_plan(PlanDraft(entities=[], window_start=None, window_end=None, tasks=[mine, bogus],
                                    budget_weights=[]), ws.allegation, 50)
    assert [(t.objective, t.expectation_id) for t in plan.tasks if t.subclaim_ids == ["C5"]][:2] == [
        ("TUNEPS notice", "C5.E1"), ("made up", None)]
    assert not any("expected record C5.E1" in f for f in plan.fixes)


def test_absence_that_cannot_be_checked_does_not_count(store):
    ws = workspace(store)
    expect_tender_notice(ws)
    ws.window = (None, datetime(2030, 1, 1, tzinfo=UTC))  # the search cannot cover the future
    task = ws.add_task(specialist="official", objective="Find the tender notice", expectation_id="C5.E1")
    official = tools(ws, "official")
    search_hard(official, task)
    out = official["complete_task"](task_id=task.id, outcome="not_found", note="nothing")
    assert "The absence does not count: Rejected: search made before the end of the window" in out
    assert task.status == "done" and ws.absences == []

    found = ws.add_task(specialist="official", objective="Find it again", expectation_id="C5.E1")
    assert "Absence" not in tools(ws, "official")["complete_task"](task_id=found.id, outcome="found", note="there")


def test_ad_hoc_absence_with_the_tool(store):
    ws = workspace(store)
    agent = tools(ws, "investigator")
    search_hard(agent)
    out = agent["record_absence"](
        subclaim_id="C5", register_id="jort", relation="supports", query="décret procédure d'urgence 2026-0412")
    assert out == "Accepted as evidence E1."
    assert ws.verdict().weighed[0].weight == 0.425  # JORT 0.85, halved: no capture stored


def test_not_found_needs_several_searches(store):
    ws = workspace(store)
    task = ws.add_task(specialist="official", objective="Find the emergency decree", subclaim_ids=["C9"])
    official = tools(ws, "official")
    official["search_evidence"](query="décret 2026-0412", purpose="challenge", task_id=task.id)
    refused = official["complete_task"]
    with pytest.raises(ToolRefusal, match="1 different search"):
        refused(task_id=task.id, outcome="not_found", note="nothing in the JORT")
    assert task.status == "open"
    # Queries run with a search we cannot see (the provider's own) are declared, and count.
    out = refused(task_id=task.id, outcome="not_found", note="nothing in the JORT",
                  searched=["decree 2026-0412 emergency", "état d'urgence énergie 2026"])
    assert "closed (not_found)" in out
    assert [s.tool for s in ws.searches] == ["search_evidence", "declared", "declared"]
    with pytest.raises(ToolRefusal, match="0 different search"):
        official["record_absence"](subclaim_id="C4", register_id="jort", relation="supports", query="q")


def test_near_the_end_of_the_budget_not_found_is_accepted_but_flagged(store):
    ws = workspace(store)
    task = ws.add_task(specialist="official", objective="Find the decree", subclaim_ids=["C9"])
    agent = {t.__name__: t for t in build_tools(ws, AgentContext(name="official", budget=2), NAMES)}
    agent["complete_task"](task_id=task.id, outcome="not_found", note="nothing")
    assert task.note == "nothing [only 0 search(es): budget nearly spent]"
