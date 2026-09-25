"""Allegations, their sub-claims and competing hypotheses."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from caligula.domain.model.evidence import Relation


class Bearing(StrEnum):
    """What a sub-claim being true means for the party whose conduct is at issue."""

    AGAINST = "against"  # incriminating: "the award skipped the tender"
    FOR = "for"  # exculpating: "an emergency decree justified the direct award"
    NEUTRAL = "neutral"  # context: "an outage occurred"


class PartyRole(StrEnum):
    ACCUSED = "accused"  # the body, company or office whose conduct is at issue
    COMPLAINANT = "complainant"  # who made or pushes the allegation (rival, opponent, activist)


class Party(BaseModel):
    """A party with a stake in the outcome. Documents it publishes are weighed
    by whether they serve or hurt its interest (see `domain.services.interest`)."""

    name: str
    role: PartyRole
    aliases: list[str] = Field(default_factory=list)


class ExpectedRecord(BaseModel):
    """An observable implication: a record that should exist in a register if
    the sub-claim were false (or true). Searching for it is a test; not finding
    it after a proper search is scored evidence (`domain.services.absence`)."""

    description: str  # "TUNEPS tender notice for market 2026-017, before the award"
    register_id: str  # key of `domain.model.registers.REGISTERS`
    absence_means: Relation  # what finding nothing means for the sub-claim


class SubClaim(BaseModel):
    id: str
    statement: str
    verification_questions: list[str] = Field(default_factory=list)
    # A document seen before the event cannot report it happening.
    event_date: datetime | None = None
    # For "X existed before date D": a page the accused can edit only counts if
    # it was observed before D (otherwise it may have been backdated).
    attested_before: datetime | None = None
    # None: core sub-claims are incriminating, the others neutral.
    bearing: Bearing | None = None
    expected_records: list[ExpectedRecord] = Field(default_factory=list)


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
    parties: list[Party] = Field(default_factory=list)

    def bearing_of(self, subclaim_id: str) -> Bearing:
        claim = next(c for c in self.subclaims if c.id == subclaim_id)
        if claim.bearing is not None:
            return claim.bearing
        return Bearing.AGAINST if subclaim_id in self.core_subclaims else Bearing.NEUTRAL
