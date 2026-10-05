

from caligula.domain.model.intake import ClaimType, Decision, Intake, SubjectType
from caligula.domain.services.intake_policy import decide


def intake(**kw):
    base = dict(claim_type=ClaimType.PROCUREMENT, subject_types=[SubjectType.PUBLIC_BODY, SubjectType.COMPANY],
                public_nexus=True, documented_act=True, relies_on_sensitive_traits=False,
                involves_leaked_or_classified_material=False, rationale="")
    return Intake(**{**base, **kw})


def test_policy_decisions():
    assert decide(intake()).decision == Decision.ACCEPT
    assert decide(intake(claim_type=ClaimType.ESPIONAGE_OR_STATE_SECURITY)).decision == Decision.REFUSE
    assert decide(intake(documented_act=False)).decision == Decision.REFUSE
    assert decide(intake(public_nexus=False)).decision == Decision.REFUSE
    assert decide(intake(relies_on_sensitive_traits=True)).decision == Decision.REFUSE
    review = decide(intake(claim_type=ClaimType.FINANCIAL_CRIME_INDICATORS,
                           subject_types=[SubjectType.COMPANY, SubjectType.PRIVATE_INDIVIDUAL]))
    assert review.decision == Decision.LEGAL_REVIEW and len(review.reasons) == 2
    assert decide(intake(involves_leaked_or_classified_material=True)).decision == Decision.LEGAL_REVIEW
