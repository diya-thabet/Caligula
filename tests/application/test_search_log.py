"""Every search is logged with who made it, when and for which task."""

from caligula.application.investigation.toolkit import build_tools
from caligula.application.investigation.workspace import AgentContext
from support import workspace


def tools(ws, name):
    return {t.__name__: t for t in build_tools(ws, AgentContext(name=name, budget=30), ["search_evidence"])}


def test_attempts_for_a_task(store):
    ws = workspace(store)
    task = ws.add_task(specialist="official", objective="find the tender notice", subclaim_ids=["C5"])
    search = tools(ws, "official")["search_evidence"]
    search(query="appel d'offres Rades-Fictive", purpose="support", task_id=task.id)
    search(query="Appel d'offres Rades-Fictive", purpose="support", task_id=task.id)  # same query: counted once
    search(query="tender notice 2026-017", purpose="support", subclaim_id="C5")  # untagged, on its sub-claim
    search(query="unrelated", purpose="explore", subclaim_id="C1")
    tools(ws, "web_news")["search_evidence"](query="other agent", purpose="support", task_id=task.id)
    assert [s.query for s in ws.attempts(task, "official")] == ["appel d'offres Rades-Fictive",
                                                                "tender notice 2026-017"]
    ws.round = 2  # untagged searches only count in the round they were made
    assert [s.query for s in ws.attempts(task, "official")] == ["appel d'offres Rades-Fictive"]
    s = ws.searches[0]
    assert (s.agent, s.round, s.task_id, s.tool) == ("official", 1, task.id, "search_evidence")
