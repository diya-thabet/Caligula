from types import SimpleNamespace

from caligula.adapters.fixtures.case_directory import load_case, run_case
from caligula.adapters.llm.claude_analyst import (
    ClaudeAnalyst,
    _Amount,
    _Decomposition,
    _Edge,
    _Hypothesis,
    _Prediction,
    _Reading,
)
from caligula.domain.model.claims import SubClaim
from conftest import FIXTURE


def test_synthetic_steg_case_offline(store):
    v = run_case(FIXTURE, store)
    status = {c.id: c.status for c in v.by_subclaim}
    assert status == {
        "C1": "supported", "C2": "contradicted", "C3": "supported", "C4": "supported",
        "C5": "supported", "C6": "supported", "C7": "unverified", "C8": "unverified",
    }
    assert {h.id: h.status for h in v.hypotheses} == {"H1": "consistent", "H2": "falsified", "H3": "consistent"}
    [flag] = v.retcon_flags
    assert flag.changes[0].removed == ["120000000"] and flag.changes[0].added == ["80000000"]
    assert v.financial.reference_amount_tnd == 120e6 and v.financial.flagged
    # 2 bad LLM proposals, 1 amount not in its quote, and the live JORT page
    # (editable, first seen after the outage) cannot attest the project pre-existed.
    assert len(v.rejected_evidence) == 4
    assert any("jort_award_v2 is an editable source" in r.reason for r in v.rejected_evidence)
    assert v.verdict == "high_suspicion"
    # Three news articles citing the archived JORT page add no independent support.
    c3 = next(c for c in v.by_subclaim if c.id == "C3")
    assert len(c3.supporting_clusters) == 2


class FakeMessages:
    """Stands in for client.beta.messages; returns canned parsed outputs."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", stop_details=None, parsed_output=self.outputs.pop(0))


def test_live_mode_output_goes_through_same_validation(store):
    load_case(FIXTURE, store)
    decomposition = _Decomposition(
        subject="s", claim_type="procurement",
        subclaims=[SubClaim(id="C1", statement="outage happened")],
        hypotheses=[_Hypothesis(id="H1", statement="h", kind="allegation", explains=None,
                                predictions=[_Prediction(subclaim_id="C1", predicted_true=True),
                                             _Prediction(subclaim_id="C99", predicted_true=True)])],
        core_subclaims=["C1", "C99"], financial_subclaim="C98", parties=[], ruled_out=[],
    )
    readings = []
    for doc in store.documents.values():
        if doc.id == "nightlights":
            readings.append(_Reading(edges=[_Edge(subclaim_id="C1", relation="supports", quote="Baisse de radiance nocturne de 62 %", rationale="")], amounts=[]))
        elif doc.id == "steg_communique":
            readings.append(_Reading(edges=[_Edge(subclaim_id="C1", relation="supports", quote="invented sentence", rationale="")],
                                     amounts=[_Amount(role="allocated", amount_tnd=1.0, quote="4 870 MW")]))
        else:
            readings.append(_Reading(edges=[], amounts=[]))
    messages = FakeMessages([decomposition, *readings])
    investigator = ClaudeAnalyst(client=SimpleNamespace(beta=SimpleNamespace(messages=messages)))

    v = run_case(FIXTURE, store, investigator)

    assert v.by_subclaim[0].supporting_clusters == [["nightlights"]]
    assert len(v.rejected_evidence) == 2
    # Code added the five standard innocent explanations for procurement; until
    # they are tested, the allegation hypothesis stays open.
    assert len(v.hypotheses) == 6 and v.hypotheses[0].status == "open"
    assert v.hypotheses[0].reasons[:2] == ["C1=True as predicted", "C2 is unverified"]
    first = messages.calls[0]
    assert first["model"] == "claude-opus-5" and first["fallbacks"] == "default"
