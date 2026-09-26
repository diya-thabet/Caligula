"""Investigation workflow: plan, collect in parallel, review, repeat, report.

    PLAN      lead investigator drafts entities, window, tasks, budgets;
              code fixes the draft (coverage by two kinds of source, budgets)
    COLLECT   specialists with open tasks run in parallel; each closes its
              tasks with an outcome, proposes evidence, posts leads
    REVIEW    reviewer accepts / disputes proposals, creates tasks for the
              next round
    CHALLENGE code queues a challenge task for every supported sub-claim
              nobody has tried to refute yet
    STOP?     no open tasks | no progress and nothing left to challenge |
              round limit
    VERDICT   computed by code from accepted evidence only
    REPORT    markdown case file (report.py)

Specialists share one workspace behind a lock. The reviewer's rubric is a
parameter so expert-written rubrics can replace the default without code.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from caligula.application.investigation.brief import case_brief, unknown_citations
from caligula.application.investigation.plan import MIN_BUDGET, Plan, TaskStatus, normalize_plan
from caligula.application.investigation.prompts import _COLLECTOR, REVIEWER, SPECIALIST_FOCUS
from caligula.application.investigation.toolkit import build_tools, native_web_search, web_search_tools
from caligula.application.investigation.workspace import (
    AgentContext,
    ProposalStatus,
    TraceEntry,
    Workspace,
)
from caligula.application.ports.llm import AgentRunner, ClaimAnalyst
from caligula.domain.model.verdict import Verdict

READ = ["search_evidence", "read_document", "compare_versions", "compare_names", "assess"]
WORK = ["list_tasks", "complete_task", "post_lead", "record_evidence", "record_amount", "record_absence", "report"]
ARCHIVE = ["find_archived_captures", "ingest_archived_capture"]


@dataclass(frozen=True)
class Specialist:
    name: str
    tools: list[str]
    web_search: bool


SPECIALISTS = [
    Specialist("official", READ + ARCHIVE + ["ingest_url"] + WORK, web_search=True),
    Specialist("funders_audit", READ + ["search_funder_records", "ingest_url"] + WORK, web_search=True),
    Specialist("web_news", READ + ARCHIVE + ["ingest_url"] + WORK, web_search=True),
    Specialist("social", READ + ARCHIVE + ["ingest_url"] + WORK, web_search=True),
    Specialist("telegram", READ + ["fetch_telegram_channel"] + WORK, web_search=False),
]
REVIEWER_TOOLS = READ + ["list_proposals", "review_proposal", "record_evidence", "record_amount",
                         "register_party", "request_collection", "post_lead", "complete_review"]
# Challenges go to where innocent explanations are published: decrees and official
# justifications, and press coverage of corrections or explanations.
CHALLENGE_ROUTES = ("official", "web_news")


@dataclass
class RoundSummary:
    round: int
    specialists: list[str]
    tasks_closed: dict[str, str]  # task id -> outcome
    accepted: int
    disputed: int
    statuses: dict[str, str]
    challenge_tasks_added: list[str]


@dataclass
class TeamResult:
    verdict: Verdict
    review: str | None
    reports: dict[str, list[str]]
    unknown_citations: list[str]
    rounds: list[RoundSummary]
    stop_reason: str
    plan_fixes: list[str] = field(default_factory=list)
    trace: list[TraceEntry] = field(default_factory=list)


class InvestigationTeam:
    def __init__(
        self,
        runner: AgentRunner,
        analyst: ClaimAnalyst | None = None,
        reviewer_runner: AgentRunner | None = None,
        specialists: list[Specialist] | None = None,
        max_rounds: int = 3,
        total_budget: int = 100,
        reviewer_budget: int = 40,
        rubric: str = "",
        web_search: bool = True,
        parallel: int = 5,
        on_event: Callable[[str, str], None] | None = None,
    ):
        self.runner = runner
        self.reviewer_runner = reviewer_runner or runner  # the reviewer may run on another model
        self.analyst = analyst
        self.specialists = {s.name: s for s in (specialists or SPECIALISTS)}
        self.max_rounds = max_rounds
        self.total_budget = total_budget
        self.reviewer_budget = reviewer_budget
        self.rubric = rubric
        self.web_search = web_search
        self.parallel = parallel
        self.emit = on_event or (lambda phase, detail: None)

    # --- phases ----------------------------------------------------------------

    def run(self, ws: Workspace, plan: Plan | None = None) -> TeamResult:
        ws.review_required = True
        plan = plan or self.plan(ws)
        self._apply_plan(ws, plan)
        reports: dict[str, list[str]] = defaultdict(list)
        rounds: list[RoundSummary] = []
        review: str | None = None
        stop = "round_limit"
        for n in range(1, self.max_rounds + 1):
            ws.round = n
            active = [s for s in self.specialists if ws.open_tasks(s)]
            if not active:
                stop = "no_open_tasks"
                break
            closed_before = {t.id for t in ws.tasks if t.status == TaskStatus.DONE}
            self.emit("collect", f"round {n}: {', '.join(active)}")
            self._collect_round(ws, active, plan.budgets, n, reports)
            added = self._queue_challenges(ws, n + 1)
            self.emit("review", f"round {n}: {sum(p.status == 'pending' for p in ws.proposals)} pending proposals")
            review = self._review(ws, n, reports)
            added += self._queue_challenges(ws, n + 1)
            rounds.append(self._summarise(ws, n, active, closed_before, added))
            self.emit("round", json.dumps(vars(rounds[-1]), ensure_ascii=False))
            stop = self._should_stop(ws, rounds)
            if stop:
                break
            stop = "round_limit"
        verdict = ws.verdict()
        self.emit("verdict", f"{verdict.verdict} ({verdict.likelihood_term}, {verdict.confidence} confidence)")
        return TeamResult(verdict=verdict, review=review, reports=dict(reports),
                          unknown_citations=unknown_citations(review, ws.store), rounds=rounds,
                          stop_reason=stop, plan_fixes=plan.fixes, trace=ws.trace)

    def plan(self, ws: Workspace) -> Plan:
        if self.analyst is None:
            raise ValueError("planning needs a ClaimAnalyst; pass one or pass a plan")
        draft = self.analyst.plan(ws.allegation)
        plan = normalize_plan(draft, ws.allegation, self.total_budget, tuple(self.specialists))
        self.emit("plan", f"{len(plan.tasks)} tasks, budgets {plan.budgets}, fixes {plan.fixes}")
        return plan

    @staticmethod
    def _apply_plan(ws: Workspace, plan: Plan) -> None:
        ws.entities, ws.window = plan.entities, plan.window
        for t in plan.tasks:
            ws.add_task(**t.model_dump(exclude={"id", "status", "outcome", "note", "doc_ids"}))

    def _collect_round(self, ws, active, budgets, n, reports) -> None:
        with ThreadPoolExecutor(max_workers=self.parallel) as pool:
            futures = {}
            for name in active:
                budget = budgets.get(name, MIN_BUDGET * 3)
                if n > 1:  # later rounds are targeted follow-ups
                    budget = max(MIN_BUDGET, budget // 2)
                futures[name] = pool.submit(self._collect, ws, self.specialists[name], budget)
            for name, fut in futures.items():
                reports[name].append(fut.result())

    def _queue_challenges(self, ws: Workspace, next_round: int) -> list[str]:
        """Challenge tasks for supported sub-claims that nobody has tried to refute."""
        queued = {sid for t in ws.tasks if t.purpose == "challenge" and t.status == TaskStatus.OPEN
                  for sid in t.subclaim_ids}
        claims = {c.id: c for c in ws.allegation.subclaims}
        added = []
        for cid in ws.unchallenged():
            if cid in queued:
                continue
            for route in CHALLENGE_ROUTES:
                if route in self.specialists:
                    t = ws.add_task(
                        specialist=route, subclaim_ids=[cid], purpose="challenge", round=next_round,
                        created_by="code",
                        objective=f"Look for evidence that refutes or innocently explains {cid}: "
                                  f"{claims[cid].statement} (emergency procedure, force majeure, erratum, "
                                  "corrected figures, price shock, official justification).",
                    )
                    added.append(t.id)
        return added

    @staticmethod
    def _summarise(ws, n, active, closed_before, added) -> RoundSummary:
        v = ws.verdict(sensitivity=False)
        return RoundSummary(
            round=n, specialists=active,
            tasks_closed={t.id: t.outcome.value for t in ws.tasks
                          if t.status == TaskStatus.DONE and t.id not in closed_before},
            accepted=sum(p.status == ProposalStatus.ACCEPTED for p in ws.proposals),
            disputed=sum(p.status == ProposalStatus.DISPUTED for p in ws.proposals),
            statuses={c.id: c.status for c in v.by_subclaim},
            challenge_tasks_added=added,
        )

    @staticmethod
    def _should_stop(ws: Workspace, rounds: list[RoundSummary]) -> str | None:
        # New tasks for the next round, plus unfinished ones carried over from this or earlier rounds.
        upcoming = [t for t in ws.tasks if t.status == TaskStatus.OPEN and t.round <= ws.round + 1]
        if not upcoming:
            return "no_open_tasks"
        challenges_left = any(t.purpose == "challenge" for t in upcoming)
        if len(rounds) >= 2 and not challenges_left:
            last, prev = rounds[-1], rounds[-2]
            if last.statuses == prev.statuses and last.accepted == prev.accepted:
                return "no_progress"
        return None

    # --- agents ----------------------------------------------------------------

    def _collect(self, ws: Workspace, spec: Specialist, budget: int) -> str:
        ctx = AgentContext(name=spec.name, budget=budget)
        wanted = spec.web_search and self.web_search
        tools = build_tools(ws, ctx, spec.tools + web_search_tools(ws, wanted))
        system = f"{_COLLECTOR}\n\n{SPECIALIST_FOCUS[spec.name]}"
        tasks = [t.model_dump(include={"id", "objective", "subclaim_ids", "purpose", "queries", "urls",
                                       "expectation_id"}, exclude_none=True)
                 for t in ws.open_tasks(spec.name)]
        entities = [e.model_dump() for e in ws.entities]
        brief = (case_brief(ws, budget)
                 + f"\n\n<entities>\n{json.dumps(entities, ensure_ascii=False)}\n</entities>"
                 + f"\n\n<your_tasks round=\"{ws.round}\">\n{json.dumps(tasks, ensure_ascii=False, indent=1)}\n</your_tasks>"
                 + "\n\nWork your tasks, close each with complete_task, check list_tasks for leads, then report.")
        self.runner.run(system, tools, brief, budget + 15, lambda: ctx.done,
                        web_search=native_web_search(ws, wanted))
        return ctx.report or f"({spec.name} ended without a report)"

    def _review(self, ws: Workspace, n: int, reports: dict[str, list[str]]) -> str | None:
        ctx = AgentContext(name="reviewer", budget=self.reviewer_budget)
        tools = build_tools(ws, ctx, REVIEWER_TOOLS)
        system = REVIEWER + (f"\n\nReview rubric from domain experts:\n{self.rubric}" if self.rubric else "")
        latest = {name: r[-1] for name, r in reports.items() if r}
        closed = [t.model_dump(include={"id", "specialist", "objective", "purpose", "outcome", "note", "doc_ids"},
                               mode="json")
                  for t in ws.tasks if t.status == TaskStatus.DONE and t.round == n]
        queued = [f"{t.id} {t.specialist} ({t.purpose}): {t.objective[:100]}"
                  for t in ws.tasks if t.status == TaskStatus.OPEN and t.round > n]
        leads = [f"{lead.by}: {lead.note}" for lead in ws.leads_for("reviewer")]
        last = n == self.max_rounds
        brief = (
            case_brief(ws, self.reviewer_budget)
            + f"\n\nRound {n} of at most {self.max_rounds}"
            + (" (last: no further collection is possible; decide with what you have)." if last else ".")
            + f"\n\n<closed_tasks>\n{json.dumps(closed, ensure_ascii=False, indent=1)}\n</closed_tasks>"
            + f"\n\n<already_queued_for_next_round>\n{json.dumps(queued, ensure_ascii=False)}\n</already_queued_for_next_round>"
            + f"\n\n<leads_for_you>\n{json.dumps(leads, ensure_ascii=False)}\n</leads_for_you>"
            + f"\n\n<specialist_reports>\n{json.dumps(latest, ensure_ascii=False, indent=1)}\n</specialist_reports>"
        )
        self.reviewer_runner.run(system, tools, brief, self.reviewer_budget + 10, lambda: ctx.done)
        return ctx.report
