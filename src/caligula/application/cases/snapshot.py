"""A case as plain data: what persistence stores, and what restore reads back.

A `Case` holds threads, locks, a live store and a model-backed team, none of which
can be serialised. This module picks out what is worth keeping -- and nothing else
-- so the repository never sees a live object. Anything that can be recomputed is
either not stored (the verdict is always recomputed on restore) or stored for the
record only.

Evidence keeps its id: `evidence` holds every item ever accepted for the case, in
the order the ids were issued, each marked with whether it still counts. That order
is what makes E1..En mean the same thing after a restart.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from caligula.application.investigation.plan import EntityHint, Plan, Task
from caligula.application.investigation.suspicions import Suspicion, SuspicionStatus
from caligula.application.investigation.team import TeamResult
from caligula.application.investigation.workspace import Lead, Proposal, ProposalStatus, Search, TraceEntry, Workspace
from caligula.domain.model.evidence import AbsenceFinding, EvidenceEdge, FinancialFigure, RejectedEvidence
from caligula.domain.services.scoring import DEFAULT_PARAMS, Params

ITEMS = (EvidenceEdge, FinancialFigure, AbsenceFinding)


def _plain(value: Any) -> Any:
    """Dataclasses, enums and datetimes as JSON-ready values; pydantic already is."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _item(item: Any) -> dict:
    """Any model, pydantic or dataclass, as JSON-ready data."""
    return item.model_dump(mode="json") if hasattr(item, "model_dump") else _plain(item)


def workspace_to_dict(ws: Workspace) -> dict:
    """The reasoning graph, minus the parts that cannot outlive the process."""
    counted = ws.counted()
    return {
        "round": ws.round,
        "budget": ws.budget,
        "poc": ws.poc,
        "review_required": ws.review_required,
        "summary": ws.summary,
        "params": None if ws.params == DEFAULT_PARAMS else _plain(ws.params),
        "window": [ws.window[0].isoformat() if ws.window[0] else None,
                   ws.window[1].isoformat() if ws.window[1] else None],
        "evidence": [{"id": eid, "counted": eid in counted, "item": _item(item)}
                     for eid, item in ws.evidence_ids.items()],
        "proposals": [{"id": p.id, "by": p.by, "status": p.status.value, "note": p.note, "item": _item(p.item)}
                      for p in ws.proposals],
        "suspicions": [_plain(s) for s in ws.suspicions],
        "tasks": [t.model_dump(mode="json") for t in ws.tasks],
        "leads": [_plain(lead) for lead in ws.leads],
        "entities": [e.model_dump(mode="json") for e in ws.entities],
        "rejected": [_item(r) for r in ws.rejected],
        "searches": [_plain(s) for s in ws.searches],
        "trace": [asdict(t) for t in ws.trace],
    }


def workspace_from_dict(ws: Workspace, data: dict) -> Workspace:
    """Put a stored graph back on a workspace, ids and counted sets intact."""
    ws.round = data.get("round", 1)
    ws.budget = data.get("budget") or ws.budget
    ws.poc = bool(data.get("poc", ws.poc))
    ws.review_required = bool(data.get("review_required", ws.review_required))
    ws.summary = data.get("summary") or None
    if data.get("params"):
        ws.params = Params(**data["params"])
    window = data.get("window") or [None, None]
    ws.window = (datetime.fromisoformat(window[0]) if window[0] else None,
                 datetime.fromisoformat(window[1]) if window[1] else None)

    restored: dict[str, Any] = {}
    for row in data.get("evidence", []):
        cls = next((c for c in ITEMS if _matches(c, row["item"])), None)
        if cls is None:  # a model type we no longer have: keep it out, do not guess
            continue
        restored[row["id"]] = cls.model_validate(row["item"])
    ws.evidence_ids = restored

    counted = [restored[row["id"]] for row in data.get("evidence", [])
               if row.get("counted") and row["id"] in restored]
    ws.edges = [i for i in counted if isinstance(i, EvidenceEdge)]
    ws.figures = [i for i in counted if isinstance(i, FinancialFigure)]
    ws.absences = [i for i in counted if isinstance(i, AbsenceFinding)]

    ws.proposals = [Proposal(id=p["id"], by=p["by"], status=ProposalStatus(p["status"]), note=p["note"],
                             item=_validate(p["item"])) for p in data.get("proposals", [])]
    ws.suspicions = [Suspicion(**{**s, "status": SuspicionStatus(s["status"])}) for s in data.get("suspicions", [])]
    ws.tasks = [Task.model_validate(t) for t in data.get("tasks", [])]
    ws.leads = [Lead(**lead) for lead in data.get("leads", [])]
    ws.entities = [EntityHint.model_validate(e) for e in data.get("entities", [])]
    ws.rejected = [RejectedEvidence.model_validate(r) for r in data.get("rejected", [])]
    ws.searches = [Search(**s) for s in data.get("searches", [])]
    ws.trace = [TraceEntry(**t) for t in data.get("trace", [])]
    return ws


def _matches(cls: type, payload: dict) -> bool:
    """Which item type a stored payload is: the model's own fields, nothing more."""
    try:
        cls.model_validate(payload)
        return True
    except Exception:
        return False


def _validate(payload: dict) -> Any:
    for cls in ITEMS:
        if _matches(cls, payload):
            return cls.model_validate(payload)
    return payload


@dataclass
class CaseSnapshot:
    """A case as stored. `workspace` is `workspace_to_dict` output; the rest are
    `Case` fields. Everything is JSON-ready."""

    id: str
    claim: str
    mode: str
    poc: bool
    created_by: str
    created_at: str
    updated_at: str = ""
    status: str = ""
    note: str = ""
    origin: str = "api"
    round: int = 1
    added_by_code: list[str] = field(default_factory=list)
    intake: dict | None = None
    decision: dict | None = None
    allegation: dict | None = None
    plan: dict | None = None
    params: dict | None = None
    review: str | None = None
    summary: str | None = None
    verdict: dict | None = None
    attribution: dict | None = None
    result: dict | None = None
    workspace: dict = field(default_factory=dict)
    status_history: list[dict] = field(default_factory=list)
    sign_off: dict | None = None

    def to_row(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> CaseSnapshot:
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in row.items() if k in names})


def snapshot_of(case, workspace: Workspace | None, origin: str = "api") -> CaseSnapshot:
    """Read a live case into plain data."""
    ws = workspace if workspace is not None else getattr(case, "workspace", None)
    return CaseSnapshot(
        id=case.id,
        claim=case.claim,
        mode=case.mode.value if hasattr(case.mode, "value") else str(case.mode),
        poc=bool(case.poc),
        created_by=case.created_by,
        created_at=_iso(case.created_at),
        updated_at=_iso(getattr(case, "updated_at", None) or case.last_activity),
        status=case.status.value if hasattr(case.status, "value") else str(case.status),
        note=case.note or "",
        origin=origin,
        round=ws.round if ws else 1,
        added_by_code=list(getattr(case, "added_by_code", []) or []),
        intake=case.intake.model_dump(mode="json") if getattr(case, "intake", None) else None,
        decision=_plain(case.decision) if getattr(case, "decision", None) else None,
        allegation=case.allegation.model_dump(mode="json") if getattr(case, "allegation", None) else None,
        plan=_plan_of(case),
        params=_plain(ws.params) if ws and ws.params != DEFAULT_PARAMS else None,
        review=getattr(case, "review", None),
        summary=ws.summary if ws else None,
        verdict=case.verdict.model_dump(mode="json") if getattr(case, "verdict", None) else None,
        attribution=(case.result.attribution.model_dump(mode="json")
                     if getattr(case, "result", None) and case.result.attribution else None),
        result=_result_of(getattr(case, "result", None)),
        workspace=workspace_to_dict(ws) if ws else {},
        status_history=[_plain(h) for h in getattr(case, "status_history", [])],
        sign_off=_plain(case.sign_off) if getattr(case, "sign_off", None) else None,
    )


def _iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value or "")


def as_datetime(value: Any) -> datetime | None:
    """Read a timestamp that may be an ISO string (from jsonb) or a datetime (from a
    timestamptz column). Anything unparseable is None, never an exception."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _plan_of(case) -> dict | None:
    plan: Plan | None = getattr(case, "plan", None)
    if plan is None:
        draft = getattr(case, "draft", None)
        return draft.model_dump(mode="json") if draft else None
    return {"entities": [e.model_dump(mode="json") for e in plan.entities],
            "window": [plan.window[0].isoformat() if plan.window[0] else None,
                       plan.window[1].isoformat() if plan.window[1] else None],
            "tasks": [t.model_dump(mode="json") for t in plan.tasks],
            "budgets": dict(plan.budgets),
            "fixes": list(plan.fixes)}


def _result_of(result: TeamResult | None) -> dict | None:
    if result is None:
        return None
    return {"stop_reason": result.stop_reason,
            "unknown_citations": list(result.unknown_citations),
            "plan_fixes": list(result.plan_fixes),
            "reports": {k: list(v) for k, v in result.reports.items()},
            "rounds": [asdict(r) for r in result.rounds]}