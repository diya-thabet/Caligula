"""The investigation loop: suspicions drive new rounds; the case stops when it is
settled, exhausted, or a hard cap is hit, and says which."""

from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.application.investigation.plan import Plan, Task
from caligula.application.investigation.team import STOP_REASONS, InvestigationTeam, Specialist
from caligula.application.investigation.workspace import Mode, Workspace
from caligula.domain.model.claims import Allegation, SubClaim
from caligula.domain.model.documents import SourceKind
from caligula.domain.model.intake import ClaimType, Intake, SubjectType
from conftest import add_doc
from support import assert_invariants, scripted_team, workspace

COLLECT = ["list_tasks", "complete_task", "search_evidence", "record_evidence", "compare_versions", "report"]
TEAM = [Specialist("official", COLLECT, False), Specialist("web_news", COLLECT, False)]


def plan(*tasks: Task) -> Plan:
    return Plan(entities=[], window=(None, None), tasks=list(tasks), budgets={"official": 30, "web_news": 30})


def task(specialist, subclaims, objective="look", **kw):
    return Task(id="T0", specialist=specialist, objective=objective, subclaim_ids=subclaims, **kw)


def ev(doc, claim, quote, rel="supports"):
    return ("record_evidence", {"doc_id": doc, "subclaim_id": claim, "relation": rel, "quote": quote, "rationale": "r"})


def close_all(ws, agent, outcome="found"):
    def calls():
        out = []
        for t in ws.open_tasks(agent):
            if outcome == "not_found":
                out += [("search_evidence", {"query": f"{t.id} try {i}", "purpose": t.purpose, "task_id": t.id})
                        for i in range(3)]
            out.append(("complete_task", {"task_id": t.id, "outcome": outcome, "note": "n"}))
        return out
    return ("__expand__", calls)


def accept_all(ws):
    return ("__expand__", lambda: [("review_proposal", {"proposal_id": p.id, "decision": "accept", "note": "ok"})
                                   for p in ws.proposals if p.status == "pending"])


def suspect(statement, **kw):
    return ("raise_suspicion", {"statement": statement, "confirm_by": "archived versions of the award page",
                                "refute_by": "a published erratum", "confirm_specialist": "official",
                                "refute_specialist": "web_news"} | kw)


def done(summary="done"):
    return ("complete_review", {"summary": summary})


def test_a_suspicion_is_tested_in_the_next_round_and_resolved_by_the_evidence(store):
    ws = workspace(store)
    retcon = "The award amount was rewritten from 120M to 80M TND after the audit"
    scripts = {
        ("official", 1): [ev("jort_award_v1", "C3", "extension de 450 MW"), close_all(ws, "official"),
                          ("report", {"summary": "award found"})],
        ("reviewer", 1): [accept_all(ws), suspect(retcon), done("S1 raised")],
        # Round 2: the confirm task finds the earlier version; the refute task finds no erratum.
        ("official", 2): [("__expand__", lambda: [ev("jort_award_v1", ws.suspicions[0].subclaim_id,
                                                     "pour un montant de 120 000 000 TND")]),
                          close_all(ws, "official"), ("report", {"summary": "earlier version found"})],
        ("web_news", 2): [close_all(ws, "web_news", "not_found"), ("report", {"summary": "no erratum"})],
        ("reviewer", 2): [accept_all(ws), done("S1 confirmed")],
    }
    briefs = {}
    team = InvestigationTeam(runner=scripted_team(scripts, briefs=briefs), specialists=TEAM, web_search=False,
                             max_rounds=6)
    result = team.run(ws, plan=plan(task("official", ["C3"])))

    # The reviewer sees its suspicions; the specialists get the tasks that test them.
    assert '"id": "S1"' in briefs[("reviewer", 2)] and "Try to confirm suspicion S1" in briefs[("official", 2)]
    [s] = ws.suspicions
    assert (s.status, s.resolved_round) == ("confirmed", 2)
    assert result.rounds[0].suspicions_raised == ["S1"]
    assert result.rounds[1].suspicions_changed == {"S1": "confirmed"}
    # Both tests of S1 and the automatic challenge of C3 ran in round 2: nothing is left to do.
    assert result.stop_reason == "no_open_tasks" and len(result.rounds) == 2
    assert any(e.action == "stop" and e.data["reason"] == "no_open_tasks" for e in ws.ledger.entries)
    assert_invariants(ws, result.verdict)


def test_new_suspicions_keep_the_loop_going_up_to_the_hard_cap(store):
    ws = workspace(store)
    scripts = {("reviewer", n): [suspect(f"Suspicion number {n} about the award"), done()] for n in range(1, 9)}
    for n in range(1, 9):
        scripts[("official", n)] = [close_all(ws, "official", "not_found"), ("report", {"summary": "nothing"})]
        scripts[("web_news", n)] = [close_all(ws, "web_news", "not_found"), ("report", {"summary": "nothing"})]
    team = InvestigationTeam(runner=scripted_team(scripts), specialists=TEAM, web_search=False, max_rounds=4)
    result = team.run(ws, plan=plan(task("official", ["C3"])))
    # Nothing is ever found, but every review raises a new suspicion worth a round.
    assert result.stop_reason == "round_limit" and len(result.rounds) == 4
    assert [r.suspicions_raised for r in result.rounds] == [["S1"], ["S2"], ["S3"], ["S4"]]
    assert_invariants(ws, result.verdict)


def test_budget_cap_stops_the_loop(store):
    ws = workspace(store)
    scripts = {("official", 1): [ev("jort_award_v1", "C3", "extension de 450 MW"), close_all(ws, "official"),
                                 ("report", {"summary": "x"})],
               ("reviewer", 1): [accept_all(ws), suspect("A suspicion that would need another round"), done()]}
    team = InvestigationTeam(runner=scripted_team(scripts), specialists=TEAM, web_search=False, max_tool_calls=3)
    result = team.run(ws, plan=plan(task("official", ["C3"])))
    assert result.stop_reason == "budget" and len(result.rounds) == 1
    assert "budget" in STOP_REASONS["budget"]


def test_settled_case_stops_even_with_work_queued(store):
    add_doc(store, "mirror", "Le prêt finance le marché 2026-017.", kind=SourceKind.FOREIGN_MIRROR)
    add_doc(store, "audit", "Le marché 2026-017 a été financé.", kind=SourceKind.AUDIT)
    allegation = Allegation(id="A", text="Market 2026-017 was funded.", subject="s", claim_type="other",
                            subclaims=[SubClaim(id="C1", statement="market 2026-017 was funded")],
                            hypotheses=[], core_subclaims=["C1"])
    ws = Workspace(store=store, allegation=allegation, mode=Mode.INVESTIGATE, ledger=JsonlLedger())
    scripts = {
        ("official", 1): [ev("mirror", "C1", "Le prêt finance le marché 2026-017."),
                          ev("audit", "C1", "Le marché 2026-017 a été financé."),
                          ("search_evidence", {"query": "marché 2026-017 annulé", "purpose": "challenge",
                                               "subclaim_id": "C1"}),
                          close_all(ws, "official"), ("report", {"summary": "two independent records"})],
        ("reviewer", 1): [accept_all(ws), done()],
    }
    team = InvestigationTeam(runner=scripted_team(scripts), specialists=TEAM, web_search=False)
    result = team.run(ws, plan=plan(task("official", ["C1"]), task("web_news", ["C1"], "follow-up", round=2)))
    assert result.verdict.confidence == "high"
    assert result.stop_reason == "settled" and len(result.rounds) == 1
    assert ws.open_tasks() == [] and any(t.status == "open" for t in ws.tasks)  # queued work left undone
    assert_invariants(ws, result.verdict)


class RefusingAnalyst:
    """Classifies every statement as a suspicion about intentions (no documented act)."""

    def classify(self, text):
        return Intake(claim_type=ClaimType.OTHER, subject_types=[SubjectType.PRIVATE_INDIVIDUAL], public_nexus=True,
                      documented_act=False, relies_on_sensitive_traits=False,
                      involves_leaked_or_classified_material=False, rationale="about intentions")


def test_team_applies_the_legal_policy_to_suspicions_that_widen_the_case(store):
    ws = workspace(store)
    scripts = {("official", 1): [close_all(ws, "official"), ("report", {"summary": "x"})],
               ("reviewer", 1): [suspect("Karim Ben Fictif plans to move the money abroad",
                                         entities=["Karim Ben Fictif"]), done()]}
    team = InvestigationTeam(runner=scripted_team(scripts), analyst=RefusingAnalyst(), specialists=TEAM,
                             web_search=False, max_rounds=1)
    team.run(ws, plan=plan(task("official", ["C3"])))
    [s] = ws.suspicions
    assert s.status == "rejected" and not s.task_ids
    assert [e.data["decision"] for e in ws.ledger.entries if e.action == "scope_check"] == ["refuse"]
