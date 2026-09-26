"""Cases: the lifecycle an investigator drives, with a person deciding at each checkpoint.

    open ─ intake ─┬─ refused
                   ├─ awaiting_legal_review ─ approve_legal ─┐
                   └─────────────────────────────────────────┴─ preparing (decompose, plan)
    awaiting_plan_approval ─ edit_plan* ─ approve_plan ─ running ⇄ paused ─ in_review ─ sign_off ─ approved
    (stop ends a run early; a failure at any step leaves the case "failed" with its error)

The agents investigate and propose; a person approves the plan, decides on
any wider scope, and signs off the result. Every decision goes to the case's
ledger with who took it. Long steps (model calls, the investigation itself)
run in the background; their progress is published on the case's events.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from caligula.application.cases.events import EventLog, ObservedLedger
from caligula.application.evidence_store import EvidenceStore
from caligula.application.investigation.plan import Plan, PlanDraft, PlannedTask, normalize_plan
from caligula.application.investigation.suspicions import Suspicion
from caligula.application.investigation.team import InvestigationTeam, TeamResult
from caligula.application.investigation.workspace import Connectors, Mode, Workspace
from caligula.application.ports.llm import ClaimAnalyst
from caligula.application.ports.storage import Ledger
from caligula.application.usecases.decompose import decompose_case
from caligula.application.usecases.intake import admit
from caligula.domain.model.claims import Allegation
from caligula.domain.model.intake import Decision, Intake, IntakeDecision
from caligula.domain.model.verdict import Verdict


class CaseStatus(StrEnum):
    REFUSED = "refused"
    AWAITING_LEGAL_REVIEW = "awaiting_legal_review"
    PREPARING = "preparing"
    AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"
    RUNNING = "running"
    PAUSED = "paused"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    FAILED = "failed"


class CaseError(Exception):
    """A request the case cannot take in its current state."""


class NotFound(CaseError):
    pass


@dataclass
class SignOff:
    by: str
    at: datetime
    note: str


@dataclass
class Case:
    id: str
    claim: str
    mode: Mode
    poc: bool
    created_by: str
    created_at: datetime
    ledger: Ledger
    events: EventLog
    status: CaseStatus = CaseStatus.PREPARING
    note: str = ""  # why the case is where it is (refusal reasons, the error...)
    intake: Intake | None = None
    decision: IntakeDecision | None = None
    allegation: Allegation | None = None
    added_by_code: list[str] = field(default_factory=list)  # innocent explanations code added
    draft: PlanDraft | None = None
    plan: Plan | None = None
    workspace: Workspace | None = None
    team: InvestigationTeam | None = None
    result: TeamResult | None = None
    verdict: Verdict | None = None
    review: str | None = None  # the reviewer's summary, as written
    sign_off: SignOff | None = None

    @property
    def last_activity(self) -> datetime:
        last = self.events.last
        return last.at if last else self.created_at

    def awaiting_scope(self) -> list[Suspicion]:
        return [s for s in (self.workspace.suspicions if self.workspace else []) if s.status == "awaiting_scope"]


@dataclass
class Engine:
    """What running cases needs: the analyst (intake, decomposition, planning, and judge if it
    can), a way to build a team for a case, the evidence store and live sources."""

    analyst: ClaimAnalyst
    new_team: Callable[[Callable[[str, str], None]], InvestigationTeam]  # given the case's event callback
    store: EvidenceStore
    connectors: Connectors = field(default_factory=Connectors)


def _in_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True).start()


class CaseService:
    def __init__(self, engine: Engine | None, new_ledger: Callable[[str], Ledger],
                 background: Callable[[Callable[[], None]], None] = _in_thread,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.engine = engine  # None: the service only holds cases imported as they are
        self.new_ledger = new_ledger
        self.background = background
        self.clock = clock
        self.cases: dict[str, Case] = {}
        self.lock = threading.RLock()

    # --- reading ------------------------------------------------------------------

    def get(self, case_id: str) -> Case:
        case = self.cases.get(case_id)
        if case is None:
            raise NotFound(f"no case {case_id}")
        return case

    def list(self) -> list[Case]:
        return sorted(self.cases.values(), key=lambda c: c.created_at, reverse=True)

    # --- lifecycle ----------------------------------------------------------------

    def open(self, claim: str, by: str, mode: Mode = Mode.INVESTIGATE, poc: bool = True,
             case_id: str | None = None, legal_approved_by: str | None = None) -> Case:
        engine = self._engine()
        if not claim.strip():
            raise CaseError("describe the claim to investigate")
        case = self._new_case(case_id, claim, by, mode, poc)

        def work() -> None:
            admission = admit(engine.analyst, case.ledger, case.id, claim, legal_approved_by, poc)
            case.intake, case.decision = admission.intake, admission.decision
            if admission.decision.decision == Decision.REFUSE:
                self._status(case, CaseStatus.REFUSED, "; ".join(admission.decision.reasons))
            elif not admission.proceed:
                self._status(case, CaseStatus.AWAITING_LEGAL_REVIEW, admission.note or "")
            else:
                self._prepare(case, admission.note or "")

        self._run(case, work)
        return case

    def approve_legal(self, case_id: str, by: str, note: str = "") -> Case:
        case = self._expect(case_id, CaseStatus.AWAITING_LEGAL_REVIEW)
        case.ledger.append("legal_approval", by, case_id=case.id, scope=case.claim, note=note)
        self._status(case, CaseStatus.PREPARING, f"scope approved by {by}")
        self._run(case, lambda: self._prepare(case, f"scope approved by {by}"))
        return case

    def edit_plan(self, case_id: str, tasks: list[PlannedTask], by: str) -> Case:
        """Replace the planned tasks. Code checks the edit as it checks the planner's draft, so
        the guarantees hold (two kinds of source per core sub-claim, a test per innocent
        explanation, a search per expected record); what it re-adds is listed in plan.fixes."""
        case = self._expect(case_id, CaseStatus.AWAITING_PLAN_APPROVAL)
        case.draft = case.draft.model_copy(update={"tasks": tasks})
        case.plan = self._normalize(case)
        case.ledger.append("plan_edited", by, tasks=len(tasks), fixes=case.plan.fixes)
        self._status(case, CaseStatus.AWAITING_PLAN_APPROVAL, f"plan edited by {by}")
        return case

    def approve_plan(self, case_id: str, by: str) -> Case:
        case = self._expect(case_id, CaseStatus.AWAITING_PLAN_APPROVAL)
        case.ledger.append("plan_approved", by, tasks=[t.id for t in case.plan.tasks], budgets=case.plan.budgets)
        self._status(case, CaseStatus.RUNNING, f"plan approved by {by}")

        def work() -> None:
            result = case.team.run(case.workspace, plan=case.plan)
            case.result, case.verdict, case.review = result, result.verdict, result.review
            self._status(case, CaseStatus.IN_REVIEW, result.stop_reason)

        self._run(case, work)
        return case

    def pause(self, case_id: str, by: str) -> Case:
        case = self._expect(case_id, CaseStatus.RUNNING)
        case.workspace.control.pause()
        case.ledger.append("paused", by)
        self._status(case, CaseStatus.PAUSED, f"paused by {by}")
        return case

    def resume(self, case_id: str, by: str) -> Case:
        case = self._expect(case_id, CaseStatus.PAUSED)
        case.ledger.append("resumed", by)
        self._status(case, CaseStatus.RUNNING, f"resumed by {by}")
        case.workspace.control.resume()
        return case

    def stop(self, case_id: str, by: str) -> Case:
        case = self._expect(case_id, CaseStatus.RUNNING, CaseStatus.PAUSED)
        case.ledger.append("stop_requested", by)
        case.workspace.control.stop()
        if case.status == CaseStatus.PAUSED:
            self._status(case, CaseStatus.RUNNING, f"stopping, requested by {by}")
        return case

    def decide_scope(self, case_id: str, suspicion_id: str, approve: bool, by: str, note: str = "") -> Suspicion:
        case = self.get(case_id)
        if case.workspace is None:
            raise CaseError("this case has no investigation yet")
        try:
            return case.workspace.decide_scope(suspicion_id, approve, by, note)
        except ValueError as exc:
            raise CaseError(str(exc)) from exc

    def sign_off(self, case_id: str, by: str, note: str = "") -> Case:
        """A named person approves the case file as it stands; nothing is approved by default."""
        case = self._expect(case_id, CaseStatus.IN_REVIEW)
        case.sign_off = SignOff(by, self.clock(), note)
        case.ledger.append("sign_off", by, case_id=case.id, verdict=case.verdict.verdict if case.verdict else None,
                           ledger_head=case.ledger.head, note=note)
        self._status(case, CaseStatus.APPROVED, f"approved by {by}")
        return case

    def add_reviewed(self, ws: Workspace, claim: str, by: str, review: str | None = None) -> Case:
        """A case investigated elsewhere (an offline replay), added for review as it stands."""
        case = self._new_case(ws.allegation.id, claim, by, ws.mode, ws.poc, ledger=ws.ledger)
        case.allegation, case.workspace = ws.allegation, ws
        case.verdict, case.review = ws.verdict(), review
        self._status(case, CaseStatus.IN_REVIEW, "imported for review")
        return case

    # --- internals ----------------------------------------------------------------

    def _engine(self) -> Engine:
        if self.engine is None:
            raise CaseError("no model is configured: new cases cannot be investigated")
        return self.engine

    def _new_case(self, case_id: str | None, claim: str, by: str, mode: Mode, poc: bool,
                  ledger: Ledger | None = None) -> Case:
        with self.lock:
            case_id = case_id or f"CASE-{self.clock():%Y%m%d}-{len(self.cases) + 1:03d}"
            if case_id in self.cases:
                raise CaseError(f"case {case_id} already exists")
            events = EventLog(self.clock)
            observed = ObservedLedger(ledger or self.new_ledger(case_id), events)
            case = Case(id=case_id, claim=claim, mode=mode, poc=poc, created_by=by, created_at=self.clock(),
                        ledger=observed, events=events)
            self.cases[case_id] = case
        case.ledger.append("case_opened", by, case_id=case_id, mode=mode.value, poc=poc)
        return case

    def _prepare(self, case: Case, note: str) -> None:
        engine = self._engine()
        self._status(case, CaseStatus.PREPARING, note or "decomposing the claim")
        case.allegation, case.added_by_code = decompose_case(engine.analyst, case.id, case.claim)
        case.ledger.append("decomposition", "caligula", subclaims=len(case.allegation.subclaims),
                           added_by_code=case.added_by_code)
        case.workspace = Workspace(store=engine.store, allegation=case.allegation, mode=case.mode,
                                   ledger=case.ledger, connectors=engine.connectors, poc=case.poc,
                                   listeners=[case.events.append])
        case.team = engine.new_team(lambda phase, detail: case.events.append("phase", {"phase": phase,
                                                                                       "detail": detail}))
        case.draft = engine.analyst.plan(case.allegation)
        case.plan = self._normalize(case)
        self._status(case, CaseStatus.AWAITING_PLAN_APPROVAL, "plan ready for review")

    @staticmethod
    def _normalize(case: Case) -> Plan:
        return normalize_plan(case.draft, case.allegation, case.team.total_budget, tuple(case.team.specialists))

    def _expect(self, case_id: str, *statuses: CaseStatus) -> Case:
        case = self.get(case_id)
        if case.status not in statuses:
            wanted = " or ".join(s.value for s in statuses)
            raise CaseError(f"case {case_id} is {case.status.value}, not {wanted}")
        return case

    def _status(self, case: Case, status: CaseStatus, note: str = "") -> None:
        with self.lock:
            case.status, case.note = status, note
        case.events.append("status", {"status": status.value, "note": note})

    def _run(self, case: Case, work: Callable[[], None]) -> None:
        def guarded() -> None:
            try:
                work()
            except Exception as exc:  # the case keeps the error; the service keeps running
                case.events.append("error", {"error": f"{type(exc).__name__}: {exc}"})
                case.ledger.append("failure", "caligula", error=f"{type(exc).__name__}: {exc}")
                self._status(case, CaseStatus.FAILED, f"{type(exc).__name__}: {exc}")

        self.background(guarded)
