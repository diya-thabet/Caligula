from types import SimpleNamespace

from caligula.adapters.fixtures.case_directory import load_case, run_case
from caligula.adapters.llm.analyst_base import AmountOut, Decomposition, EdgeOut, HypothesisOut, Prediction, Reading
from caligula.adapters.llm.claude_analyst import ClaudeAnalyst
from caligula.domain.model.claims import SubClaim
from conftest import FIXTURE


def test_synthetic_steg_case_offline(store):
    v = run_case(FIXTURE, store)
    status = {c.id: c.status for c in v.by_subclaim}
    assert status == {
        "C1": "supported", "C2": "contradicted", "C3": "supported", "C4": "supported",
        "C5": "supported", "C6": "supported", "C7": "unverified", "C8": "unverified",
        # The operator's emergency (self-serving) against the audit and the decree missing from the JORT.
        "C9": "contradicted",
        # Innocent explanations code added and nobody has tested yet.
        "C10": "unverified", "C11": "unverified", "C12": "unverified",
    }
    assert {h.id: h.status for h in v.hypotheses} == {
        "H1": "consistent", "H2": "falsified", "H3": "open", "H4": "falsified",
        "H5": "open", "H6": "open", "H7": "open",
    }
    # ACH: the missing tender (C5) fits a rigged award and a lawful emergency alike;
    # only the emergency evidence (C9) tells them apart, and it goes against H4.
    outage, award = v.ach
    assert outage.ranking == ["H1", "H2"]
    assert award.ranking == ["H3", "H4"] and award.untested == ["H5", "H6", "H7"]
    assert {r.subclaim_id for r in award.rows if r.diagnostic} == {"C9"}
    assert award.inconsistency["H3"] == 0.25 and award.inconsistency["H4"] == 1.275
    # The verdict rests on the benchmark and on the satellite analysis: each is a single origin.
    critical = [(d.origin, d.changes) for d in v.depends_on if d.changes_verdict]
    assert critical == [
        (["benchmark"], ["verdict high_suspicion -> partially_supported", "C6 supported -> unverified"]),
        (["sentinel"], ["verdict high_suspicion -> partially_supported", "C4 supported -> partially_supported"]),
    ]
    c9 = {w.doc_id: (w.weight, w.interest) for w in v.weighed if w.subclaim_id == "C9"}
    assert c9 == {"steg_procedure": (0.25, "self_serving"), "audit": (0.85, "none"), "absence:jort": (0.425, "none")}
    [flag] = v.retcon_flags
    assert flag.changes[0].removed == ["120000000"] and flag.changes[0].added == ["80000000"]
    assert v.financial.reference_amount_tnd == 120e6 and v.financial.flagged
    # 2 bad LLM proposals, 1 amount not in its quote, and the live JORT page
    # (editable, first seen after the outage) cannot attest the project pre-existed.
    assert len(v.rejected_evidence) == 4
    assert any("jort_award_v2 is an editable source" in r.reason for r in v.rejected_evidence)
    assert v.verdict == "high_suspicion"
    # Likelihood and confidence are two statements: the facts are very likely, but the
    # basis is only moderate, and the reasons say what would raise it.
    assert (v.likelihood, v.likelihood_term, v.confidence) == (0.867, "very likely", "moderate")
    assert v.confidence_reasons == [
        "the verdict would change without benchmark", "the verdict would change without sentinel",
        "innocent explanation H5 not yet tested", "innocent explanation H6 not yet tested",
        "innocent explanation H7 not yet tested",
    ]
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
    decomposition = Decomposition(
        subject="s", claim_type="procurement",
        subclaims=[SubClaim(id="C1", statement="outage happened")],
        hypotheses=[HypothesisOut(id="H1", statement="h", kind="allegation", explains=None,
                                predictions=[Prediction(subclaim_id="C1", predicted_true=True),
                                             Prediction(subclaim_id="C99", predicted_true=True)])],
        core_subclaims=["C1", "C99"], financial_subclaim="C98", parties=[], ruled_out=[],
    )
    readings = []
    for doc in store.documents.values():
        if doc.id == "nightlights":
            readings.append(Reading(edges=[EdgeOut(subclaim_id="C1", relation="supports", quote="Baisse de radiance nocturne de 62 %", rationale="")], amounts=[]))
        elif doc.id == "steg_communique":
            readings.append(Reading(edges=[EdgeOut(subclaim_id="C1", relation="supports", quote="invented sentence", rationale="")],
                                     amounts=[AmountOut(role="allocated", amount_tnd=1.0, quote="4 870 MW")]))
        else:
            readings.append(Reading(edges=[], amounts=[]))
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
