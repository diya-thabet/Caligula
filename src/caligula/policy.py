"""Intake policy: what Caligula will investigate, refuse, or route to a lawyer.

The model classifies a request (`llm.claude.ClaudeInvestigator.classify`);
this module decides. The rules follow from docs/legal.md:

- Investigate documented acts, not predicted intentions. "Could be planning"
  is not a checkable claim; a contract, a payment or a statement is.
- Public bodies, public money, companies and public office holders are in
  scope. Private individuals only through a documented link to those (company
  officer or owner, counterparty of a public contract, author of a public
  statement being checked), never as free-standing targets.
- Espionage, treason and state-security accusations are refused. They are for
  courts and intelligence services, carry the heaviest penalties for the
  accused and for whoever publishes them, and have been used against critics.
  What *can* be checked is documented and lawful to examine: undisclosed
  foreign funding where disclosure is required, foreign state ownership of
  companies holding public contracts.
- Sensitive traits (religion, health, sexuality, ethnicity, political
  opinion as such) are never grounds for suspicion.
"""

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


REFUSED_TYPES = {
    ClaimType.ESPIONAGE_OR_STATE_SECURITY: (
        "Espionage and state-security accusations are outside Caligula's scope: they belong to courts and "
        "intelligence services, and publishing them endangers the accused and the publisher. Caligula can check "
        "documented facts instead, such as undisclosed foreign funding where disclosure is legally required, or "
        "foreign ownership of a company holding public contracts."
    ),
    ClaimType.PRIVATE_LIFE: "Private life is not a matter of public interest for Caligula.",
}
REVIEW_TYPES = {ClaimType.FINANCIAL_CRIME_INDICATORS, ClaimType.UNDISCLOSED_FOREIGN_FUNDING}


def decide(intake: Intake) -> IntakeDecision:
    reasons: list[str] = []
    if intake.claim_type in REFUSED_TYPES:
        return IntakeDecision(Decision.REFUSE, [REFUSED_TYPES[intake.claim_type]])
    if intake.relies_on_sensitive_traits:
        return IntakeDecision(Decision.REFUSE, ["Suspicion based on religion, health, ethnicity, sexuality or "
                                                "political opinion is refused."])
    if not intake.documented_act:
        return IntakeDecision(Decision.REFUSE, ["Only documented acts can be checked. Rephrase as a specific "
                                                "contract, payment, decision or statement."])
    if not intake.public_nexus:
        return IntakeDecision(Decision.REFUSE, ["No link to public money, public office, a public contract or a "
                                                "public statement."])
    if SubjectType.PRIVATE_INDIVIDUAL in intake.subject_types:
        reasons.append("A private individual is involved: limit collection to their documented link to the "
                       "public matter, and have a lawyer confirm proportionality.")
    if intake.claim_type in REVIEW_TYPES:
        reasons.append(f"{intake.claim_type} allegations carry high defamation risk; a lawyer confirms scope first.")
    if intake.involves_leaked_or_classified_material:
        reasons.append("Leaked or classified material: a lawyer decides whether it may be held and used.")
    return IntakeDecision(Decision.LEGAL_REVIEW if reasons else Decision.ACCEPT, reasons)
