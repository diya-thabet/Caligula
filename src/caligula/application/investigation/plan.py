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

from caligula.domain.model.claims import Allegation, HypothesisKind
from caligula.domain.model.evidence import Relation
from caligula.domain.model.registers import REGISTERS
from caligula.domain.services.interest import helps_accused

SPECIALIST_NAMES = ("official", "funders_audit", "web_news", "social", "telegram")
# Default route for each kind of question when the planner leaves a core sub-claim uncovered.
FALLBACK_ROUTES = ("official", "funders_audit", "web_news")
# Where lawful explanations are published: decrees and official justifications, then the press.
INNOCENT_ROUTES = ("official", "web_news", "funders_audit")
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
    expectation_id: str | None = None  # an expected record this task searches for ("C5.E1")
    suspicion_id: str | None = None  # the suspicion this task tries to confirm or refute ("S1")
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
    expectation_id: str | None = None  # the expected record this task searches for, if any


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


def _expected_record_tasks(allegation: Allegation, tasks: list[Task], specialists: tuple[str, ...],
                           fixes: list[str]) -> list[Task]:
    """A search task for every expected record the planner did not assign."""
    covered = {t.expectation_id for t in tasks}
    added: list[Task] = []
    for eid, (cid, record) in allegation.expected().items():
        register = REGISTERS.get(record.register_id)
        if eid in covered or register is None:
            continue
        if register.specialist not in specialists:
            fixes.append(f"no specialist available to search {record.register_id} for {eid}")
            continue
        # Finding the record is what would help the accused: then the search is a challenge.
        presence = Relation.CONTRADICTS if record.absence_means == Relation.SUPPORTS else Relation.SUPPORTS
        purpose = "challenge" if helps_accused(allegation.bearing_of(cid), presence) else "support"
        added.append(Task(
            id=f"T{len(tasks) + len(added) + 1}", specialist=register.specialist, subclaim_ids=[cid],
            purpose=purpose, created_by="code", expectation_id=eid,
            objective=f"Search {register.name} for: {record.description}. If a proper search finds nothing, "
                      "close this task not_found, say exactly what you searched, and give the stored capture "
                      "of the empty result as the first doc_id: the absence is scored."))
        fixes.append(f"added {register.specialist} task for expected record {eid}")
    return added


def _innocent_tasks(allegation: Allegation, tasks: list[Task], specialists: tuple[str, ...],
                    fixes: list[str]) -> list[Task]:
    """A challenge task for every innocent explanation that no task tests yet."""
    tested = {cid for t in tasks for cid in t.subclaim_ids}
    claims = {c.id: c for c in allegation.subclaims}
    route = next((r for r in INNOCENT_ROUTES if r in specialists), None)
    added: list[Task] = []
    for h in allegation.hypotheses:
        if h.kind != HypothesisKind.INNOCENT or route is None:
            continue
        for cid in h.predicts:
            if cid in tested or cid not in claims:
                continue
            look_for = "; ".join(claims[cid].verification_questions) or claims[cid].statement
            added.append(Task(
                id=f"T{len(tasks) + len(added) + 1}", specialist=route, subclaim_ids=[cid], purpose="challenge",
                created_by="code",
                objective=f"Test the innocent explanation {h.id} ({h.statement}) through {cid}: "
                          f"{claims[cid].statement} Look for: {look_for}. Record what you find either way."))
            tested.add(cid)
            fixes.append(f"added {route} task to test innocent explanation {h.id}")
    return added


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
        expectation = t.expectation_id if t.expectation_id in allegation.expected() else None
        tasks.append(Task(id=f"T{len(tasks) + 1}", specialist=t.specialist, objective=t.objective,
                          subclaim_ids=ids, purpose=t.purpose, queries=t.queries, urls=t.urls,
                          expectation_id=expectation))
    tasks += _expected_record_tasks(allegation, tasks, specialists, fixes)
    tasks += _innocent_tasks(allegation, tasks, specialists, fixes)

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
