"""Pause, resume and stop a running investigation; watch it through listeners."""

import threading
import time

from caligula.application.investigation.control import RunControl
from caligula.application.investigation.plan import Plan, Task
from caligula.application.investigation.team import STOP_REASONS, InvestigationTeam, Specialist
from support import assert_invariants, scripted_team, workspace

COLLECT = ["list_tasks", "complete_task", "search_evidence", "record_evidence", "report"]
TEAM = [Specialist("official", COLLECT, False)]
PLAN = Plan(entities=[], window=(None, None), budgets={"official": 30},
            tasks=[Task(id="T0", specialist="official", objective="award", subclaim_ids=["C3"])])


def search(query):
    return ("search_evidence", {"query": query, "purpose": "support", "subclaim_id": "C3"})


def test_control_states():
    c = RunControl()
    assert (c.paused, c.stopped, c.checkpoint()) == (False, False, True)
    c.pause()
    assert c.paused
    threading.Timer(0.05, c.resume).start()
    started = time.monotonic()
    assert c.checkpoint(poll=0.01) and time.monotonic() - started >= 0.04
    c.pause()
    threading.Timer(0.05, c.stop).start()
    assert c.checkpoint(poll=0.01) is False and c.stopped and not c.paused


def test_a_stop_ends_the_agents_turn_and_the_loop(store):
    ws = workspace(store)
    record = {}
    scripts = {("official", 1): [search("first"), ("__expand__", lambda: [ws.control.stop()] and []),
                                 search("after the stop"), ("report", {"summary": "partial work"})],
               ("reviewer", 1): [("complete_review", {"summary": "should not run"})]}
    team = InvestigationTeam(runner=scripted_team(scripts, record), specialists=TEAM, web_search=False)
    result = team.run(ws, plan=PLAN)
    calls = record[("official", 1)]
    assert [(name, err) for name, err, _ in calls] == [("search_evidence", False), ("search_evidence", True),
                                                       ("report", True)]
    assert "stopped the investigation" in calls[1][2]
    assert result.stop_reason == "stopped" and STOP_REASONS["stopped"] == "stopped by the investigator"
    assert ("reviewer", 1) not in record  # no review after a stop
    assert [e.data["reason"] for e in ws.ledger.entries if e.action == "stop"] == ["stopped"]
    assert_invariants(ws, result.verdict)


def test_a_pause_holds_the_next_tool_call_until_resumed(store):
    ws = workspace(store)
    waited = []

    def pause_then_resume_later():
        ws.control.pause()
        threading.Timer(0.1, ws.control.resume).start()
        waited.append(time.monotonic())
        return []

    scripts = {("official", 1): [("__expand__", pause_then_resume_later), search("held until resumed"),
                                 ("__expand__", lambda: waited.append(time.monotonic()) or []),
                                 ("__expand__", lambda: [("complete_task", {"task_id": t.id, "outcome": "partial",
                                                                            "note": "n"})
                                                         for t in ws.open_tasks("official")]),
                                 ("report", {"summary": "done"})],
               ("reviewer", 1): [("complete_review", {"summary": "More work is needed."})]}
    team = InvestigationTeam(runner=scripted_team(scripts), specialists=TEAM, web_search=False, max_rounds=1)
    result = team.run(ws, plan=PLAN)
    assert waited[1] - waited[0] >= 0.09 and result.stop_reason != "stopped"


def test_listeners_see_every_tool_call(store):
    seen = []
    ws = workspace(store, listeners=[lambda kind, data: seen.append((kind, data["agent"], data["tool"])),
                                     lambda kind, data: 1 / 0])  # a broken listener changes nothing
    scripts = {("official", 1): [search("q"), ("report", {"summary": "done"})]}
    InvestigationTeam(runner=scripted_team(scripts), specialists=TEAM, web_search=False, max_rounds=1).run(
        ws, plan=PLAN)
    assert ("tool", "official", "search_evidence") in seen
