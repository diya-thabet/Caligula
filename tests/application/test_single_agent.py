"""The agent loop with a scripted stand-in for Claude: checks the plumbing and
that code, not the model, decides what counts."""

import json

import httpx

from caligula.adapters.presenters.public_reply import public_reply
from caligula.adapters.sources.worldbank import WorldBankClient
from caligula.application.investigation.single_agent import InvestigatorAgent
from caligula.application.investigation.workspace import Connectors, Mode
from support import ScriptedAgentRunner, assert_invariants, workspace


def agent_for(script, record, calls):
    return InvestigatorAgent(ScriptedAgentRunner(lambda system, brief: (script, record), calls), web_search=False)


def test_agent_builds_case_and_must_challenge_before_finishing(store):
    ws = workspace(store)
    ev = lambda doc, c, q, rel="supports": ("record_evidence", {"doc_id": doc, "subclaim_id": c, "relation": rel, "quote": q, "rationale": "r"})
    script = [
        ("search_evidence", {"query": "marché 2026-017", "purpose": "support", "subclaim_id": "C3"}),
        ("compare_versions", {"canonical_url": "https://jort.example.tn/2026/017"}),
        ev("jort_award_v1", "C3", "extension de 450 MW de la centrale de Rades-Fictive"),
        ev("worldbank", "C3", "extension de capacité, centrale de Rades-Fictive"),
        ev("jort_award_v2", "C3", "extension de 450 MW de la centrale de Rades-Fictive"),  # rejected: backdating rule
        ev("site_report", "C4", "aucune fondation visible"),
        ev("sentinel", "C4", "aucun changement de surface bâtie détecté"),
        ev("jort_award_v1", "C5", "par procédure de gré à gré"),
        ev("audit", "C5", "n'est pas justifié par une situation d'urgence documentée"),
        ev("tuneps_search", "C5", "Aucun avis d'appel d'offres publié"),
        ("record_amount", {"doc_id": "jort_award_v1", "role": "allocated", "amount_tnd": 120e6, "quote": "120 000 000 TND"}),
        ("record_amount", {"doc_id": "benchmark", "role": "benchmark", "amount_tnd": 60e6, "quote": "60 000 000 TND"}),
        ("record_amount", {"doc_id": "worldbank", "role": "disbursed", "amount_tnd": 110e6, "quote": "110 000 000 TND"}),
        ("finish", {"summary": "too early"}),  # refused: nothing challenged yet
        *[("search_evidence", {"query": "procédure d'urgence décret 2026-0412", "purpose": "challenge", "subclaim_id": c})
          for c in ("C3", "C4", "C5", "C6")],
        ev("steg_procedure", "C5", "conformément à la procédure d'urgence", "qualifies"),
        ("assess", {}),
        # Refused once: documents are cited, not evidence items.
        ("finish", {"summary": "Award [jort_award_v1] was rewritten [jort_award_v2]; see [nowhere]."}),
        ("finish", {"summary": "The award was made by direct agreement [E5]. It was worth 120 million TND "
                               "[E8]; see [nowhere]."}),
        ("search_evidence", {"query": "after finish", "purpose": "explore"}),  # refused
    ]
    record, calls = [], []
    result = agent_for(script, record, calls).run(ws)

    errors = [(name, out) for name, err, out in record if err]
    assert [e[0] for e in errors] == ["record_evidence", "finish", "finish", "search_evidence"]
    assert "editable source" in errors[0][1] and "C3" in errors[1][1]
    assert "cites documents, not evidence items: jort_award_v1, jort_award_v2" in errors[2][1]
    assert [s.status for s in ws.attribution.sentences] == ["unjudged", "unjudged"]
    assert result.verdict.verdict == "high_suspicion"
    assert result.unknown_citations == ["nowhere"]
    assessed = json.loads(next(out for name, _, out in record if name == "assess"))
    assert assessed["not_yet_challenged"] == [] and assessed["financial"]["flagged"]
    assert calls[0]["web_search"] is False
    assert "investigation" in calls[0]["system"]
    assert public_reply(result, Mode.INVESTIGATE, store).startswith("Caligula opened case")
    assert_invariants(ws, result.verdict)


def test_budget_is_enforced(store):
    ws = workspace(store, mode=Mode.FACTCHECK, budget=2)
    script = [("search_evidence", {"query": "q", "purpose": "explore"})] * 3 + [("assess", {}), ("finish", {"summary": "s"})]
    record = []
    agent_for(script, record, []).run(ws)
    assert [err for _, err, _ in record] == [False, False, True, False, False]
    assert "budget exhausted" in record[2][2]


def test_factcheck_reply_cites_sources(store):
    ws = workspace(store, mode=Mode.FACTCHECK)
    script = [
        ("record_evidence", {"doc_id": "ins_peak", "subclaim_id": "C2", "relation": "contradicts", "quote": "2026 : 4 870 MW (+0,8 % par rapport à 2025)", "rationale": "r"}),
        ("record_evidence", {"doc_id": "weather", "subclaim_id": "C2", "relation": "contradicts", "quote": "Aucun épisode de chaleur exceptionnel", "rationale": "r"}),
        ("finish", {"summary": "Demand did not surge [E1, E2]."}),
    ]
    ws.allegation.core_subclaims = ["C2"]
    result = agent_for(script, [], []).run(ws)
    reply = public_reply(result, Mode.FACTCHECK, store)
    assert reply.startswith("Contradicted by the documents.")
    assert "INS (fictif), 2026-09-02" in reply


def test_funder_records_are_stored_as_foreign_mirror(store):
    body = {"projects": {"P000001": {"id": "P000001", "project_name": "Fictional Power Project", "totalcommamt": "100,000,000"}}}
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    ws = workspace(store, connectors=Connectors(funders=WorldBankClient(http)))
    record = []
    agent_for([("search_funder_records", {"query": "power"})], record, []).run(ws)
    out = json.loads(record[0][2])
    doc = store.get(out["doc_id"])
    assert doc.source_kind == "foreign_mirror" and "Fictional Power Project" in doc.text
    assert out["projects"][0]["id"] == "P000001"
