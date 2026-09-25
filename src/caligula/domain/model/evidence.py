"""Evidence proposed for sub-claims: quoted edges and monetary figures.

Everything a model proposes is stored here as a *proposal*; nothing counts until
`domain.services.validation` has checked it against the stored documents."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


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


class AbsenceFinding(BaseModel):
    """A proper search of a register that found nothing. Its weight is the
    register's completeness, reduced when no capture of the empty result was
    stored (then only our word proves the search)."""

    subclaim_id: str
    relation: Relation  # what the absence means for the sub-claim
    register_id: str  # key of `domain.model.registers.REGISTERS`
    query: str
    searched_at: datetime
    window_start: datetime | None = None
    window_end: datetime | None = None
    doc_id: str | None = None  # stored capture of the empty result page
    note: str = ""


class RejectedEvidence(BaseModel):
    item: str
    reason: str
