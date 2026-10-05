from datetime import UTC, datetime

from caligula.domain.model.claims import Allegation, SubClaim
from caligula.domain.model.documents import SourceKind
from caligula.domain.model.evidence import AbsenceFinding, Relation
from caligula.domain.services.verdict import build_verdict
from conftest import add_doc

JUNE = datetime(2026, 6, 1, tzinfo=UTC)


def _case():
    return Allegation(id="A", text="t", subject="s", claim_type="procurement",
                      subclaims=[SubClaim(id="C1", statement="no tender notice was published")],
                      hypotheses=[], core_subclaims=["C1"])


def absent(register, doc_id=None, **kw):
    return AbsenceFinding(subclaim_id=kw.pop("subclaim_id", "C1"), relation=kw.pop("relation", Relation.SUPPORTS),
                          register_id=register, query="extension centrale Rades-Fictive",
                          searched_at=kw.pop("searched_at", JUNE), doc_id=doc_id, **kw)


def test_absence_weighs_by_register_completeness_and_capture(store):
    add_doc(store, "tuneps_empty", "Aucun résultat pour : extension centrale", kind=SourceKind.ARCHIVE, day=20)
    v = build_verdict(store.corpus(), _case(), [], [], absences=[absent("tuneps", "tuneps_empty")])
    assert [(w.kind, w.weight) for w in v.weighed] == [("absence", 0.8)]
    assert v.by_subclaim[0].status == "supported"

    v = build_verdict(store.corpus(), _case(), [], [], absences=[absent("tuneps")])
    assert v.weighed[0].weight == 0.4 and v.weighed[0].doc_id == "absence:tuneps"  # our word only
    v = build_verdict(store.corpus(), _case(), [], [], absences=[absent("web_search")])
    assert v.by_subclaim[0].support == 0.025  # no article found proves little


def test_repeated_searches_of_one_register_are_one_origin(store):
    findings = [absent("tuneps"), absent("tuneps", note="second try"), absent("jort")]
    [c1] = build_verdict(store.corpus(), _case(), [], [], absences=findings).by_subclaim
    assert c1.supporting_clusters == [["absence:tuneps"], ["absence:jort"]]
    assert c1.support == round(1 - (1 - 0.4) * (1 - 0.425), 3)


def test_unverifiable_absences_are_rejected(store):
    add_doc(store, "early_capture", "Aucun résultat", kind=SourceKind.ARCHIVE, day=2)
    window_end = datetime(2026, 1, 15, tzinfo=UTC)
    findings = [
        absent("facebook"),
        absent("tuneps", relation=Relation.QUALIFIES),
        absent("tuneps", subclaim_id="C9"),
        absent("tuneps", "early_capture", window_end=window_end),
        absent("tuneps", searched_at=datetime(2026, 1, 3, tzinfo=UTC), window_end=window_end),
        absent("tuneps", window_start=JUNE, window_end=window_end),
    ]
    v = build_verdict(store.corpus(), _case(), [], [], absences=findings)
    assert [r.reason for r in v.rejected_evidence] == [
        "unknown register facebook",
        "an absence supports or contradicts a sub-claim; it cannot qualify it",
        "unknown sub-claim C9",
        "capture early_capture predates the end of the window it claims to cover",
        "search made before the end of the window it claims to cover",
        "search window ends before it starts",
    ]
    assert v.weighed == []
