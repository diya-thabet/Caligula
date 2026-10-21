"""Evidence ids: every item that counts gets one, so a summary can cite the exact
quote or search it relies on rather than a whole document."""

import json

from caligula.application.investigation.toolkit import build_tools
from caligula.application.investigation.workspace import AgentContext
from caligula.domain.model.evidence import EvidenceEdge, Relation
from support import workspace

NAMES = ["record_evidence", "list_proposals", "review_proposal", "assess"]


def tools(ws, name):
    return {t.__name__: t for t in build_tools(ws, AgentContext(name=name, budget=20), NAMES)}


def edge(quote="extension de 450 MW", claim="C3", doc="jort_award_v1"):
    return EvidenceEdge(doc_id=doc, subclaim_id=claim, relation=Relation.SUPPORTS, quote=quote)


def test_an_item_gets_its_id_when_it_first_counts(store):
    ws = workspace(store, review_required=True)
    official, reviewer = tools(ws, "official"), tools(ws, "reviewer")
    out = official["record_evidence"](doc_id="jort_award_v1", subclaim_id="C3", relation="supports",
                                      quote="extension de 450 MW", rationale="r")
    assert out.startswith("Proposed as P1") and ws.evidence_ids == {}  # a proposal is not evidence yet
    assert reviewer["review_proposal"](proposal_id="P1", decision="accept", note="ok") == \
        "P1 accepted: counts as evidence E1."
    [row] = json.loads(reviewer["list_proposals"](status="accepted"))
    assert row["evidence_id"] == "E1"
    assert json.loads(reviewer["assess"]())["counted_evidence"] == {
        "E1": "C3 supports [jort_award_v1]: « extension de 450 MW »"}
    assert [e.data["evidence_id"] for e in ws.ledger.entries if e.action == "review"] == ["E1"]


def test_ids_are_never_reused_and_a_withdrawn_item_stops_counting(store):
    ws = workspace(store, review_required=True)
    for quote in ("extension de 450 MW", "pour un montant de 120 000 000 TND"):
        ws.record(edge(quote), "official")
    ws.review("P1", True, "ok", "reviewer")
    ws.review("P2", True, "ok", "reviewer")
    ws.review("P1", False, "wrong entity after all", "reviewer")
    assert list(ws.counted()) == ["E2"] and set(ws.evidence_ids) == {"E1", "E2"}
    ws.review("P1", True, "right entity", "reviewer")
    assert list(ws.counted()) == ["E1", "E2"]  # the same item keeps its id


def test_without_review_an_item_counts_and_gets_its_id_at_once(store):
    ws = workspace(store)
    out = tools(ws, "investigator")["record_evidence"](doc_id="jort_award_v1", subclaim_id="C3",
                                                       relation="supports", quote="extension de 450 MW",
                                                       rationale="r")
    assert out == "Accepted as evidence E1." and list(ws.counted()) == ["E1"]
    assert [e.data["id"] for e in ws.ledger.entries if e.action == "evidence"] == ["E1"]
