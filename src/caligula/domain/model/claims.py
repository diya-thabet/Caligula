"""Allegations, their sub-claims and competing hypotheses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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
