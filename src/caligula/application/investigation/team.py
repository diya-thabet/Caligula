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
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from caligula.application.investigation.attribution import check_summary
from caligula.application.investigation.brief import case_brief, unknown_citations
from caligula.application.investigation.plan import MIN_BUDGET, Plan, TaskStatus, normalize_plan, round_budget
from caligula.application.investigation.prompts import _COLLECTOR, REVIEWER, SPECIALIST_FOCUS
from caligula.application.investigation.suspicions import SuspicionStatus
from caligula.application.investigation.toolkit import build_tools, native_web_search, web_search_tools
from caligula.application.investigation.workspace import (
    AgentContext,
    ProposalStatus,
    TraceEntry,
    Workspace,
)
from caligula.application.ports.llm import AgentRunner, AttributionJudge, ClaimAnalyst
from caligula.domain.model.attribution import AttributionReport
from caligula.domain.model.claims import HypothesisKind
from caligula.domain.model.intake import IntakeDecision
from caligula.domain.model.verdict import Verdict
from caligula.domain.services.intake_policy import decide

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
                         "register_party", "raise_suspicion", "request_collection", "post_lead",
                         "complete_review"]
# Challenges go to where innocent explanations are published: decrees and official
# justifications, and press coverage of corrections or explanations.
CHALLENGE_ROUTES = ("official", "web_news")


# Why a case stops, as the case file explains it.
STOP_REASONS = {
    "settled": "settled: confidence is high and no suspicion is open",
    "exhausted": "exhausted: the last round brought no new evidence, changed no status and raised no new suspicion",
    "no_open_tasks": "nothing left to do: every task is closed",
    "budget": "the tool-call budget is spent",
    "round_limit": "the round limit was reached with work still open",
}


def priority_subclaims(ws: Workspace) -> set[str]:
    """Where more effort pays: sub-claims testing an open suspicion or an innocent explanation
    not yet refuted, and core sub-claims that rest on a single origin."""
    v = ws.verdict(sensitivity=False)
    status = {h.id: h.status for h in v.hypotheses}
    out = {s.subclaim_id for s in ws.suspicions if s.status == SuspicionStatus.OPEN and s.subclaim_id}
    out |= {cid for h in ws.allegation.hypotheses if h.kind == HypothesisKind.INNOCENT
            and status.get(h.id) != "falsified" for cid in h.predicts}
    out |= {c.id for c in v.by_subclaim if c.id in ws.allegation.core_subclaims
            and len(c.supporting_clusters if c.status != "contradicted" else c.contradicting_clusters) < 2}
    return out


@dataclass
class RoundSummary:
    round: int
    specialists: list[str]
    tasks_closed: dict[str, str]  # task id -> outcome
    accepted: int
    disputed: int
    statuses: dict[str, str]
    challenge_tasks_added: list[str]
    new_accepted: int = 0
    suspicions_raised: list[str] = field(default_factory=list)
    suspicions_changed: dict[str, str] = field(default_factory=dict)  # id -> new status
    verdict: str = ""
    confidence: str = ""
    tool_calls: int = 0  # cumulative


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
    # The final summary checked sentence by sentence; its published() text is what an editor sees.
    attribution: AttributionReport | None = None


class InvestigationTeam:
    def __init__(
        self,
        runner: AgentRunner,
        analyst: ClaimAnalyst | None = None,
        reviewer_runner: AgentRunner | None = None,
        specialists: list[Specialist] | None = None,
        max_rounds: int = 6,
        max_tool_calls: int = 600,
        total_budget: int = 100,
        reviewer_budget: int = 40,
        rubric: str = "",
        web_search: bool = True,
        parallel: int = 5,
        on_event: Callable[[str, str], None] | None = None,
        judge: AttributionJudge | None = None,
    ):
        self.runner = runner
        self.reviewer_runner = reviewer_runner or runner  # the reviewer may run on another model
        self.analyst = analyst
        self.specialists = {s.name: s for s in (specialists or SPECIALISTS)}
        self.max_rounds = max_rounds  # hard caps: the loop otherwise runs until settled or exhausted
        self.max_tool_calls = max_tool_calls
        self.total_budget = total_budget
        self.reviewer_budget = reviewer_budget
        self.rubric = rubric
        self.web_search = web_search
        self.parallel = parallel
        self.emit = on_event or (lambda phase, detail: None)
        self.judge = judge  # reads the final summary sentence by sentence; code checks it either way

    # --- phases ----------------------------------------------------------------

    def run(self, ws: Workspace, plan: Plan | None = None) -> TeamResult:
        """Rounds of collection and review until the case is settled or exhausted, or a hard cap is hit."""
        ws.review_required = True
        if ws.scope_policy is None and self.analyst is not None:
            ws.scope_policy = self._scope_policy(ws)
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
            if len(ws.trace) >= self.max_tool_calls:
                stop = "budget"
                break
            closed_before = {t.id for t in ws.tasks if t.status == TaskStatus.DONE}
            self.emit("collect", f"round {n}: {', '.join(active)}")
            self._collect_round(ws, active, plan.budgets, n, reports)
            added = self._queue_challenges(ws, n + 1)
            self.emit("review", f"round {n}: {sum(p.status == 'pending' for p in ws.proposals)} pending proposals")
            review = self._review(ws, n, reports)
            added += self._queue_challenges(ws, n + 1)
            changed = {s.id: s.status.value for s in ws.resolve_suspicions()}
            rounds.append(self._summarise(ws, n, active, closed_before, added, rounds, changed))
            self.emit("round", json.dumps(vars(rounds[-1]), ensure_ascii=False))
            stop = self._should_stop(ws, rounds)
            if stop:
                break
            stop = "round_limit"
        verdict = ws.verdict()
        self.emit("verdict", f"{verdict.verdict} ({verdict.likelihood_term}, {verdict.confidence} confidence)")
        ws.ledger.append("stop", "caligula", reason=stop, rounds=len(rounds))
        review = self._finalise_summary(ws, review, verdict)
        return TeamResult(verdict=verdict, review=review, reports=dict(reports),
                          unknown_citations=unknown_citations(review, ws), rounds=rounds,
                          stop_reason=stop, plan_fixes=plan.fixes, trace=ws.trace, attribution=ws.attribution)

    def _scope_policy(self, ws: Workspace):
        """The intake policy, applied to a suspicion that widens the case."""
        def check(statement: str) -> IntakeDecision:
            decision = decide(self.analyst.classify(statement))
            ws.ledger.append("scope_check", "caligula", statement=statement, decision=decision.decision.value,
                             reasons=decision.reasons)
            return decision
        return check

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
        priority = priority_subclaims(ws) if n > 1 else set()
        with ThreadPoolExecutor(max_workers=self.parallel) as pool:
            futures = {}
            for name in active:
                urgent = sum(1 for t in ws.open_tasks(name) if t.suspicion_id or set(t.subclaim_ids) & priority)
                budget = round_budget(budgets.get(name, MIN_BUDGET * 3), n, urgent)
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
    def _summarise(ws, n, active, closed_before, added, previous, changed) -> RoundSummary:
        v = ws.verdict()
        accepted = sum(p.status == ProposalStatus.ACCEPTED for p in ws.proposals)
        return RoundSummary(
            round=n, specialists=active,
            tasks_closed={t.id: t.outcome.value for t in ws.tasks
                          if t.status == TaskStatus.DONE and t.id not in closed_before},
            accepted=accepted,
            disputed=sum(p.status == ProposalStatus.DISPUTED for p in ws.proposals),
            statuses={c.id: c.status for c in v.by_subclaim},
            challenge_tasks_added=added,
            new_accepted=accepted - (previous[-1].accepted if previous else 0),
            suspicions_raised=[s.id for s in ws.suspicions if s.round == n],
            suspicions_changed=changed,
            verdict=v.verdict, confidence=v.confidence, tool_calls=len(ws.trace),
        )

    def _should_stop(self, ws: Workspace, rounds: list[RoundSummary]) -> str | None:
        last = rounds[-1]
        open_suspicions = [s for s in ws.suspicions if s.status == SuspicionStatus.OPEN]
        if last.confidence == "high" and not open_suspicions:
            return "settled"
        # New tasks for the next round, plus unfinished ones carried over from this or earlier rounds.
        upcoming = [t for t in ws.tasks if t.status == TaskStatus.OPEN and t.round <= ws.round + 1]
        if not upcoming:
            return "no_open_tasks"
        if len(rounds) >= 2:
            unchanged = last.statuses == rounds[-2].statuses and not last.new_accepted
            if unchanged and not last.suspicions_changed and not last.suspicions_raised:
                return "exhausted"
        if last.tool_calls >= self.max_tool_calls:
            return "budget"
        return None

    def _finalise_summary(self, ws: Workspace, review: str | None, verdict: Verdict) -> str | None:
        """The judge reads the final summary; sentences it does not find in their evidence go back to
        the reviewer once, and whatever still fails is removed from the published text."""
        if not review:
            return review
        report = check_summary(ws, review, self.judge, verdict)
        if report.failures and self.judge is not None:
            self.emit("citations", f"{len(report.failures)} sentence(s) sent back to the reviewer")
            review = self._rewrite(ws, review, report) or review
            report = check_summary(ws, review, self.judge, verdict)
        ws.attribution = report
        counts = Counter(s.status.value for s in report.sentences)
        ws.ledger.append("attribution", "caligula", statuses=dict(sorted(counts.items())),
                         removed=[s.text for s in report.failures], judged=self.judge is not None)
        self.emit("citations", ", ".join(f"{n} {status}" for status, n in sorted(counts.items())))
        return review

    def _rewrite(self, ws: Workspace, review: str, report: AttributionReport) -> str | None:
        # Already sent back once: complete_review accepts the rewrite, which the judge then reads.
        ctx = AgentContext(name="reviewer", budget=3, summary_returned=True)
        tools = build_tools(ws, ctx, ["assess", "complete_review"])
        problems = "\n".join(f"- « {s.text} »: {'; '.join(s.reasons)}" for s in report.failures)
        brief = (case_brief(ws, ctx.budget)
                 + f"\n\n<your_summary>\n{review}\n</your_summary>"
                 + f"\n\n<sentences_not_backed_by_their_evidence>\n{problems}\n</sentences_not_backed_by_their_evidence>"
                 + "\n\nRewrite the summary so that every sentence says only what its cited evidence says "
                   "(assess lists counted_evidence), or drop those sentences, then call complete_review. "
                   "Sentences that still fail will be removed.")
        self.reviewer_runner.run(REVIEWER, tools, brief, 8, lambda: ctx.done, deep=True)
        return ctx.report

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
        suspicions = [{"id": s.id, "statement": s.statement, "status": s.status.value, "tested_by": s.subclaim_id,
                       "raised_in_round": s.round} for s in ws.suspicions]
        last = n == self.max_rounds
        brief = (
            case_brief(ws, self.reviewer_budget)
            + f"\n\nRound {n} of at most {self.max_rounds}"
            + (" (last: no further collection is possible; decide with what you have)." if last else ".")
            + f"\n\n<closed_tasks>\n{json.dumps(closed, ensure_ascii=False, indent=1)}\n</closed_tasks>"
            + f"\n\n<already_queued_for_next_round>\n{json.dumps(queued, ensure_ascii=False)}\n</already_queued_for_next_round>"
            + f"\n\n<leads_for_you>\n{json.dumps(leads, ensure_ascii=False)}\n</leads_for_you>"
            + f"\n\n<suspicions>\n{json.dumps(suspicions, ensure_ascii=False)}\n</suspicions>"
            + f"\n\n<specialist_reports>\n{json.dumps(latest, ensure_ascii=False, indent=1)}\n</specialist_reports>"
        )
        self.reviewer_runner.run(system, tools, brief, self.reviewer_budget + 10, lambda: ctx.done, deep=True)
        return ctx.report
