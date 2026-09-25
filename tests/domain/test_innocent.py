from caligula.domain.model.claims import (
    Allegation,
    Hypothesis,
    HypothesisKind,
    Party,
    PartyRole,
    RuledOut,
    SubClaim,
)
from caligula.domain.model.documents import SourceKind
from caligula.domain.model.evidence import EvidenceEdge, Relation
from caligula.domain.services.innocent import ensure_innocent_explanations, explanations_for
from caligula.domain.services.verdict import build_verdict
from conftest import add_doc


def _case(**kw):
    return Allegation(
        id="A", text="t", subject="s", claim_type=kw.pop("claim_type", "corruption_procurement"),
        subclaims=[SubClaim(id="C1", statement="the award skipped the tender"),
                   SubClaim(id="C3", statement="the price is inflated")],
        hypotheses=[Hypothesis(id="H1", statement="rigged award", predicts={"C1": True},
                               kind=HypothesisKind.ALLEGATION)],
        core_subclaims=["C1", "C3"], **kw,
    )


def test_claim_type_selects_the_catalogue():
    assert [e.id for e in explanations_for("corruption_procurement")] == [
        "emergency", "sole_supplier", "price_shock", "clerical_error", "documented_delay"]
    assert [e.id for e in explanations_for("undisclosed_foreign_funding")] == ["funding_declared", "homonym"]
    assert explanations_for("other") == []


def test_missing_explanations_become_tests_the_allegation_denies():
    original = _case()
    a, notes = ensure_innocent_explanations(original)
    assert len(original.subclaims) == 2  # not mutated
    assert [c.id for c in a.subclaims] == ["C1", "C3", "C2", "C4", "C5", "C6", "C7"]  # free ids, no collisions
    emergency = a.subclaims[2]
    assert emergency.bearing == "for" and emergency.expected_records[0].register_id == "jort"
    assert a.bearing_of("C2") == "for" and "C2" not in a.core_subclaims
    h2 = next(h for h in a.hypotheses if h.explains == "emergency")
    assert (h2.id, h2.kind, h2.predicts) == ("H2", "innocent", {"C2": True})
    assert a.hypotheses[0].predicts == {"C1": True, "C2": False, "C4": False, "C5": False, "C6": False, "C7": False}
    assert notes[0] == "added innocent explanation emergency as H2 (tested by C2)"


def test_covered_or_ruled_out_explanations_are_not_added():
    case = _case(ruled_out=[RuledOut(explanation_id="sole_supplier", reason="the notice invokes urgency only"),
                            RuledOut(explanation_id="price_shock", reason=" ")])  # no reason: does not count
    case.hypotheses.append(Hypothesis(id="H9", statement="lawful emergency", predicts={"C1": True},
                                      kind=HypothesisKind.INNOCENT, explains="emergency"))
    a, notes = ensure_innocent_explanations(case)
    added = [h.explains for h in a.hypotheses if h.id not in ("H1", "H9")]
    assert added == ["price_shock", "clerical_error", "documented_delay"]
    assert len(notes) == 3


def test_refuted_innocent_explanation_is_falsified(store):
    a, _ = ensure_innocent_explanations(_case())
    add_doc(store, "audit", "Le recours au gré à gré n'est pas justifié par une urgence documentée.",
            kind=SourceKind.AUDIT)
    add_doc(store, "reply", "Le marché relève de la procédure d'urgence.", kind=SourceKind.OFFICIAL_LIVE,
            publisher="STEG")
    edges = [EvidenceEdge(doc_id="audit", subclaim_id="C2", relation=Relation.CONTRADICTS,
                          quote="n'est pas justifié par une urgence documentée"),
             EvidenceEdge(doc_id="reply", subclaim_id="C2", relation=Relation.SUPPORTS,
                          quote="relève de la procédure d'urgence")]

    def h2_status(allegation):
        return next(h.status for h in build_verdict(store.corpus(), allegation, edges, []).hypotheses if h.id == "H2")

    # An audit against an unknown publisher's word (0.85 vs 0.5): contested, the explanation stays open.
    assert h2_status(a) == "open"
    # Once the operator is known to be the accused, its justification is self-serving (0.25).
    a.parties.append(Party(name="STEG", role=PartyRole.ACCUSED))
    assert h2_status(a) == "falsified"
