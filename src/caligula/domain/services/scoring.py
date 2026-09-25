"""Evidence math. No LLM output reaches this module unvalidated, and no number
here comes from the LLM.

The weights are priors, not calibrated values. They must be fitted against a
labelled set of past cases before any score is published (see docs/architecture.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from caligula.domain.model.claims import Allegation
from caligula.domain.model.documents import Document, SourceKind
from caligula.domain.model.evidence import AmountRole, EvidenceEdge, FinancialFigure, Relation
from caligula.domain.model.registers import REGISTERS
from caligula.domain.model.verdict import (
    FinancialAnomaly,
    HypothesisResult,
    RetconFlag,
    SubClaimResult,
    WeighedEvidence,
)
from caligula.domain.services.interest import Interest, interest, role_of

# Inverse to how easily the accused party can silently change the source.
SOURCE_WEIGHTS: dict[SourceKind, float] = {
    SourceKind.AUDIT: 0.85,
    SourceKind.FOREIGN_MIRROR: 0.80,
    SourceKind.ARCHIVE: 0.75,
    SourceKind.STATISTICS: 0.70,
    SourceKind.OSINT: 0.70,
    SourceKind.CONTRIBUTOR: 0.60,
    SourceKind.OFFICIAL_LIVE: 0.50,
    SourceKind.NEWS: 0.35,
    SourceKind.SOCIAL: 0.15,
}
SUPPORTED, CONTRADICTED, CONTESTED = "supported", "contradicted", "contested"
PARTIAL, UNVERIFIED = "partially_supported", "unverified"


@dataclass(frozen=True)
class Params:
    """Every tunable number in one place, so `calibration.py` can fit them."""

    weights: dict[SourceKind, float] = field(default_factory=lambda: dict(SOURCE_WEIGHTS))
    # A version that diverges from an earlier attested copy is itself suspect.
    retconned_penalty: float = 0.3
    strong: float = 0.7
    weak: float = 0.3
    anomaly_ratio: float = 0.20
    anomaly_min_clusters: int = 2
    # Support given to the financial sub-claim when the deterministic check flags it.
    financial_check_weight: float = 0.9
    # A party conceding a point against its own interest: at least this weight.
    against_interest_floor: float = 0.8
    # A party asserting a point that serves it: its weight is multiplied by this.
    self_serving_factor: float = 0.5
    # Absence of a record: weight = the register's completeness, times this
    # factor when no capture of the empty search result was stored.
    completeness: dict[str, float] = field(default_factory=lambda: {k: r.completeness for k, r in REGISTERS.items()})
    absence_uncaptured_factor: float = 0.5

    def with_(self, **changes) -> Params:
        return replace(self, **changes)


DEFAULT_PARAMS = Params()


def weigh_edges(
    allegation: Allegation,
    edges: list[EvidenceEdge],
    documents: dict[str, Document],
    retcons: list[RetconFlag],
    clusters: dict[str, str],
    params: Params = DEFAULT_PARAMS,
) -> list[WeighedEvidence]:
    """Weight of each validated edge: source kind, then the publisher's interest
    in this particular point, then the penalty for a rewritten version."""
    retconned = {f.later_doc_id for f in retcons}
    out = []
    for e in edges:
        doc = documents[e.doc_id]
        stake = interest(role_of(doc.publisher, allegation.parties), allegation.bearing_of(e.subclaim_id), e.relation)
        w = params.weights[doc.source_kind]
        if stake == Interest.AGAINST_INTEREST:
            w = max(w, params.against_interest_floor)
        elif stake == Interest.SELF_SERVING:
            w *= params.self_serving_factor
        if doc.id in retconned:
            w *= params.retconned_penalty
        out.append(WeighedEvidence(doc_id=e.doc_id, subclaim_id=e.subclaim_id, relation=e.relation,
                                   cluster=clusters[e.doc_id], weight=round(w, 4), interest=stake.value))
    return out


def _noisy_or(cluster_weights: list[float]) -> float:
    p_none = 1.0
    for w in cluster_weights:
        p_none *= 1.0 - w
    return 1.0 - p_none


def _by_cluster(items: list[WeighedEvidence]) -> dict[str, list[WeighedEvidence]]:
    groups: dict[str, list[WeighedEvidence]] = {}
    for item in items:
        groups.setdefault(item.cluster, []).append(item)
    return groups


def score_subclaims(
    allegation: Allegation,
    items: list[WeighedEvidence],
    params: Params = DEFAULT_PARAMS,
) -> dict[str, SubClaimResult]:
    results = {}
    for claim in allegation.subclaims:
        mine = [i for i in items if i.subclaim_id == claim.id]
        sup = _by_cluster([i for i in mine if i.relation == Relation.SUPPORTS])
        con = _by_cluster([i for i in mine if i.relation == Relation.CONTRADICTS])
        # One independent origin counts once, at the weight of its best item.
        support = _noisy_or([max(i.weight for i in g) for g in sup.values()])
        contra = _noisy_or([max(i.weight for i in g) for g in con.values()])
        results[claim.id] = SubClaimResult(
            id=claim.id,
            statement=claim.statement,
            status=_status(support, contra, params),
            support=round(support, 3),
            contradiction=round(contra, 3),
            supporting_clusters=[sorted({i.doc_id for i in g}) for g in sup.values()],
            contradicting_clusters=[sorted({i.doc_id for i in g}) for g in con.values()],
            qualifying_docs=sorted({i.doc_id for i in mine if i.relation == Relation.QUALIFIES}),
        )
    return results


def _status(support: float, contra: float, p: Params) -> str:
    if support >= p.strong and contra < p.weak:
        return SUPPORTED
    if contra >= p.strong and support < p.weak:
        return CONTRADICTED
    if support >= p.weak and contra >= p.weak:
        return CONTESTED
    if support > 0 or contra > 0:
        return PARTIAL
    return UNVERIFIED


def evaluate_hypotheses(
    allegation: Allegation, subclaims: dict[str, SubClaimResult]
) -> list[HypothesisResult]:
    known = {SUPPORTED: True, CONTRADICTED: False}
    out = []
    for hyp in allegation.hypotheses:
        reasons, falsified, open_ = [], False, False
        for claim_id, predicted in hyp.predicts.items():
            observed = known.get(subclaims[claim_id].status)
            if observed is None:
                open_ = True
                reasons.append(f"{claim_id} is {subclaims[claim_id].status}")
            elif observed != predicted:
                falsified = True
                reasons.append(f"predicts {claim_id}={predicted}, evidence says {observed}")
            else:
                reasons.append(f"{claim_id}={observed} as predicted")
        status = "falsified" if falsified else "open" if open_ else "consistent"
        out.append(HypothesisResult(id=hyp.id, statement=hyp.statement, status=status, reasons=reasons))
    return out


def detect_financial_anomaly(
    figures: list[FinancialFigure],
    retcons: list[RetconFlag],
    clusters: dict[str, str],
    params: Params = DEFAULT_PARAMS,
) -> FinancialAnomaly | None:
    """discrepancy = committed amount - what the work can be shown to cost.

    Figures from a version that was rewritten after an earlier attested copy
    are excluded; the attested copy is used instead.
    """
    retconned = {f.later_doc_id for f in retcons}
    usable = [f for f in figures if f.doc_id not in retconned]

    def pick(role: AmountRole) -> list[FinancialFigure]:
        return [f for f in usable if f.role == role]

    reference = pick(AmountRole.ALLOCATED) or pick(AmountRole.DISBURSED)
    spend = pick(AmountRole.PROVEN_SPEND) or pick(AmountRole.BENCHMARK)
    if not reference or not spend:
        return None
    ref = max(reference, key=lambda f: f.amount_tnd)
    if spend[0].role == AmountRole.PROVEN_SPEND:
        proven = sum(f.amount_tnd for f in spend)
    else:
        # Several comparables: take the most expensive, so doubt favours the accused.
        spend = [max(spend, key=lambda f: f.amount_tnd)]
        proven = spend[0].amount_tnd
    discrepancy = ref.amount_tnd - proven
    ratio = discrepancy / ref.amount_tnd
    used = [ref, *spend, *(f for f in pick(AmountRole.DISBURSED) if f is not ref)]
    independent = len({clusters[f.doc_id] for f in used})
    return FinancialAnomaly(
        reference_role=ref.role,
        reference_amount_tnd=ref.amount_tnd,
        proven_spend_tnd=proven,
        discrepancy_tnd=discrepancy,
        discrepancy_ratio=round(ratio, 3),
        independent_clusters=independent,
        flagged=ratio > params.anomaly_ratio and independent >= params.anomaly_min_clusters,
        figures=used,
    )
