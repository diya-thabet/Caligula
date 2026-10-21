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
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from caligula.application.cases.events import EventLog, ObservedLedger
from caligula.application.cases.snapshot import CaseSnapshot, as_datetime, snapshot_of, workspace_from_dict
from caligula.application.evidence_store import EvidenceStore
from caligula.application.investigation.plan import EntityHint, Plan, PlanDraft, PlannedTask, Task, normalize_plan
from caligula.application.investigation.suspicions import Suspicion
from caligula.application.investigation.team import InvestigationTeam, RoundSummary, TeamResult
from caligula.application.investigation.workspace import Connectors, Mode, Workspace
from caligula.application.ports.llm import ClaimAnalyst
from caligula.application.ports.storage import Ledger
from caligula.application.usecases.decompose import decompose_case
from caligula.application.usecases.intake import admit
from caligula.domain.model.attribution import AttributionReport
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
    status_history: list[dict] = field(default_factory=list)  # every transition, with its reason
    restored: bool = False  # read back from storage: a record, not work in progress

    @property
    def last_activity(self) -> datetime:
        return self.events.last_at or self.created_at

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
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 repository: Any = None, origin: str = "api"):
        self.engine = engine  # None: the service only holds cases imported as they are
        self.new_ledger = new_ledger
        self.background = background
        self.clock = clock
        self.cases: dict[str, Case] = {}
        self.lock = threading.RLock()
        # Optional durable store. When absent nothing is written and nothing changes.
        self.repository = repository
        self.origin = origin

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
        case = self._expect_work(case_id, CaseStatus.AWAITING_PLAN_APPROVAL)
        case.draft = case.draft.model_copy(update={"tasks": tasks})
        case.plan = self._normalize(case)
        case.ledger.append("plan_edited", by, tasks=len(tasks), fixes=case.plan.fixes)
        self._status(case, CaseStatus.AWAITING_PLAN_APPROVAL, f"plan edited by {by}")
        return case

    def approve_plan(self, case_id: str, by: str) -> Case:
        case = self._expect_work(case_id, CaseStatus.AWAITING_PLAN_APPROVAL)
        case.ledger.append("plan_approved", by, tasks=[t.id for t in case.plan.tasks], budgets=case.plan.budgets)
        self._status(case, CaseStatus.RUNNING, f"plan approved by {by}")

        def work() -> None:
            result = case.team.run(case.workspace, plan=case.plan)
            case.result, case.verdict, case.review = result, result.verdict, result.review
            self._status(case, CaseStatus.IN_REVIEW, result.stop_reason)

        self._run(case, work)
        return case

    def pause(self, case_id: str, by: str) -> Case:
        case = self._expect_work(case_id, CaseStatus.RUNNING)
        case.workspace.control.pause()
        case.ledger.append("paused", by)
        self._status(case, CaseStatus.PAUSED, f"paused by {by}")
        return case

    def resume(self, case_id: str, by: str) -> Case:
        case = self._expect_work(case_id, CaseStatus.PAUSED)
        case.ledger.append("resumed", by)
        self._status(case, CaseStatus.RUNNING, f"resumed by {by}")
        case.workspace.control.resume()
        return case

    def stop(self, case_id: str, by: str) -> Case:
        case = self._expect_work(case_id, CaseStatus.RUNNING, CaseStatus.PAUSED)
        case.ledger.append("stop_requested", by)
        case.workspace.control.stop()
        if case.status == CaseStatus.PAUSED:
            self._status(case, CaseStatus.RUNNING, f"stopping, requested by {by}")
        return case

    def decide_scope(self, case_id: str, suspicion_id: str, approve: bool, by: str, note: str = "") -> Suspicion:
        case = self.get(case_id)
        if case.restored:
            raise CaseError(f"case {case_id} was restored from storage and is read-only; "
                            "its findings are kept as they were")
        if case.workspace is None:
            raise CaseError("this case has no investigation yet")
        try:
            suspicion = case.workspace.decide_scope(suspicion_id, approve, by, note)
        except ValueError as exc:
            raise CaseError(str(exc)) from exc
        self._persist(case)
        return suspicion

    def sign_off(self, case_id: str, by: str, note: str = "") -> Case:
        """A named person approves the case file as it stands; nothing is approved by default."""
        case = self._expect_work(case_id, CaseStatus.IN_REVIEW)
        case.sign_off = SignOff(by, self.clock(), note)
        case.ledger.append("sign_off", by, case_id=case.id, verdict=case.verdict.verdict if case.verdict else None,
                           ledger_head=case.ledger.head, note=note)
        self._status(case, CaseStatus.APPROVED, f"approved by {by}")
        return case

    def add_reviewed(self, ws: Workspace, claim: str, by: str, review: str | None = None) -> Case:
        """A case investigated elsewhere (an offline replay), added for review as it stands."""
        existing = self.cases.get(ws.allegation.id)
        if existing is not None:
            # Already restored from storage: that copy is the record, so leave its findings alone.
            # A replayed case is re-offered on every start, so its recorded chain is imported once,
            # into the durable ledger, the first time the stored case has none of its own.
            if not existing.ledger.entries and ws.ledger.entries:
                for entry in ws.ledger.entries:
                    existing.ledger.append(entry.action, entry.actor, **entry.data)
                self._persist(existing)
            return existing
        case = self._new_case(ws.allegation.id, claim, by, ws.mode, ws.poc, ledger=ws.ledger)
        case.allegation, case.workspace = ws.allegation, ws
        case.verdict, case.review = ws.verdict(), review
        self._status(case, CaseStatus.IN_REVIEW, "imported for review")
        return case

    # --- restoring ---------------------------------------------------------------

    def hydrate(self, snapshots: Iterable[CaseSnapshot], store: Any) -> list[Case]:
        """Rebuild the stored cases after a restart, before any new case is opened.

        Each is a record, not work in progress: a run that was in flight when the process
        died is recorded as failed rather than silently continued, and a case that was
        waiting at a checkpoint keeps that checkpoint. One unreadable snapshot marks that
        case failed and leaves the rest alone -- a bad row must not stop the service.
        """
        restored: list[Case] = []
        for snapshot in snapshots:
            if snapshot.id in self.cases:
                continue
            try:
                restored.append(self._restore(snapshot, store))
            except Exception as exc:
                restored.append(self._unreadable(snapshot, exc))
        return restored

    def _restore(self, s: CaseSnapshot, store: Any) -> Case:
        """Rebuild one case. The verdict is recomputed from the corpus, not read back:
        a snapshot that disagrees with its own evidence is a problem to see, not hide."""
        updated = as_datetime(s.updated_at)
        ledger = self.new_ledger(s.id)
        case = Case(
            id=s.id, claim=s.claim, mode=Mode(s.mode), poc=s.poc, created_by=s.created_by,
            created_at=as_datetime(s.created_at) or self.clock(),
            ledger=ObservedLedger(ledger, EventLog(self.clock, seed_at=updated)),
            events=EventLog(self.clock, seed_at=updated), status=CaseStatus(s.status), note=s.note,
            intake=Intake.model_validate(s.intake) if s.intake else None,
            decision=IntakeDecision(**s.decision) if s.decision else None,
            allegation=Allegation.model_validate(s.allegation) if s.allegation else None,
            added_by_code=list(s.added_by_code), review=s.review,
            sign_off=_sign_off(s.sign_off),
            status_history=list(s.status_history), restored=True,
        )
        self.cases[case.id] = case

        if case.allegation is not None:
            ws = Workspace(store=store, allegation=case.allegation, mode=case.mode,
                           ledger=case.ledger, poc=case.poc)
            workspace_from_dict(ws, s.workspace or {})
            case.workspace = ws
            case.verdict = ws.verdict()
        case.draft = PlanDraft.model_validate(s.plan) if s.plan and "budget_weights" in s.plan else None
        if s.plan and "budgets" in s.plan:
            case.plan = _plan_from_dict(s.plan)

        if case.status in (CaseStatus.RUNNING, CaseStatus.PAUSED, CaseStatus.PREPARING):
            # In flight when the process died: record that plainly instead of continuing
            # a run whose agents, budgets and stop rules no longer exist.
            case.restored = False
            case.ledger.append("failure", "caligula", error="interrupted by a restart")
            self._status(case, CaseStatus.FAILED, "interrupted by a restart")
            case.restored = True

        if s.result:
            case.result = _result_from_dict(s.result, case.verdict,
                                            AttributionReport.model_validate(s.attribution) if s.attribution else None)

        self._replay_events(case, ledger)
        return case

    def _replay_events(self, case: Case, ledger: Ledger) -> None:
        """Rebuild the live view's history: status changes, ledger echoes, then tool calls.

        Each event keeps the time it actually happened. Tool calls carry no timestamp of
        their own, so they are stamped with the moment the case was written -- not with
        the time of the restart, which would make a three-day-old case look three seconds old.
        """
        written = case.events.last_at
        history: list[tuple[datetime, str, dict]] = []
        for entry in case.status_history:
            at = as_datetime(entry.get("at"))
            if at:
                history.append((at, "status", {"status": entry["status"], "note": entry.get("note", "")}))
        for entry in ledger.entries:
            at = as_datetime(entry.at)
            if at:
                history.append((at, "audit", {"action": entry.action, "actor": entry.actor,
                                               "data": entry.data}))
        for step in (case.workspace.trace if case.workspace else []):
            if written:  # a tool call carries no time of its own; the write time is the honest one
                history.append((written, "tool", {"step": step.step, "agent": step.agent, "tool": step.tool,
                                                  "args": step.args, "outcome": step.outcome,
                                                  "round": case.workspace.round}))
        for at, kind, data in sorted(history, key=lambda h: h[0]):
            case.events.append(kind, data, at=at)

    def _unreadable(self, s: CaseSnapshot, exc: Exception) -> Case:
        """A snapshot this build cannot read: kept visible as a failure, ledger intact."""
        events = EventLog(self.clock)
        case = Case(id=s.id, claim=s.claim, mode=Mode(s.mode), poc=s.poc, created_by=s.created_by,
                    created_at=as_datetime(s.created_at) or self.clock(),
                    ledger=ObservedLedger(self.new_ledger(s.id), events), events=events,
                    status=CaseStatus.FAILED, restored=True,
                    note=f"stored snapshot could not be read: {type(exc).__name__}")
        case.events.append("status", {"status": case.status.value, "note": case.note})
        self.cases[case.id] = case
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
        self._persist(case)
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

    def _expect_work(self, case_id: str, *statuses: CaseStatus) -> Case:
        """Like `_expect`, for acts that change the record: never on a restored case.

        A case read back from storage is history, not work in progress. Its ledger and
        documents are intact, so nothing is lost by refusing; reopening it as a new
        attempt (which inherits what it established) is the way forward.
        """
        case = self.get(case_id)
        if case.restored:
            raise CaseError(f"case {case_id} was restored from storage and is read-only; "
                            "its findings are kept as they were")
        if case.status not in statuses:
            wanted = " or ".join(s.value for s in statuses)
            raise CaseError(f"case {case_id} is {case.status.value}, not {wanted}")
        return case

    def _status(self, case: Case, status: CaseStatus, note: str = "") -> None:
        at = self.clock()  # one reading for both the history and the event, or they disagree
        with self.lock:
            case.status, case.note = status, note
            case.status_history.append({"at": at.isoformat(), "status": status.value, "note": note})
        case.events.append("status", {"status": status.value, "note": note}, at=at)
        self._persist(case)

    def _persist(self, case: Case) -> None:
        """Write the snapshot if a repository is configured. Best effort: the case keeps
        working even when the store is unreachable, and the failure surfaces on restore."""
        if self.repository is None:
            return
        try:
            self.repository.save(snapshot_of(case, case.workspace, self.origin))
        except Exception:  # a store problem must not take the investigation down
            pass

    def _run(self, case: Case, work: Callable[[], None]) -> None:
        def guarded() -> None:
            try:
                work()
            except Exception as exc:  # the case keeps the error; the service keeps running
                case.events.append("error", {"error": f"{type(exc).__name__}: {exc}"})
                case.ledger.append("failure", "caligula", error=f"{type(exc).__name__}: {exc}")
                self._status(case, CaseStatus.FAILED, f"{type(exc).__name__}: {exc}")

        self.background(guarded)


def _plan_from_dict(data: dict) -> Plan:
    window = data.get("window") or [None, None]
    return Plan(
        entities=[EntityHint.model_validate(e) for e in data.get("entities", [])],
        window=(datetime.fromisoformat(window[0]) if window[0] else None,
                datetime.fromisoformat(window[1]) if window[1] else None),
        tasks=[Task.model_validate(t) for t in data.get("tasks", [])],
        budgets=dict(data.get("budgets", {})), fixes=list(data.get("fixes", [])))


def _result_from_dict(data: dict, verdict: Verdict | None, attribution: AttributionReport | None) -> TeamResult:
    return TeamResult(
        verdict=verdict, review=None, reports={k: list(v) for k, v in (data.get("reports") or {}).items()},
        unknown_citations=list(data.get("unknown_citations", [])),
        rounds=[RoundSummary(**r) for r in data.get("rounds", [])],
        stop_reason=data.get("stop_reason", ""), plan_fixes=list(data.get("plan_fixes", [])),
        attribution=attribution)


def _sign_off(data: dict | None) -> SignOff | None:
    if not data:
        return None
    return SignOff(by=data["by"], at=as_datetime(data.get("at")) or datetime.now(UTC), note=data.get("note", ""))
