"""A request to investigate, as described by the intake classifier."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel


class SubjectType(StrEnum):
    PUBLIC_BODY = "public_body"
    PUBLIC_OFFICIAL = "public_official"  # elected, appointed or senior civil servant, in that capacity
    COMPANY = "company"
    ASSOCIATION = "association"
    PRIVATE_INDIVIDUAL = "private_individual"
    UNKNOWN = "unknown"


class ClaimType(StrEnum):
    FACTUAL_STATEMENT = "factual_statement"  # "unemployment fell to 12%"
    PUBLIC_FUNDS = "public_funds"  # misuse, diversion, waste
    PROCUREMENT = "procurement"
    CONFLICT_OF_INTEREST = "conflict_of_interest"
    FINANCIAL_CRIME_INDICATORS = "financial_crime_indicators"  # fraud schemes, laundering typologies
    RECORD_TAMPERING = "record_tampering"
    UNDISCLOSED_FOREIGN_FUNDING = "undisclosed_foreign_funding"
    ESPIONAGE_OR_STATE_SECURITY = "espionage_or_state_security"
    PRIVATE_LIFE = "private_life"
    OTHER = "other"


class Intake(BaseModel):
    """What the model extracted from a request; the decision is made in code."""

    claim_type: ClaimType
    subject_types: list[SubjectType]
    public_nexus: bool  # public money, public office, public contract, or a public statement
    documented_act: bool  # a specific past or ongoing act, not a prediction or a profile
    relies_on_sensitive_traits: bool
    involves_leaked_or_classified_material: bool
    rationale: str


class Decision(StrEnum):
    ACCEPT = "accept"
    LEGAL_REVIEW = "legal_review"  # a lawyer signs off before any agent runs
    REFUSE = "refuse"


@dataclass(frozen=True)
class IntakeDecision:
    decision: Decision
    reasons: list[str]
