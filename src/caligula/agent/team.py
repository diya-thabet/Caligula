"""Investigation team: source specialists in parallel, then a reviewer.

    round 1:  official ─┐
              funders ──┤
              web_news ─┼─► proposals ─► reviewer ─► accept / dispute
              social ───┤                    │
              telegram ─┘                    ├─► request_collection (gaps, challenges)
    round 2:  only the specialists the reviewer asked for, with its instructions
    ...
    verdict:  computed by code from accepted evidence only

Specialists share one workspace (store, ledger, proposals) behind a lock.
The reviewer's rubric is a parameter so that expert-written rubrics can
replace the default without code changes.
"""

from __future__ import annotations

import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import anthropic

from caligula.agent.loop import WEB_SEARCH, run_loop
from caligula.agent.prompts import REVIEWER, SPECIALIST_FOCUS, _COLLECTOR
from caligula.agent.runner import case_brief, unknown_citations
from caligula.agent.tools import build_tools
from caligula.agent.workspace import AgentContext, TraceEntry, Workspace
from caligula.llm.claude import MODEL
from caligula.models import Verdict

READ = ["search_evidence", "read_document", "compare_versions", "compare_names", "assess"]
PROPOSE = ["record_evidence", "record_amount", "report"]
ARCHIVE = ["find_archived_captures", "ingest_archived_capture"]


@dataclass(frozen=True)
class Specialist:
    name: str
    tools: list[str]
    web_search: bool
    budget: int = 25


SPECIALISTS = [
    Specialist("official", READ + ARCHIVE + ["ingest_url"] + PROPOSE, web_search=True),
    Specialist("funders_audit", READ + ["search_funder_records", "ingest_url"] + PROPOSE, web_search=True),
    Specialist("web_news", READ + ARCHIVE + ["ingest_url"] + PROPOSE, web_search=True),
    Specialist("social", READ + ARCHIVE + ["ingest_url"] + PROPOSE, web_search=True),
    Specialist("telegram", READ + ["fetch_telegram_channel"] + PROPOSE, web_search=False),
]
REVIEWER_TOOLS = READ + ["list_proposals", "review_proposal", "record_evidence", "record_amount",
                         "request_collection", "complete_review"]


@dataclass
class TeamResult:
    verdict: Verdict
    review: str | None
    reports: dict[str, list[str]]
    unknown_citations: list[str]
    rounds: int
    trace: list[TraceEntry] = field(default_factory=list)


class InvestigationTeam:
    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model: str = MODEL,
        specialists: list[Specialist] | None = None,
        max_rounds: int = 2,
        reviewer_budget: int = 40,
        rubric: str = "",
        web_search: bool = True,
        parallel: int = 5,
    ):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.specialists = {s.name: s for s in (specialists or SPECIALISTS)}
        self.max_rounds = max_rounds
        self.reviewer_budget = reviewer_budget
        self.rubric = rubric
        self.web_search = web_search
        self.parallel = parallel

    def run(self, ws: Workspace) -> TeamResult:
        ws.review_required = True
        reports: dict[str, list[str]] = defaultdict(list)
        tasks = {name: "" for name in self.specialists}
        review = None
        rounds = 0
        for rounds in range(1, self.max_rounds + 1):
            with ThreadPoolExecutor(max_workers=self.parallel) as pool:
                futures = {name: pool.submit(self._collect, ws, self.specialists[name], extra)
                           for name, extra in tasks.items()}
                for name, fut in futures.items():
                    reports[name].append(fut.result())
            review = self._review(ws, rounds, reports)
            with ws.lock:
                requests, ws.requests = ws.requests, []
            if not requests or rounds == self.max_rounds:
                break
            grouped: dict[str, list[str]] = defaultdict(list)
            for r in requests:
                if r.specialist in self.specialists:
                    grouped[r.specialist].append(
                        f"- ({r.purpose}{', ' + r.subclaim_id if r.subclaim_id else ''}) {r.instructions}")
            tasks = {name: "The reviewer asks you to:\n" + "\n".join(items) for name, items in grouped.items()}
        return TeamResult(
            verdict=ws.verdict(), review=review, reports=dict(reports),
            unknown_citations=unknown_citations(review, ws.store), rounds=rounds, trace=ws.trace,
        )

    def _collect(self, ws: Workspace, spec: Specialist, extra: str) -> str:
        ctx = AgentContext(name=spec.name, budget=spec.budget)
        tools: list = build_tools(ws, ctx, spec.tools)
        if spec.web_search and self.web_search:
            tools.append(WEB_SEARCH)
        system = f"{_COLLECTOR}\n\n{SPECIALIST_FOCUS[spec.name]}"
        brief = case_brief(ws, spec.budget) + (f"\n\n{extra}" if extra else "")
        run_loop(self.client, self.model, system, tools, brief, spec.budget + 10, lambda: ctx.done)
        return ctx.report or f"({spec.name} ended without a report)"

    def _review(self, ws: Workspace, round_no: int, reports: dict[str, list[str]]) -> str | None:
        ctx = AgentContext(name="reviewer", budget=self.reviewer_budget)
        tools = build_tools(ws, ctx, REVIEWER_TOOLS)
        system = REVIEWER + (f"\n\nReview rubric from domain experts:\n{self.rubric}" if self.rubric else "")
        latest = {name: r[-1] for name, r in reports.items()}
        last_round = round_no == self.max_rounds
        brief = (
            case_brief(ws, self.reviewer_budget)
            + f"\n\nCollection round {round_no} of {self.max_rounds}"
            + (" (last: no further collection is possible; decide with what you have)." if last_round else ".")
            + f"\n\n<specialist_reports>\n{json.dumps(latest, ensure_ascii=False, indent=1)}\n</specialist_reports>"
        )
        run_loop(self.client, self.model, system, tools, brief, self.reviewer_budget + 10, lambda: ctx.done)
        return ctx.report
