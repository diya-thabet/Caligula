"""Assemble the structured verdict from validated evidence.

The engine never outputs "corruption proven". The strongest verdict is
`high_suspicion`: every core sub-claim is supported by independent evidence, a
deterministic signal (financial anomaly or rewritten official record) is
present, and no innocent explanation is confirmed by the evidence. Attributing it to a person is out of scope for the engine and requires
human review with a right of reply.
"""

from __future__ import annotations

from caligula.domain.model.claims import Allegation, HypothesisKind
from caligula.domain.model.documents import Corpus
from caligula.domain.model.evidence import AbsenceFinding, EvidenceEdge, FinancialFigure, RejectedEvidence, Relation
from caligula.domain.model.verdict import SubClaimResult, Verdict, WeighedEvidence
from caligula.domain.services.absence import validate_absences, weigh_absences
from caligula.domain.services.ach import build_matrices
from caligula.domain.services.judgment import confidence, likelihood
from caligula.domain.services.provenance import group_by_cluster, origin_clusters
from caligula.domain.services.retcon import detect_retcons
from caligula.domain.services.scoring import (
    CONTRADICTED,
    DEFAULT_PARAMS,
    SUPPORTED,
    Params,
    detect_financial_anomaly,
    evaluate_hypotheses,
    score_subclaims,
    weigh_edges,
)
from caligula.domain.services.sensitivity import dependencies
from caligula.domain.services.validation import validate_edges, validate_figures

DISCLAIMER = (
    "Evidence assessment, not a finding of guilt. Scores use uncalibrated priors. "
    "No individual is named by the engine; any attribution requires human review "
    "and a right of reply."
)


def build_verdict(
    corpus: Corpus,
    allegation: Allegation,
    edges: list[EvidenceEdge],
    figures: list[FinancialFigure],
    params: Params = DEFAULT_PARAMS,
    absences: list[AbsenceFinding] | None = None,
    sensitivity: bool = True,
) -> Verdict:
    absences = absences or []
    verdict = _assess(corpus, allegation, edges, figures, absences, params)
    if not sensitivity:
        return verdict
    clusters = origin_clusters(corpus.documents)
    origins: dict[str, set[str]] = {}
    for item in verdict.weighed:
        origins.setdefault(item.cluster, set()).add(item.doc_id)
    for fig in verdict.financial.figures if verdict.financial else []:
        origins.setdefault(clusters[fig.doc_id], set()).add(fig.doc_id)

    def without(cluster: str) -> Verdict:
        kept = {i: d for i, d in corpus.documents.items() if clusters[i] != cluster}
        return _assess(
            Corpus(kept, corpus.intact), allegation,
            [e for e in edges if e.doc_id in kept], [f for f in figures if f.doc_id in kept],
            [a for a in absences if (a.doc_id in kept if a.doc_id else f"absence:{a.register_id}" != cluster)],
            params)

    verdict.depends_on = dependencies(verdict, ((c, sorted(m)) for c, m in origins.items()), without)
    level, reasons = confidence(verdict, allegation, params)
    verdict.confidence, verdict.confidence_reasons = level.value, reasons
    return verdict


def _assess(
    corpus: Corpus,
    allegation: Allegation,
    edges: list[EvidenceEdge],
    figures: list[FinancialFigure],
    absences: list[AbsenceFinding],
    params: Params,
) -> Verdict:
    edges, rejected_edges = validate_edges(corpus, allegation, edges)
    figures, rejected_figures = validate_figures(corpus, figures)
    absences, rejected_absences = validate_absences(corpus, allegation, absences)
    rejected: list[RejectedEvidence] = rejected_edges + rejected_figures + rejected_absences

    retcons = detect_retcons(corpus.documents.values())
    clusters = origin_clusters(corpus.documents)
    weighed = weigh_edges(allegation, edges, dict(corpus.documents), retcons, clusters, params)
    weighed += weigh_absences(absences, clusters, params)
    subclaims = score_subclaims(allegation, weighed, params)

    financial = detect_financial_anomaly(figures, retcons, clusters, params)
    matrix_items = list(weighed)
    if financial and allegation.financial_subclaim:
        figure_clusters = group_by_cluster({f.doc_id for f in financial.figures}, clusters)
        result = subclaims[allegation.financial_subclaim]
        if _apply_financial(result, financial.flagged, figure_clusters, params.financial_check_weight):
            matrix_items.append(WeighedEvidence(
                doc_id="financial-check", subclaim_id=result.id, relation=Relation.SUPPORTS, kind="financial",
                cluster="financial-check", weight=params.financial_check_weight))

    hypotheses = evaluate_hypotheses(allegation, subclaims)
    verdict = _overall(allegation, subclaims, bool(financial and financial.flagged), bool(retcons))
    innocent = {h.id for h in allegation.hypotheses if h.kind == HypothesisKind.INNOCENT}
    if verdict == "high_suspicion" and any(h.status == "consistent" for h in hypotheses if h.id in innocent):
        # The facts hold, but a lawful explanation of them does too.
        verdict = "partially_supported"

    # Ask for more wherever a sub-claim is unsettled or rests on a single origin.
    missing = [
        f"{c.id}: {q}"
        for c in allegation.subclaims
        if _independent_origins(subclaims[c.id]) < 2
        for q in c.verification_questions
    ]
    p, term = likelihood(allegation, subclaims)
    v = Verdict(
        allegation_id=allegation.id,
        verdict=verdict,
        likelihood=p,
        likelihood_term=term,
        confidence="",
        confidence_reasons=[],
        by_subclaim=list(subclaims.values()),
        hypotheses=hypotheses,
        ach=build_matrices(allegation, matrix_items),
        financial=financial,
        retcon_flags=retcons,
        rejected_evidence=rejected,
        weighed=weighed,
        missing_evidence=missing,
        disclaimer=DISCLAIMER,
    )
    level, reasons = confidence(v, allegation, params)
    v.confidence, v.confidence_reasons = level.value, reasons
    return v


def _independent_origins(result: SubClaimResult) -> int:
    if result.status == SUPPORTED:
        return len(result.supporting_clusters)
    if result.status == CONTRADICTED:
        return len(result.contradicting_clusters)
    return 0


def _apply_financial(result: SubClaimResult, flagged: bool, figure_clusters: list[list[str]], weight: float) -> bool:
    """Settle the financial sub-claim from the deterministic check. Returns whether it did."""
    # An exonerating document (contradicting edge) still blocks the computed result.
    if flagged and result.status != CONTRADICTED and not result.contradicting_clusters:
        result.status = SUPPORTED
        result.support = max(result.support, weight)
        result.supporting_clusters = figure_clusters
        return True
    return False


def _overall(
    allegation: Allegation,
    subclaims: dict[str, SubClaimResult],
    anomaly: bool,
    retcon: bool,
) -> str:
    core = [subclaims[i] for i in allegation.core_subclaims if i in subclaims]
    if not core:
        return "unverified"
    if any(c.status == CONTRADICTED for c in core):
        return "contradicted"
    supported = sum(c.status == SUPPORTED for c in core)
    if supported == len(core) and (anomaly or retcon):
        return "high_suspicion"
    if supported:
        return "partially_supported"
    return "unverified"
