"""Evidence proposed for sub-claims: quoted edges and monetary figures.

Everything a model proposes is stored here as a *proposal*; nothing counts until
`domain.services.validation` has checked it against the stored documents."""

from __future__ import annotations

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


class RejectedEvidence(BaseModel):
    item: str
    reason: str
