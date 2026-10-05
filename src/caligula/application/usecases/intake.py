"""Admit or refuse a request before any agent runs, and log the decision."""

from __future__ import annotations

from dataclasses import dataclass

from caligula.application.ports.llm import ClaimAnalyst
from caligula.application.ports.storage import Ledger
from caligula.domain.model.intake import Decision, Intake, IntakeDecision
from caligula.domain.services.intake_policy import decide

POC_NOTE = "legal review skipped in PoC mode; output is internal, not for publication"


@dataclass(frozen=True)
class Admission:
    intake: Intake
    decision: IntakeDecision
    proceed: bool
    note: str | None = None  # why it proceeds or stops, when not a plain accept


def admit(
    analyst: ClaimAnalyst,
    ledger: Ledger,
    case_id: str,
    text: str,
    legal_approved_by: str | None = None,
    poc: bool = True,
) -> Admission:
    intake = analyst.classify(text)
    decision = decide(intake)
    ledger.append("intake", "caligula", case_id=case_id, decision=decision.decision.value,
                  reasons=decision.reasons, intake=intake.model_dump(mode="json"))
    if decision.decision == Decision.REFUSE:
        return Admission(intake, decision, proceed=False, note="refused by policy")
    if decision.decision == Decision.ACCEPT:
        return Admission(intake, decision, proceed=True)
    if legal_approved_by:
        ledger.append("legal_approval", legal_approved_by, case_id=case_id, scope=text)
        return Admission(intake, decision, proceed=True, note=f"scope approved by {legal_approved_by}")
    if poc:
        ledger.append("poc_unreviewed", "caligula", case_id=case_id, note=POC_NOTE)
        return Admission(intake, decision, proceed=True, note="PoC mode: proceeding without legal review; "
                                                              "output is internal only")
    return Admission(intake, decision, proceed=False,
                     note="a lawyer must approve the scope first (re-run with --legal-approved NAME)")
