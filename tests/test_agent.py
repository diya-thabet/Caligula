"""The agent loop with a scripted stand-in for Claude: checks the plumbing and
that code, not the model, decides what counts."""

import json
from types import SimpleNamespace

import httpx

from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.agent.reply import public_reply
from caligula.agent.runner import InvestigatorAgent
from caligula.agent.workspace import Connectors, Mode, Workspace
from caligula.case import load_case
from caligula.domain.model.claims import Allegation
from caligula.ingest.sources import WorldBankClient
from conftest import FIXTURE


class ScriptedRunner:
    """Plays a fixed sequence of tool calls through the real tool objects."""

    def __init__(self, tools, script, record):
        self.tools = {t.name: t for t in tools if hasattr(t, "name")}
        self.script, self.record = script, record

    def __iter__(self):
        script = list(self.script)
        while script:
            name, args = script.pop(0)
            if name == "__expand__":  # decide the next calls from the live workspace state
                script[:0] = args()
                continue
            try:
                out, err = self.tools[name].call(args), False
            except Exception as exc:  # ToolError -> is_error result, as in the SDK runner
                out, err = str(exc), True
            self.record.append((name, err, out))
            yield SimpleNamespace(content=[], stop_reason="tool_use")
        yield SimpleNamespace(content=[], stop_reason="end_turn")

    def generate_tool_call_response(self):
        return None


def agent_for(script, record, calls):
    def tool_runner(**kwargs):
        calls.append(kwargs)
        return ScriptedRunner(kwargs["tools"], script, record)

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner)))
    return InvestigatorAgent(client=client, web_search=False)


def workspace(store, mode=Mode.INVESTIGATE, **kw):
    case = load_case(FIXTURE, store)
    return Workspace(store=store, allegation=Allegation.model_validate(case["allegation"]), mode=mode,
                     ledger=JsonlLedger(), **kw)


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
        ("finish", {"summary": "Award [jort_award_v1] was rewritten [jort_award_v2]; see [nowhere]."}),
        ("search_evidence", {"query": "after finish", "purpose": "explore"}),  # refused
    ]
    record, calls = [], []
    result = agent_for(script, record, calls).run(ws)

    errors = [(name, out) for name, err, out in record if err]
    assert [e[0] for e in errors] == ["record_evidence", "finish", "search_evidence"]
    assert "editable source" in errors[0][1] and "C3" in errors[1][1]
    assert result.verdict.verdict == "high_suspicion"
    assert result.unknown_citations == ["nowhere"]
    assessed = json.loads(next(out for name, _, out in record if name == "assess"))
    assert assessed["not_yet_challenged"] == [] and assessed["financial"]["flagged"]
    assert calls[0]["fallbacks"] == "default" and calls[0]["model"] == "claude-opus-5"
    assert "investigation" in calls[0]["system"]
    assert public_reply(result, Mode.INVESTIGATE, store).startswith("Caligula opened case")


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
        ("finish", {"summary": "Demand did not surge [ins_peak]."}),
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
