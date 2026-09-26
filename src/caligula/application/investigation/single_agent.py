"""Single-agent investigator (used for fact-checks).

A workflow with an agentic middle:

1. decompose (one structured call): claim -> sub-claims + hypotheses
2. investigate (tool loop): search, read, fetch archives and mirrors, record
   evidence, assess gaps, challenge what looks supported, finish
3. verdict (code): the same validation and scoring as offline cases

The model decides which tool to call next; code decides what counts.
For multi-source investigations see `team.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from caligula.application.investigation.brief import case_brief, unknown_citations
from caligula.application.investigation.prompts import SYSTEM
from caligula.application.investigation.toolkit import (
    SINGLE_AGENT_TOOLS,
    build_tools,
    native_web_search,
    web_search_tools,
)
from caligula.application.investigation.workspace import TraceEntry, Workspace
from caligula.application.ports.llm import AgentRunner
from caligula.domain.model.verdict import Verdict


@dataclass
class InvestigationResult:
    verdict: Verdict
    summary: str | None
    unknown_citations: list[str]
    trace: list[TraceEntry]
    stop_reason: str


class InvestigatorAgent:
    def __init__(self, runner: AgentRunner, web_search: bool = True):
        self.runner = runner
        self.web_search = web_search

    def run(self, ws: Workspace) -> InvestigationResult:
        tools = build_tools(ws, names=SINGLE_AGENT_TOOLS + web_search_tools(ws, self.web_search))
        stop_reason = self.runner.run(SYSTEM[ws.mode], tools, case_brief(ws, ws.budget),
                                      max_iterations=ws.budget + 20, done=lambda: ws.finished,
                                      web_search=native_web_search(ws, self.web_search))
        return InvestigationResult(
            verdict=ws.verdict(), summary=ws.summary, unknown_citations=unknown_citations(ws.summary, ws.store),
            trace=ws.trace, stop_reason=stop_reason,
        )
