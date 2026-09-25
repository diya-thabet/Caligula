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

    doc_id: str
    subclaim_id: str
    relation: Relation
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
    confidence: float
    by_subclaim: list[SubClaimResult]
    hypotheses: list[HypothesisResult]
    financial: FinancialAnomaly | None
    retcon_flags: list[RetconFlag]
    rejected_evidence: list[RejectedEvidence]
    weighed: list[WeighedEvidence]
    missing_evidence: list[str]
    disclaimer: str
