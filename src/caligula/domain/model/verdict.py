"""What the engine concludes, and why."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from caligula.domain.model.evidence import AmountRole, FinancialFigure, RejectedEvidence, Relation


class FieldChange(BaseModel):
    kind: str
    removed: list[str]
    added: list[str]


class RetconFlag(BaseModel):
    canonical_url: str
    earlier_doc_id: str
    later_doc_id: str
    earlier_observed_at: datetime
    later_observed_at: datetime
    changes: list[FieldChange]
    # OCR can misread digits: a flag on OCR text is a lead until a human checks the scan.
    needs_review: bool = False


class WeighedEvidence(BaseModel):
    """A validated evidence item as the scoring counted it."""

    doc_id: str  # for an absence without a stored capture: "absence:<register>"
    subclaim_id: str
    relation: Relation
    kind: str = "edge"  # edge (a quote) | absence (a search that found nothing)
    cluster: str  # origin cluster: items sharing one count once
    weight: float
    interest: str = "none"  # see domain.services.interest.Interest


class SubClaimResult(BaseModel):
    id: str
    statement: str
    status: str
    support: float
    contradiction: float
    supporting_clusters: list[list[str]]
    contradicting_clusters: list[list[str]]
    qualifying_docs: list[str]  # conditions or innocent explanations to weigh by hand


class HypothesisResult(BaseModel):
    id: str
    statement: str
    status: str  # falsified / consistent / open
    reasons: list[str]


class AchRow(BaseModel):
    """One independent origin's evidence on one sub-claim, rated against every
    competing hypothesis: C consistent, I inconsistent, N no prediction."""

    subclaim_id: str
    relation: Relation
    kind: str  # edge | absence | financial
    doc_ids: list[str]
    weight: float
    ratings: dict[str, str]
    # At least two hypotheses predict this sub-claim and disagree: the row helps tell them apart.
    diagnostic: bool


class AchMatrix(BaseModel):
    """Analysis of competing hypotheses for one set of hypotheses that make
    predictions about the same sub-claims."""

    hypotheses: list[str]
    rows: list[AchRow]
    inconsistency: dict[str, float]  # weight of the evidence against each hypothesis
    ranking: list[str]  # tested hypotheses, least evidence against first
    untested: list[str]  # no evidence yet on anything they predict: neither likely nor unlikely


class Dependency(BaseModel):
    """What the conclusion loses if one independent origin turns out to be wrong."""

    origin: list[str]  # the documents (or searches) sharing that origin
    changes: list[str]  # e.g. "verdict high_suspicion -> partially_supported", "C5 supported -> unverified"
    changes_verdict: bool


class FinancialAnomaly(BaseModel):
    reference_role: AmountRole
    reference_amount_tnd: float
    proven_spend_tnd: float
    discrepancy_tnd: float
    discrepancy_ratio: float
    independent_clusters: int
    flagged: bool
    figures: list[FinancialFigure]


class Verdict(BaseModel):
    allegation_id: str
    verdict: str
    # Probability that every core sub-claim is true, in ICD 203 words; None when it cannot be assessed.
    likelihood: float | None
    likelihood_term: str
    # How solid the basis is (low / moderate / high), and every weakness that capped it.
    confidence: str
    confidence_reasons: list[str]
    by_subclaim: list[SubClaimResult]
    hypotheses: list[HypothesisResult]
    ach: list[AchMatrix]
    financial: FinancialAnomaly | None
    retcon_flags: list[RetconFlag]
    rejected_evidence: list[RejectedEvidence]
    weighed: list[WeighedEvidence]
    # Filled by the sensitivity analysis: origins whose removal changes something, most critical first.
    depends_on: list[Dependency] = []
    missing_evidence: list[str]
    disclaimer: str
