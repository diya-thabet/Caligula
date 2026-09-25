"""The investigation workflow with scripted stand-ins for Claude.

Checks the orchestration (plan, tasks, parallel rounds, review, automatic
challenges, stopping) and that code, not the model, decides what counts.
"""

import threading

from caligula.adapters.presenters.markdown_report import build_report
from caligula.adapters.presenters.public_reply import public_reply
from caligula.application.investigation.plan import (
    BudgetWeight,
    PlanDraft,
    PlannedTask,
    normalize_plan,
)
from caligula.application.investigation.prompts import SPECIALIST_FOCUS
from caligula.application.investigation.team import InvestigationTeam, Specialist
from caligula.application.investigation.workspace import Mode
from support import ScriptedAgentRunner, workspace

WS = {}


def ev(doc, claim, quote, rel="supports"):
    return ("record_evidence", {"doc_id": doc, "subclaim_id": claim, "relation": rel, "quote": quote, "rationale": "r"})


def amount(doc, role, value, quote):
    return ("record_amount", {"doc_id": doc, "role": role, "amount_tnd": value, "quote": quote})


def close_all(agent, outcome="found", note="done"):
    return ("__expand__", lambda: [("complete_task", {"task_id": t.id, "outcome": outcome, "note": note})
                                   for t in WS["ws"].open_tasks(agent)])


def review_all():
    """Reviewer policy for the test: repeats of the leak are disputed, the rest accepted."""
    return [
        ("review_proposal", {"proposal_id": p.id, "note": "repeats the JORT leak" if p.item.doc_id.startswith("news_") else "ok",
                             "decision": "dispute" if p.item.doc_id.startswith("news_") else "accept"})
        for p in WS["ws"].proposals if p.status == "pending"
    ]


SCRIPTS = {
    ("official", 1): [
        ("report", {"summary": "too early"}),  # refused: open tasks
        ("compare_versions", {"canonical_url": "https://jort.example.tn/2026/017"}),
        ev("jort_award_v1", "C3", "extension de 450 MW de la centrale de Rades-Fictive"),
        ev("jort_award_v1", "C5", "par procédure de gré à gré"),
        ev("tuneps_search", "C5", "Aucun avis d'appel d'offres publié"),
        amount("jort_award_v1", "allocated", 120e6, "120 000 000 TND"),
        amount("benchmark", "benchmark", 60e6, "60 000 000 TND"),
        ("post_lead", {"to": "web_news", "note": "JORT award 2026-017 was rewritten 120M -> 80M"}),
        ("post_lead", {"to": "reviewer", "note": "the operator invokes decree 2026-0412"}),
        close_all("official"),
        ("report", {"summary": "JORT award rewritten between [jort_award_v1] and [jort_award_v2]."}),
    ],
    ("funders_audit", 1): [
        ev("worldbank", "C3", "extension de capacité, centrale de Rades-Fictive"),
        ev("audit", "C5", "n'est pas justifié par une situation d'urgence documentée"),
        amount("worldbank", "disbursed", 110e6, "110 000 000 TND"),
        close_all("funders_audit"),
        ("report", {"summary": "Funder and audit records."}),
    ],
    ("web_news", 1): [
        ("list_tasks", {}),
        ev("news_jort_b", "C3", "le marché n° 2026-017 de 120 000 000 TND a été attribué"),
        ev("news_jort_c", "C3", "le marché n° 2026-017 de 120 000 000 TND a été attribué"),
        close_all("web_news", "partial", "articles all cite the JORT leak"),
        ("report", {"summary": "Articles all cite the JORT leak."}),
    ],
    ("social", 1): [
        ev("site_report", "C4", "aucune fondation visible"),
        ev("sentinel", "C4", "aucun changement de surface bâtie détecté"),
        close_all("social"),
        ("report", {"summary": "Site evidence."}),
    ],
    ("telegram", 1): [close_all("telegram", "not_found", "no relevant public posts"),
                      ("report", {"summary": "Nothing relevant in public channels."})],
    ("reviewer", 1): [
        ("list_proposals", {"status": "pending"}),
        ("complete_review", {"summary": "too early"}),  # refused: proposals pending
        ("__expand__", review_all),
        ("request_collection", {"specialist": "funders_audit", "purpose": "support", "subclaim_ids": ["C7"],
                                "instructions": "Find the contractor's managers in the business register"}),
        ("complete_review", {"summary": "Round 1 reviewed."}),
    ],
    ("official", 2): [
        ev("steg_procedure", "C5", "conformément à la procédure d'urgence", "qualifies"),
        close_all("official", "partial", "only the operator's own statement invokes urgency"),
        ("report", {"summary": "Only the operator's own statement invokes urgency [steg_procedure]."}),
    ],
    ("web_news", 2): [close_all("web_news", "not_found", "no correction or explanation published"),
                      ("report", {"summary": "No innocent explanation in the press."})],
    ("funders_audit", 2): [close_all("funders_audit", "blocked", "business register unreachable"),
                           ("report", {"summary": "Register blocked."})],
    ("reviewer", 2): [
        ("__expand__", review_all),
        ("complete_review", {"summary": "Anomalies: rewritten award [jort_award_v1], no tender [tuneps_search]."}),
    ],
}


def fake_runner(record, briefs, scripts=SCRIPTS):
    rounds = {}
    lock = threading.Lock()

    def script_for(system, brief):
        agent = "reviewer" if system.startswith("You are the reviewer") else next(
            name for name, focus in SPECIALIST_FOCUS.items() if focus in system)
        with lock:
            rounds[agent] = rounds.get(agent, 0) + 1
            n = rounds[agent]
            briefs[(agent, n)] = brief
        return scripts.get((agent, n), []), record.setdefault((agent, n), [])

    return ScriptedAgentRunner(script_for)


def draft():
    t = lambda spec, claims, purpose="support": PlannedTask(specialist=spec, objective=f"{spec} on {claims}",
                                                           subclaim_ids=claims, purpose=purpose, queries=[], urls=[])
    return PlanDraft(
        entities=[], window_start="2025-01-01", window_end=None,
        tasks=[t("official", ["C3", "C5", "C6"]), t("funders_audit", ["C3", "C6", "C99"]), t("web_news", ["C3"]),
               t("social", ["C4"]), t("telegram", ["C3"], "explore")],
        budget_weights=[BudgetWeight(specialist="official", weight=3), BudgetWeight(specialist="telegram", weight=0.2)],
    )


def test_plan_normalization_guarantees_two_kinds_of_source(store):
    ws = workspace(store)
    plan = normalize_plan(draft(), ws.allegation, total_budget=100)
    by_claim = {cid: {t.specialist for t in plan.tasks if cid in t.subclaim_ids and t.purpose == "support"}
                for cid in ws.allegation.core_subclaims}
    assert all(len(specs) >= 2 for specs in by_claim.values())
    assert "added official task so C4 is covered by two kinds of source" in plan.fixes
    assert any("unknown sub-claims" in f for f in plan.fixes)
    assert plan.budgets["official"] == 40 and plan.budgets["telegram"] == 5  # clamped to [5, 40]


def test_workflow_rounds_review_challenges_and_report(store):
    ws = WS["ws"] = workspace(store)
    record, briefs, events = {}, {}, []
    team = InvestigationTeam(runner=fake_runner(record, briefs), web_search=False, max_rounds=3,
                             on_event=lambda phase, detail: events.append(phase))
    result = team.run(ws, plan=normalize_plan(draft(), ws.allegation, total_budget=100))

    # Two rounds, then nothing left to do.
    assert [r.round for r in result.rounds] == [1, 2] and result.stop_reason == "no_open_tasks"
    assert set(result.rounds[1].specialists) == {"official", "web_news", "funders_audit"}
    # Searching for the tender notice (C5) and the progress reports (C4) already
    # challenged those; code queued a challenge for the other supported core
    # sub-claims, to official and web_news.
    expected = {t.expectation_id: (t.specialist, t.purpose) for t in ws.tasks if t.expectation_id}
    assert expected == {"C3.E1": ("official", "support"), "C4.E1": ("funders_audit", "challenge"),
                        "C5.E1": ("official", "challenge"), "C9.E1": ("official", "challenge"),
                        "C11.E1": ("official", "challenge"), "C12.E1": ("funders_audit", "challenge")}
    # Every innocent explanation is tested: through its expected record, or by a task of its own.
    innocent = {t.subclaim_ids[0]: t.specialist for t in ws.tasks if t.objective.startswith("Test the innocent")}
    assert innocent == {"C10": "official"}
    added = result.rounds[0].challenge_tasks_added
    challenged = {sid for t in ws.tasks if t.id in added for sid in t.subclaim_ids}
    assert challenged == {"C3", "C6"} and len(added) == 4
    # Specialists see their tasks in the brief; the reviewer's request reached round 2.
    assert "<your_tasks round=\"1\">" in briefs[("official", 1)]
    assert "business register" in briefs[("funders_audit", 2)]
    assert "the operator invokes decree 2026-0412" in briefs[("reviewer", 1)]
    # Wrap-ups are refused until the work is done.
    assert "Close your open tasks first" in record[("official", 1)][0][2]
    assert "still pending" in next(out for name, err, out in record[("reviewer", 1)] if err)
    # Leads posted in parallel are on the shared board.
    assert [lead.to for lead in ws.leads] == ["web_news", "reviewer"]
    # Verdict from accepted evidence only; disputed repeats do not count.
    assert [p.status for p in ws.proposals if p.item.doc_id.startswith("news_")] == ["disputed", "disputed"]
    assert result.verdict.verdict == "high_suspicion"
    assert ws.unchallenged() == []
    assert events[0] == "collect" and events[-1] == "verdict"
    # The case file records it all, including negative results.
    report = build_report(ws, result.verdict, result.review, stop_reason=result.stop_reason)
    assert "PROOF OF CONCEPT" in report and "| blocked | business register unreachable |" in report
    assert "✗ supports · `news_jort_b`" in report and "reviewer: repeats the JORT leak" in report
    assert "chain intact" in report
    assert "- **H4** (innocent) open: The direct award was a lawful emergency procedure." in report
    assert "Innocent explanation *sole_supplier* ruled out: The award notice" in report
    assert public_reply(result, Mode.INVESTIGATE, store, "Le marché a été attribué").startswith("Caligula a ouvert")


def test_no_progress_stops_early(store):
    ws = WS["ws"] = workspace(store)
    # Every round, the reviewer asks for more and nobody finds anything.
    scripts = {("official", n): [close_all("official", "not_found"), ("report", {"summary": "nothing"})]
               for n in range(1, 5)}
    for n in range(1, 5):
        scripts[("reviewer", n)] = [
            ("request_collection", {"specialist": "official", "purpose": "support", "instructions": f"try again {n}"}),
            ("complete_review", {"summary": "more"}),
        ]
    plan = normalize_plan(PlanDraft(entities=[], window_start=None, window_end=None, budget_weights=[], tasks=[]),
                          ws.allegation, 50, ("official",))
    team = InvestigationTeam(runner=fake_runner({}, {}, scripts), web_search=False, max_rounds=4,
                             specialists=[Specialist("official", ["list_tasks", "complete_task", "report"], False)])
    result = team.run(ws, plan=plan)
    assert result.stop_reason == "no_progress" and len(result.rounds) == 2


def test_specialists_only_get_their_tools(store):
    ws = WS["ws"] = workspace(store)
    runner = ScriptedAgentRunner(lambda system, brief: ([], []))
    team = InvestigationTeam(runner=runner, web_search=False, max_rounds=1,
                             specialists=[Specialist("telegram", ["fetch_telegram_channel", "report"], False)])
    plan = normalize_plan(draft(), ws.allegation, 50, ("telegram",))
    team.run(ws, plan=plan)
    toolsets = [sorted(t.__name__ for t in call["tools"]) for call in runner.calls]
    assert ["fetch_telegram_channel", "report"] in toolsets
    reviewer = next(t for t in toolsets if "review_proposal" in t)
    assert "ingest_url" not in reviewer and "fetch_telegram_channel" not in reviewer


def test_unfinished_tasks_carry_over(store):
    ws = WS["ws"] = workspace(store)
    first_task = lambda: [("complete_task", {"task_id": ws.open_tasks("official")[0].id, "outcome": "found", "note": "n"})]
    scripts = {
        # Round 1: closes only one of its tasks, then runs out of budget.
        ("official", 1): [("__expand__", first_task)] * 5 + [("report", {"summary": "out of budget"})],
        ("official", 2): [close_all("official", "not_found"), ("report", {"summary": "finished"})],
        ("reviewer", 1): [("complete_review", {"summary": "r1"})],
        ("reviewer", 2): [("complete_review", {"summary": "r2"})],
    }
    draft_ = PlanDraft(entities=[], window_start=None, window_end=None, budget_weights=[],
                       tasks=[PlannedTask(specialist="official", objective=f"task {i}", subclaim_ids=[], purpose="explore",
                                          queries=[], urls=[]) for i in range(8)])
    plan = normalize_plan(draft_, ws.allegation, 40, ("official",))  # 8 planned + 4 coverage tasks
    team = InvestigationTeam(runner=fake_runner({}, {}, scripts), web_search=False, max_rounds=3,
                             specialists=[Specialist("official", ["list_tasks", "complete_task", "report"], False)])
    result = team.run(ws, plan=plan)
    assert [r.round for r in result.rounds] == [1, 2]
    assert len(result.rounds[0].tasks_closed) == 5 and not ws.open_tasks()
