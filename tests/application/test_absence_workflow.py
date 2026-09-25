"""A task that searches for an expected record and finds nothing becomes
scored absence evidence, reviewed like any other proposal."""

import json
import typing
from datetime import UTC, datetime

from caligula.application.investigation.toolkit import RegisterName, build_tools
from caligula.application.investigation.workspace import AgentContext
from caligula.domain.model.claims import ExpectedRecord
from caligula.domain.model.evidence import Relation
from caligula.domain.model.registers import REGISTERS
from support import workspace

NAMES = ["complete_task", "record_absence", "list_proposals", "review_proposal"]


def tools(ws, name):
    return {t.__name__: t for t in build_tools(ws, AgentContext(name=name, budget=20), NAMES)}


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
    out = tools(ws, "official")["complete_task"](task_id=task.id, outcome="not_found", note="TUNEPS search empty",
                                                 doc_ids=["tuneps_search"])
    assert "Absence recorded: Proposed as P1" in out

    reviewer = tools(ws, "reviewer")
    [row] = json.loads(reviewer["list_proposals"]())
    assert row["absence"]["register_id"] == "tuneps" and row["register_completeness"] == 0.8
    reviewer["review_proposal"](proposal_id="P1", decision="accept", note="search covered the award period")
    [item] = ws.verdict().weighed
    assert (item.kind, item.subclaim_id, item.weight, item.doc_id) == ("absence", "C5", 0.8, "tuneps_search")


def test_absence_that_cannot_be_checked_does_not_count(store):
    ws = workspace(store)
    expect_tender_notice(ws)
    ws.window = (None, datetime(2030, 1, 1, tzinfo=UTC))  # the search cannot cover the future
    task = ws.add_task(specialist="official", objective="Find the tender notice", expectation_id="C5.E1")
    out = tools(ws, "official")["complete_task"](task_id=task.id, outcome="not_found", note="nothing")
    assert "The absence does not count: Rejected: search made before the end of the window" in out
    assert task.status == "done" and ws.absences == []

    found = ws.add_task(specialist="official", objective="Find it again", expectation_id="C5.E1")
    assert "Absence" not in tools(ws, "official")["complete_task"](task_id=found.id, outcome="found", note="there")


def test_ad_hoc_absence_with_the_tool(store):
    ws = workspace(store)
    out = tools(ws, "investigator")["record_absence"](
        subclaim_id="C5", register_id="jort", relation="supports", query="décret procédure d'urgence 2026-0412")
    assert out == "Accepted."
    assert ws.verdict().weighed[0].weight == 0.425  # JORT 0.85, halved: no capture stored
