from caligula.models import (
    Allegation,
    AmountRole,
    EvidenceEdge,
    FinancialFigure,
    Hypothesis,
    Relation,
    SourceKind,
    SubClaim,
)
from caligula.verdict import build_verdict

from conftest import add_doc


def allegation(**kw):
    return Allegation(
        id="A",
        text="t",
        subject="s",
        claim_type="corruption_procurement",
        subclaims=[SubClaim(id="C1", statement="award happened"), SubClaim(id="C2", statement="demand surged"),
                   SubClaim(id="C3", statement="price inflated")],
        hypotheses=[Hypothesis(id="H", statement="surge", predicts={"C2": True})],
        core_subclaims=kw.pop("core", ["C1"]),
        **kw,
    )


def edge(doc, claim, quote, rel=Relation.SUPPORTS):
    return EvidenceEdge(doc_id=doc, subclaim_id=claim, relation=rel, quote=quote)


def test_echo_chamber_does_not_add_confidence(store):
    add_doc(store, "src", "the award happened", kind=SourceKind.NEWS)
    for i in range(5):
        add_doc(store, f"echo{i}", f"echo {i}: the award happened", cites=["src"])
    edges = [edge("src", "C1", "the award happened")] + [
        edge(f"echo{i}", "C1", "the award happened") for i in range(5)
    ]
    [c1, *_] = build_verdict(store, allegation(), edges, []).by_subclaim
    assert len(c1.supporting_clusters) == 1
    assert c1.support == 0.35  # one news origin, not six
    assert c1.status == "partially_supported"


def test_independent_sources_combine(store):
    add_doc(store, "mirror", "the award happened", kind=SourceKind.FOREIGN_MIRROR)
    add_doc(store, "audit", "audit: the award happened", kind=SourceKind.AUDIT)
    v = build_verdict(store, allegation(), [edge("mirror", "C1", "award happened"), edge("audit", "C1", "award happened")], [])
    assert v.by_subclaim[0].status == "supported"
    assert v.by_subclaim[0].support == 0.97


def test_hallucinated_quote_and_unknown_claim_are_rejected(store):
    add_doc(store, "doc", "the award happened")
    v = build_verdict(store, allegation(), [edge("doc", "C1", "the minister confessed"), edge("doc", "C9", "award")], [])
    assert [r.reason for r in v.rejected_evidence] == ["quote not found verbatim in doc", "unknown sub-claim C9"]
    assert v.by_subclaim[0].status == "unverified"


def test_tampered_blob_is_rejected(store):
    doc = add_doc(store, "doc", "the award happened")
    store.blobs._path(doc.raw_sha256).write_bytes(b"edited later")
    v = build_verdict(store, allegation(), [edge("doc", "C1", "award happened")], [])
    assert "no longer match" in v.rejected_evidence[0].reason


def test_contradicted_prediction_falsifies_hypothesis(store):
    add_doc(store, "ins", "peak 2025: 4 830 MW; 2026: 4 870 MW", kind=SourceKind.STATISTICS)
    add_doc(store, "wx", "no exceptional heat", kind=SourceKind.OSINT)
    edges = [edge("ins", "C2", "2026: 4 870 MW", Relation.CONTRADICTS),
             edge("wx", "C2", "no exceptional heat", Relation.CONTRADICTS)]
    [h] = build_verdict(store, allegation(), edges, []).hypotheses
    assert h.status == "falsified"


def test_financial_anomaly_uses_attested_version_not_retcon(store):
    url = "https://jort.example/award"
    add_doc(store, "v1", "montant de 120 000 000 TND", canonical_url=url, kind=SourceKind.ARCHIVE, day=1)
    add_doc(store, "v2", "montant de 80 000 000 TND", canonical_url=url, kind=SourceKind.OFFICIAL_LIVE, day=9)
    add_doc(store, "bench", "comparable: 60 000 000 TND", kind=SourceKind.ARCHIVE)
    figures = [
        FinancialFigure(doc_id="v1", role=AmountRole.ALLOCATED, amount_tnd=120e6, quote="120 000 000 TND"),
        FinancialFigure(doc_id="v2", role=AmountRole.ALLOCATED, amount_tnd=80e6, quote="80 000 000 TND"),
        FinancialFigure(doc_id="bench", role=AmountRole.BENCHMARK, amount_tnd=60e6, quote="60 000 000 TND"),
        FinancialFigure(doc_id="bench", role=AmountRole.BENCHMARK, amount_tnd=99e6, quote="60 000 000 TND"),
    ]
    v = build_verdict(store, allegation(core=["C3"], financial_subclaim="C3"), [], figures)
    assert v.rejected_evidence[0].reason == "amount not present in quoted text"
    assert v.financial.reference_amount_tnd == 120e6
    assert v.financial.discrepancy_ratio == 0.5
    assert v.financial.flagged
    assert v.by_subclaim[2].status == "supported"
    assert v.verdict == "high_suspicion"


def test_single_origin_anomaly_is_not_flagged(store):
    add_doc(store, "doc", "alloué 120 000 000 TND ; comparable 60 000 000 TND", kind=SourceKind.ARCHIVE)
    figures = [
        FinancialFigure(doc_id="doc", role=AmountRole.ALLOCATED, amount_tnd=120e6, quote="alloué 120 000 000 TND"),
        FinancialFigure(doc_id="doc", role=AmountRole.BENCHMARK, amount_tnd=60e6, quote="comparable 60 000 000 TND"),
    ]
    v = build_verdict(store, allegation(core=["C3"], financial_subclaim="C3"), [], figures)
    assert not v.financial.flagged
    assert v.verdict == "unverified"


def test_exonerating_document_blocks_computed_anomaly(store):
    add_doc(store, "v1", "montant de 120 000 000 TND", kind=SourceKind.ARCHIVE)
    add_doc(store, "bench", "comparable: 60 000 000 TND", kind=SourceKind.ARCHIVE)
    add_doc(store, "audit", "the price reflects a documented 2026 turbine shortage", kind=SourceKind.AUDIT)
    figures = [
        FinancialFigure(doc_id="v1", role=AmountRole.ALLOCATED, amount_tnd=120e6, quote="120 000 000 TND"),
        FinancialFigure(doc_id="bench", role=AmountRole.BENCHMARK, amount_tnd=60e6, quote="60 000 000 TND"),
    ]
    edges = [edge("audit", "C3", "documented 2026 turbine shortage", Relation.CONTRADICTS)]
    v = build_verdict(store, allegation(core=["C3"], financial_subclaim="C3"), edges, figures)
    assert v.financial.flagged
    assert v.by_subclaim[2].status == "contradicted"
    assert v.verdict == "contradicted"
