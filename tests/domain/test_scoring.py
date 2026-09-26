from caligula.domain.model.claims import Allegation, Hypothesis, SubClaim
from caligula.domain.model.documents import SourceKind
from caligula.domain.model.evidence import AmountRole, EvidenceEdge, FinancialFigure, Relation
from caligula.domain.services.verdict import build_verdict
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
    [c1, *_] = build_verdict(store.corpus(), allegation(), edges, []).by_subclaim
    assert len(c1.supporting_clusters) == 1
    assert c1.support == 0.35  # one news origin, not six
    assert c1.status == "partially_supported"


def test_independent_sources_combine(store):
    add_doc(store, "mirror", "the award happened", kind=SourceKind.FOREIGN_MIRROR)
    add_doc(store, "audit", "audit: the award happened", kind=SourceKind.AUDIT)
    v = build_verdict(store.corpus(), allegation(), [edge("mirror", "C1", "award happened"), edge("audit", "C1", "award happened")], [])
    assert v.by_subclaim[0].status == "supported"
    assert v.by_subclaim[0].support == 0.97


def test_hallucinated_quote_and_unknown_claim_are_rejected(store):
    add_doc(store, "doc", "the award happened")
    v = build_verdict(store.corpus(), allegation(), [edge("doc", "C1", "the minister confessed"), edge("doc", "C9", "award")], [])
    assert [r.reason for r in v.rejected_evidence] == ["quote not found verbatim in doc", "unknown sub-claim C9"]
    assert v.by_subclaim[0].status == "unverified"


def test_tampered_blob_is_rejected(store):
    doc = add_doc(store, "doc", "the award happened")
    store.blobs._path(doc.raw_sha256).write_bytes(b"edited later")
    v = build_verdict(store.corpus(), allegation(), [edge("doc", "C1", "award happened")], [])
    assert "no longer match" in v.rejected_evidence[0].reason


def test_contradicted_prediction_falsifies_hypothesis(store):
    add_doc(store, "ins", "peak 2025: 4 830 MW; 2026: 4 870 MW", kind=SourceKind.STATISTICS)
    add_doc(store, "wx", "no exceptional heat", kind=SourceKind.OSINT)
    edges = [edge("ins", "C2", "2026: 4 870 MW", Relation.CONTRADICTS),
             edge("wx", "C2", "no exceptional heat", Relation.CONTRADICTS)]
    [h] = build_verdict(store.corpus(), allegation(), edges, []).hypotheses
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
    v = build_verdict(store.corpus(), allegation(core=["C3"], financial_subclaim="C3"), [], figures)
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
    v = build_verdict(store.corpus(), allegation(core=["C3"], financial_subclaim="C3"), [], figures)
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
    v = build_verdict(store.corpus(), allegation(core=["C3"], financial_subclaim="C3"), edges, figures)
    assert v.financial.flagged
    assert v.by_subclaim[2].status == "contradicted"
    assert v.verdict == "contradicted"


def test_temporal_checks(store):
    from datetime import UTC, datetime

    claims = allegation()
    claims.subclaims[0].event_date = datetime(2026, 1, 10, tzinfo=UTC)
    claims.subclaims[2].attested_before = datetime(2026, 1, 5, tzinfo=UTC)
    add_doc(store, "early", "outage reported", day=2)
    add_doc(store, "live_late", "project existed", kind=SourceKind.OFFICIAL_LIVE, day=8)
    add_doc(store, "mirror_late", "project existed", kind=SourceKind.FOREIGN_MIRROR, day=8)
    add_doc(store, "backdated", "outage reported", day=12, published_at=datetime(2026, 1, 20, tzinfo=UTC))
    edges = [edge("early", "C1", "outage reported"), edge("live_late", "C3", "project existed"),
             edge("mirror_late", "C3", "project existed"), edge("backdated", "C1", "outage reported")]
    v = build_verdict(store.corpus(), claims, edges, [])
    reasons = [r.reason for r in v.rejected_evidence]
    assert reasons == [
        "early was observed before the event it would report",
        "live_late is an editable source first observed after 2026-01-05",
        "backdated was observed before its stated publication date",
    ]
    assert v.by_subclaim[2].supporting_clusters == [["mirror_late"]]


def test_likelihood_and_confidence_are_separate_statements(store):
    from caligula.domain.services.judgment import estimative_term

    assert [estimative_term(p) for p in (0.03, 0.5, 0.7, 0.9, 0.99)] == [
        "almost no chance", "roughly even chance", "likely", "very likely", "almost certain"]
    add_doc(store, "mirror", "the award happened", kind=SourceKind.FOREIGN_MIRROR)
    add_doc(store, "audit", "audit: the award happened", kind=SourceKind.AUDIT)
    add_doc(store, "blog", "the price was inflated", kind=SourceKind.SOCIAL)
    # Nothing at all on a core sub-claim: we do not guess.
    v = build_verdict(store.corpus(), allegation(core=["C1", "C3"]), [edge("mirror", "C1", "award happened")], [])
    assert (v.likelihood, v.likelihood_term, v.confidence) == (None, "cannot be assessed", "low")
    assert v.confidence_reasons[0] == "C3 has no evidence"
    # Two strong independent origins: very likely, and nothing caps the confidence.
    edges = [edge("mirror", "C1", "award happened"), edge("audit", "C1", "award happened")]
    v = build_verdict(store.corpus(), allegation(), edges, [])
    assert (v.likelihood, v.likelihood_term, v.confidence) == (0.985, "almost certain", "high")
    # A weak source on a second core sub-claim: the likelihood drops and the reasons say why.
    v = build_verdict(store.corpus(), allegation(core=["C1", "C3"]),
                      [*edges, edge("blog", "C3", "price was inflated")], [])
    assert (v.likelihood, v.likelihood_term, v.confidence) == (0.566, "likely", "low")
    assert v.confidence_reasons == ["C3: evidence too weak to settle it"]


def test_each_key_judgment_has_its_own_likelihood_and_confidence(store):
    from caligula.domain.services.judgment import subclaim_judgment

    add_doc(store, "mirror", "the award happened", kind=SourceKind.FOREIGN_MIRROR)
    add_doc(store, "audit", "audit: the award happened", kind=SourceKind.AUDIT)
    add_doc(store, "blog", "the price was inflated", kind=SourceKind.SOCIAL)
    edges = [edge("mirror", "C1", "award happened"), edge("audit", "C1", "award happened"),
             edge("blog", "C3", "price was inflated")]
    a = allegation(core=["C1", "C3"])
    v = build_verdict(store.corpus(), a, edges, [])
    c1, c2, c3 = v.by_subclaim
    assert subclaim_judgment(c1, v, a) == (0.985, "almost certain", "high",
                                           ["strong, independent origins; nothing found against it"])
    assert subclaim_judgment(c1, v, a, unchallenged=["C1"])[2:] == ("moderate", ["C1 supported but never challenged"])
    assert subclaim_judgment(c2, v, a) == (None, "cannot be assessed", "low", ["C2 has no evidence"])
    assert subclaim_judgment(c3, v, a)[2:] == ("low", ["C3: evidence too weak to settle it",
                                                       "one origin decides it: without blog, C3 partially_supported "
                                                       "-> unverified"])
    # When one origin decides a sub-claim, its judgment says so.
    v = build_verdict(store.corpus(), a, [edge("mirror", "C1", "award happened")], [])
    _, _, level, reasons = subclaim_judgment(v.by_subclaim[0], v, a)
    assert level == "moderate" and "one origin decides it: without mirror, C1 supported -> unverified" in reasons
