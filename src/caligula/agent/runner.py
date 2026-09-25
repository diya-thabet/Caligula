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

import json
import re
from dataclasses import dataclass

import anthropic

from caligula.agent.loop import WEB_SEARCH, run_loop
from caligula.agent.prompts import SYSTEM
from caligula.agent.tools import build_tools
from caligula.agent.workspace import TraceEntry, Workspace
from caligula.domain.model.verdict import Verdict
from caligula.llm.claude import MODEL
from caligula.store import EvidenceStore


@dataclass
class InvestigationResult:
    verdict: Verdict
    summary: str | None
    unknown_citations: list[str]
    trace: list[TraceEntry]
    stop_reason: str


def case_brief(ws: Workspace, budget: int) -> str:
    a = ws.allegation
    claims = [
        {"id": c.id, "statement": c.statement, "verification_questions": c.verification_questions,
         "event_date": c.event_date.isoformat() if c.event_date else None,
         "attested_before": c.attested_before.isoformat() if c.attested_before else None}
        for c in a.subclaims
    ]
    return (
        f"<claim id=\"{a.id}\">\n{a.text}\n</claim>\n\n"
        f"<subclaims>\n{json.dumps(claims, ensure_ascii=False, indent=1)}\n</subclaims>\n\n"
        f"<hypotheses>\n{json.dumps([h.model_dump() for h in a.hypotheses], ensure_ascii=False)}\n</hypotheses>\n\n"
        f"Core sub-claims: {a.core_subclaims}. Documents already in the store: {len(ws.store.documents)}. "
        f"Tool budget: {budget} calls."
    )


def unknown_citations(text: str | None, store: EvidenceStore) -> list[str]:
    cited = set(re.findall(r"\[([\w.:-]+)\]", text or ""))
    return sorted(c for c in cited if store.get(c) is None)


class InvestigatorAgent:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL, web_search: bool = True):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.web_search = web_search

    def run(self, ws: Workspace) -> InvestigationResult:
        tools: list = build_tools(ws)
        if self.web_search:
            tools.append(WEB_SEARCH)
        stop_reason = run_loop(self.client, self.model, SYSTEM[ws.mode], tools, case_brief(ws, ws.budget),
                               max_iterations=ws.budget + 20, done=lambda: ws.finished)
        return InvestigationResult(
            verdict=ws.verdict(), summary=ws.summary, unknown_citations=unknown_citations(ws.summary, ws.store),
            trace=ws.trace, stop_reason=stop_reason,
        )
