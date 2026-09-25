"""Domain model for an investigation case.

Everything the LLM produces (sub-claims, evidence edges, extracted amounts) is
stored here as a *proposal*. Nothing is trusted until `validate.py` has checked
it against the stored documents.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceKind(StrEnum):
    """Where a document came from. Trust is inverse to how easily the
    publisher can silently change it (see `scoring.SOURCE_WEIGHTS`)."""

    OFFICIAL_LIVE = "official_live"  # current ministry / JORT / TUNEPS page: mutable by the accused
    ARCHIVE = "archive"  # Wayback / archive.today / Common Crawl snapshot
    FOREIGN_MIRROR = "foreign_mirror"  # World Bank, EU TED, EBRD records of the same money
    AUDIT = "audit"  # Cour des comptes, IMF/EBRD reviews
    STATISTICS = "statistics"  # INS, grid operator datasets
    CONTRIBUTOR = "contributor"  # hashed upload from a field contributor
    OSINT = "osint"  # satellite, night lights, weather
    NEWS = "news"
    SOCIAL = "social"


class Document(BaseModel):
    id: str
    # Versions of the same logical document share a canonical_url
    # (e.g. the live JORT page and its Wayback snapshot).
    canonical_url: str
    url: str
    source_kind: SourceKind
    publisher: str
    title: str = ""
    published_at: datetime | None = None
    # When the content is attested to have existed: archive capture time,
    # contributor upload time, or our own first fetch.
    observed_at: datetime
    raw_sha256: str
    text_sha256: str
    text: str
    extraction: str = "plain"  # plain | pdf_text | ocr
    cites: list[str] = Field(default_factory=list)  # document ids this one cites
    derived_from: list[str] = Field(default_factory=list)  # document ids this one copies/rewrites


class SubClaim(BaseModel):
    id: str
    statement: str
    verification_questions: list[str] = Field(default_factory=list)
    # A document seen before the event cannot report it happening.
    event_date: datetime | None = None
    # For "X existed before date D": a page the accused can edit only counts if
    # it was observed before D (otherwise it may have been backdated).
    attested_before: datetime | None = None


class Hypothesis(BaseModel):
    id: str
    statement: str
    # sub-claim id -> the truth value this hypothesis predicts for it.
    predicts: dict[str, bool]


class Allegation(BaseModel):
    id: str
    text: str
    subject: str
    claim_type: str
    subclaims: list[SubClaim]
    hypotheses: list[Hypothesis]
    # Sub-claims that must all hold for the allegation to reach `high_suspicion`.
    core_subclaims: list[str]
    # Sub-claim settled by the deterministic financial anomaly check, if any.
    financial_subclaim: str | None = None


class Relation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    QUALIFIES = "qualifies"


class EvidenceEdge(BaseModel):
    doc_id: str
    subclaim_id: str
    relation: Relation
    quote: str  # must appear verbatim (after normalization) in the document
    rationale: str = ""


class AmountRole(StrEnum):
    ALLOCATED = "allocated"
    DISBURSED = "disbursed"
    BENCHMARK = "benchmark"
    PROVEN_SPEND = "proven_spend"


class FinancialFigure(BaseModel):
    doc_id: str
    role: AmountRole
    amount_tnd: float
    quote: str


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


class RejectedEvidence(BaseModel):
    item: str
    reason: str


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
    missing_evidence: list[str]
    disclaimer: str
