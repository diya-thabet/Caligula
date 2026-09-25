"""Collection plan and tasks.

The lead investigator (one structured call) turns the decomposed case into a
plan: the entities to track under all their spellings, the time window, and
concrete tasks per source specialist. Code then checks the plan: unknown
specialists and sub-claims are dropped, budgets are clamped, and every core
sub-claim gets tasks from at least two different kinds of source, because one
kind of source can never make a claim independently supported.

Tasks are the unit of work: a specialist must close each of its tasks with an
outcome (found / partial / not_found / blocked). "Not found" is information:
a TUNEPS search that finds no tender notice is evidence of absence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from caligula.models import Allegation

SPECIALIST_NAMES = ("official", "funders_audit", "web_news", "social", "telegram")
# Default route for each kind of question when the planner leaves a core sub-claim uncovered.
FALLBACK_ROUTES = ("official", "funders_audit", "web_news")
MIN_BUDGET, MAX_BUDGET = 5, 40


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"


class Outcome(StrEnum):
    FOUND = "found"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"  # searched properly, nothing exists in reach: absence is information
    BLOCKED = "blocked"  # source unreachable, needs access we do not have, or out of policy


class Task(BaseModel):
    id: str
    specialist: str
    objective: str
    subclaim_ids: list[str] = Field(default_factory=list)
    purpose: Literal["support", "challenge", "explore"] = "support"
    queries: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    round: int = 1
    created_by: str = "planner"
    status: TaskStatus = TaskStatus.OPEN
    outcome: Outcome | None = None
    note: str = ""
    doc_ids: list[str] = Field(default_factory=list)


class EntityHint(BaseModel):
    name: str
    kind: Literal["company", "public_body", "person", "project", "document"]
    aliases: list[str] = Field(default_factory=list)


class PlannedTask(BaseModel):
    specialist: Literal["official", "funders_audit", "web_news", "social", "telegram"]
    objective: str
    subclaim_ids: list[str]
    purpose: Literal["support", "challenge", "explore"]
    queries: list[str]
    urls: list[str]


class BudgetWeight(BaseModel):
    specialist: Literal["official", "funders_audit", "web_news", "social", "telegram"]
    weight: float  # relative share of the total tool budget


class PlanDraft(BaseModel):
    """What the planner model returns; `normalize_plan` turns it into a Plan."""

    entities: list[EntityHint]
    window_start: str | None
    window_end: str | None
    tasks: list[PlannedTask]
    budget_weights: list[BudgetWeight]


@dataclass
class Plan:
    entities: list[EntityHint]
    window: tuple[datetime | None, datetime | None]
    tasks: list[Task]
    budgets: dict[str, int]
    fixes: list[str] = field(default_factory=list)  # what code changed in the draft, for the trace


def _dt(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def normalize_plan(draft: PlanDraft, allegation: Allegation, total_budget: int,
                   specialists: tuple[str, ...] = SPECIALIST_NAMES) -> Plan:
    known = {c.id for c in allegation.subclaims}
    fixes: list[str] = []
    tasks: list[Task] = []
    for t in draft.tasks:
        if t.specialist not in specialists:
            fixes.append(f"dropped task for unavailable specialist {t.specialist}")
            continue
        ids = [i for i in t.subclaim_ids if i in known]
        if len(ids) != len(t.subclaim_ids):
            fixes.append(f"removed unknown sub-claims from task '{t.objective[:40]}'")
        tasks.append(Task(id=f"T{len(tasks) + 1}", specialist=t.specialist, objective=t.objective,
                          subclaim_ids=ids, purpose=t.purpose, queries=t.queries, urls=t.urls))

    claims = {c.id: c for c in allegation.subclaims}
    for cid in allegation.core_subclaims:
        covering = {t.specialist for t in tasks if cid in t.subclaim_ids and t.purpose == "support"}
        for route in FALLBACK_ROUTES:
            if len(covering) >= 2:
                break
            if route in covering or route not in specialists:
                continue
            questions = "; ".join(claims[cid].verification_questions) or claims[cid].statement
            tasks.append(Task(id=f"T{len(tasks) + 1}", specialist=route, subclaim_ids=[cid], created_by="code",
                              objective=f"Find evidence on {cid}: {claims[cid].statement} ({questions})"))
            covering.add(route)
            fixes.append(f"added {route} task so {cid} is covered by two kinds of source")

    active = sorted({t.specialist for t in tasks})
    given = {b.specialist: b.weight for b in draft.budget_weights}
    weights = {s: given.get(s, 1.0) if given.get(s, 1.0) > 0 else 1.0 for s in active}
    total_w = sum(weights.values()) or 1.0
    budgets = {s: min(MAX_BUDGET, max(MIN_BUDGET, round(total_budget * w / total_w))) for s, w in weights.items()}
    return Plan(entities=draft.entities, window=(_dt(draft.window_start), _dt(draft.window_end)),
                tasks=tasks, budgets=budgets, fixes=fixes)
