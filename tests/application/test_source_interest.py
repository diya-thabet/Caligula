"""A publisher discovered during collection is declared a party, and its
self-serving claim then weighs less, in the scoring and in the case file."""

import json

from caligula.adapters.presenters.markdown_report import build_report
from caligula.application.investigation.toolkit import build_tools
from caligula.application.investigation.workspace import AgentContext
from caligula.domain.model.documents import SourceKind
from conftest import add_doc
from support import workspace

NAMES = ["record_evidence", "list_proposals", "register_party", "review_proposal"]


def tools(ws, name):
    return {t.__name__: t for t in build_tools(ws, AgentContext(name=name, budget=20), NAMES)}


def test_registered_party_makes_its_denial_self_serving(store):
    ws = workspace(store, review_required=True)
    add_doc(store, "works_page", "Les travaux de l'extension ont commencé en mars 2026.",
            kind=SourceKind.OFFICIAL_LIVE, publisher="Direction des travaux de Rades-Fictive")
    tools(ws, "official")["record_evidence"](
        doc_id="works_page", subclaim_id="C4", relation="contradicts",
        quote="Les travaux de l'extension ont commencé", rationale="operator says works started")
    reviewer = tools(ws, "reviewer")
    [row] = json.loads(reviewer["list_proposals"]())
    assert row["publisher_interest"] == "none"

    reviewer["register_party"](name="STEG", role="accused", aliases=["Direction des travaux de Rades-Fictive"])
    [row] = json.loads(reviewer["list_proposals"]())
    assert row["publisher_interest"] == "self_serving"
    reviewer["review_proposal"](proposal_id=row["id"], decision="accept", note="operator's own claim")

    [item] = ws.verdict().weighed
    assert item.interest == "self_serving" and item.weight == 0.25  # official live 0.5, halved
    assert [p.aliases for p in ws.allegation.parties if p.name == "STEG"] == [
        ["Société tunisienne de l'électricité et du gaz", "Direction des travaux de Rades-Fictive"]]
    assert any(e.action == "party" and e.actor == "reviewer" for e in ws.ledger.entries)
    report = build_report(ws, ws.verdict())
    assert "Parties: STEG (accused)" in report
    assert "self-serving: the publisher is a party and this helps it" in report
