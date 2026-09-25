"""Parallel specialists + reviewer, with scripted stand-ins for Claude."""

import json
import threading
from types import SimpleNamespace

from caligula.agent.prompts import SPECIALIST_FOCUS
from caligula.agent.reply import public_reply
from caligula.agent.team import InvestigationTeam, Specialist
from caligula.agent.workspace import Mode

from test_agent import ScriptedRunner, workspace


def ev(doc, claim, quote, rel="supports"):
    return ("record_evidence", {"doc_id": doc, "subclaim_id": claim, "relation": rel, "quote": quote, "rationale": "r"})


def amount(doc, role, value, quote):
    return ("record_amount", {"doc_id": doc, "role": role, "amount_tnd": value, "quote": quote})


SCRIPTS = {
    ("official", 1): [
        ("compare_versions", {"canonical_url": "https://jort.example.tn/2026/017"}),
        ev("jort_award_v1", "C3", "extension de 450 MW de la centrale de Rades-Fictive"),
        ev("jort_award_v1", "C5", "par procédure de gré à gré"),
        ev("tuneps_search", "C5", "Aucun avis d'appel d'offres publié"),
        amount("jort_award_v1", "allocated", 120e6, "120 000 000 TND"),
        amount("benchmark", "benchmark", 60e6, "60 000 000 TND"),
        ("report", {"summary": "JORT award rewritten between [jort_award_v1] and [jort_award_v2]."}),
    ],
    ("funders_audit", 1): [
        ev("worldbank", "C3", "extension de capacité, centrale de Rades-Fictive"),
        ev("audit", "C5", "n'est pas justifié par une situation d'urgence documentée"),
        amount("worldbank", "disbursed", 110e6, "110 000 000 TND"),
        ("report", {"summary": "Funder and audit records."}),
    ],
    ("web_news", 1): [
        # Three articles repeating one leak: proposed, and the reviewer disputes the repeats.
        ev("news_jort_b", "C3", "le marché n° 2026-017 de 120 000 000 TND a été attribué"),
        ev("news_jort_c", "C3", "le marché n° 2026-017 de 120 000 000 TND a été attribué"),
        ("report", {"summary": "Articles all cite the JORT leak."}),
    ],
    ("social", 1): [
        ev("site_report", "C4", "aucune fondation visible"),
        ev("sentinel", "C4", "aucun changement de surface bâtie détecté"),
        ("report", {"summary": "Site evidence."}),
    ],
    ("telegram", 1): [("report", {"summary": "Nothing relevant in public channels."})],
    ("reviewer", 1): [
        ("list_proposals", {"status": "pending"}),
        ("__expand__", lambda: review_all()),
        ("complete_review", {"summary": "too early"}),  # refused: nothing challenged
        *[("request_collection", {"specialist": "official", "instructions": "Look for an emergency decree",
                                  "purpose": "challenge", "subclaim_id": c}) for c in ("C3", "C4", "C5", "C6")],
        ("complete_review", {"summary": "Round 1 reviewed; challenges requested."}),
    ],
    ("official", 2): [
        *[("search_evidence", {"query": "décret 2026-0412 urgence", "purpose": "challenge", "subclaim_id": c})
          for c in ("C3", "C4", "C5", "C6")],
        ev("steg_procedure", "C5", "conformément à la procédure d'urgence", "qualifies"),
        ("report", {"summary": "Only the operator's own statement invokes urgency [steg_procedure]."}),
    ],
    ("reviewer", 2): [
        ("__expand__", lambda: review_all()),
        ("assess", {}),
        ("complete_review", {"summary": "Anomalies: rewritten award [jort_award_v1], no tender [tuneps_search]."}),
    ],
}


WS = {}


def review_all():
    """Reviewer policy for the test: repeats of the leak are disputed, the rest accepted."""
    return [
        ("review_proposal", {"proposal_id": p.id, "note": "r",
                             "decision": "dispute" if p.item.doc_id.startswith("news_") else "accept"})
        for p in WS["ws"].proposals if p.status == "pending"
    ]


def fake_team(record, briefs):
    rounds = {}
    lock = threading.Lock()

    def tool_runner(**kwargs):
        system = kwargs["system"]
        agent = "reviewer" if system.startswith("You are the reviewer") else next(
            name for name, focus in SPECIALIST_FOCUS.items() if focus in system)
        with lock:
            rounds[agent] = rounds.get(agent, 0) + 1
            n = rounds[agent]
            briefs[(agent, n)] = kwargs["messages"][0]["content"]
        agent_record = record.setdefault((agent, n), [])
        return ScriptedRunner(kwargs["tools"], SCRIPTS.get((agent, n), []), agent_record)

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner)))
    return InvestigationTeam(client=client, web_search=False, max_rounds=2)


def test_team_collects_in_parallel_and_reviewer_decides(store):
    ws = WS["ws"] = workspace(store)
    record, briefs = {}, {}
    result = fake_team(record, briefs).run(ws)

    assert result.rounds == 2
    # Round 2 ran only the specialist the reviewer asked for, with its instructions.
    assert set(k for k in record if k[1] == 2) == {("official", 2), ("reviewer", 2)}
    assert "Look for an emergency decree" in briefs[("official", 2)]
    # The reviewer could not close round 1 before requesting challenges.
    refused = [out for name, err, out in record[("reviewer", 1)] if err]
    assert len(refused) == 1 and "not been challenged" in refused[0]
    # Disputed repeats do not count; verdict computed from accepted evidence only.
    assert [p.status for p in ws.proposals if p.item.doc_id.startswith("news_")] == ["disputed", "disputed"]
    assert result.verdict.verdict == "high_suspicion"
    assert result.reports["official"][1].startswith("Only the operator's own statement")
    assert result.unknown_citations == []
    # Every capture, proposal and decision is in an intact ledger.
    actions = {e.action for e in ws.ledger.entries}
    assert {"proposal", "review"} <= actions and ws.ledger.verify() is None
    assert public_reply(result, Mode.INVESTIGATE, store, "Le marché a été attribué").startswith("Caligula a ouvert")


def test_specialists_only_get_their_tools(store):
    ws = workspace(store)
    seen = {}

    def tool_runner(**kwargs):
        seen[kwargs["system"][-60:]] = sorted(t.name for t in kwargs["tools"] if hasattr(t, "name"))
        return ScriptedRunner(kwargs["tools"], [], [])

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner)))
    team = InvestigationTeam(client=client, web_search=False, max_rounds=1,
                             specialists=[Specialist("telegram", ["fetch_telegram_channel", "report"], False)])
    team.run(ws)
    toolsets = list(seen.values())
    assert ["fetch_telegram_channel", "report"] in toolsets
    reviewer = next(t for t in toolsets if "review_proposal" in t)
    assert "ingest_url" not in reviewer and "fetch_telegram_channel" not in reviewer
