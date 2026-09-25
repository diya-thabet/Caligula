from types import SimpleNamespace

from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.application.usecases.intake import admit
from caligula.domain.model.intake import ClaimType, Intake, SubjectType


def analyst(**kw):
    base = dict(claim_type=ClaimType.PROCUREMENT, subject_types=[SubjectType.COMPANY], public_nexus=True,
                documented_act=True, relies_on_sensitive_traits=False,
                involves_leaked_or_classified_material=False, rationale="")
    return SimpleNamespace(classify=lambda text: Intake(**{**base, **kw}))


def test_accept_refuse_and_logging():
    ledger = JsonlLedger()
    assert admit(analyst(), ledger, "c1", "t").proceed
    refused = admit(analyst(claim_type=ClaimType.ESPIONAGE_OR_STATE_SECURITY), ledger, "c2", "t")
    assert not refused.proceed
    assert [e.data["decision"] for e in ledger.entries] == ["accept", "refuse"]


def test_legal_review_paths():
    review = dict(claim_type=ClaimType.FINANCIAL_CRIME_INDICATORS)
    ledger = JsonlLedger()
    assert admit(analyst(**review), ledger, "c", "t", legal_approved_by="Me X").proceed
    assert admit(analyst(**review), ledger, "c", "t", poc=True).proceed
    blocked = admit(analyst(**review), ledger, "c", "t", poc=False)
    assert not blocked.proceed and "lawyer" in blocked.note
    assert [e.action for e in ledger.entries] == ["intake", "legal_approval", "intake", "poc_unreviewed", "intake"]
