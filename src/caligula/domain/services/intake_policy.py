"""Intake policy: what Caligula will investigate, refuse, or route to a lawyer.

The model classifies a request (`ClaimAnalyst.classify`);
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

from caligula.domain.model.intake import ClaimType, Decision, Intake, IntakeDecision, SubjectType

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
