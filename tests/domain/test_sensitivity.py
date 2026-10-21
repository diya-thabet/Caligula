from datetime import UTC, datetime

from caligula.domain.model.claims import Allegation, SubClaim
from caligula.domain.model.documents import SourceKind
from caligula.domain.model.evidence import AbsenceFinding, EvidenceEdge, Relation
from caligula.domain.services.verdict import build_verdict
from conftest import add_doc


def _case():
    return Allegation(id="A", text="t", subject="s", claim_type="other",
                      subclaims=[SubClaim(id="C1", statement="award"), SubClaim(id="C2", statement="no tender")],
                      hypotheses=[], core_subclaims=["C1", "C2"])


def edge(doc, claim, quote):
    return EvidenceEdge(doc_id=doc, subclaim_id=claim, relation=Relation.SUPPORTS, quote=quote)


def test_conclusion_resting_on_one_origin_is_reported(store):
    add_doc(store, "mirror", "the award happened", kind=SourceKind.FOREIGN_MIRROR)
    add_doc(store, "audit", "the award happened; no tender", kind=SourceKind.AUDIT)
    add_doc(store, "copy", "copied: no tender", kind=SourceKind.NEWS, cites=["audit"])
    edges = [edge("mirror", "C1", "award happened"), edge("audit", "C1", "award happened"),
             edge("audit", "C2", "no tender"), edge("copy", "C2", "no tender")]
    v = build_verdict(store.corpus(), _case(), edges, [])
    assert v.verdict == "partially_supported"  # no deterministic signal, so not high_suspicion
    [dep] = v.depends_on
    # C1 survives losing either source; C2 rests on the audit and its copy: one origin.
    assert dep.origin == ["audit", "copy"]
    assert dep.changes == ["C2 supported -> unverified"] and not dep.changes_verdict


def test_verdict_changing_origins_come_first_and_absences_count(store):
    add_doc(store, "mirror", "the award happened", kind=SourceKind.FOREIGN_MIRROR)
    edges = [edge("mirror", "C1", "award happened")]
    absence = AbsenceFinding(subclaim_id="C2", relation=Relation.SUPPORTS, register_id="tuneps", query="q",
                             searched_at=datetime(2026, 6, 1, tzinfo=UTC))
    v = build_verdict(store.corpus(), _case(), edges, [], absences=[absence])
    assert [(d.origin, d.changes_verdict) for d in v.depends_on] == [
        (["mirror"], True), (["absence:tuneps"], False)]
    assert v.depends_on[0].changes == ["verdict partially_supported -> unverified", "C1 supported -> unverified"]


def test_sensitivity_can_be_skipped(store):
    add_doc(store, "mirror", "the award happened", kind=SourceKind.FOREIGN_MIRROR)
    v = build_verdict(store.corpus(), _case(), [edge("mirror", "C1", "award happened")], [], sensitivity=False)
    assert v.depends_on == []
