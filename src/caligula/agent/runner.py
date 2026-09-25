"""The investigator loop.

A workflow with an agentic middle:

1. decompose (one structured call): allegation -> sub-claims + hypotheses
2. investigate (tool loop): search, read, fetch archives and mirrors, record
   evidence, assess gaps, challenge what looks supported, finish
3. verdict (code): the same validation and scoring as offline cases

The model decides which tool to call next; code decides what counts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import anthropic

from caligula.agent.tools import build_tools
from caligula.agent.workspace import Mode, TraceEntry, Workspace
from caligula.llm.claude import FALLBACK_BETA, MODEL
from caligula.models import Verdict

CONTEXT_BETA = "context-management-2025-06-27"
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 10}
MAX_PAUSE_RESTARTS = 3

_COMMON = """\
You investigate public-interest claims for Caligula, a Tunisian accountability \
project. You never decide on your own authority whether a claim is true. You \
gather evidence with tools, record each piece with an exact quote, and code \
scores it. Your job is to find the evidence that would settle each sub-claim, \
from the sources hardest to falsify.

How to work:
- Start from the sub-claims and hypotheses below. Call assess early and often; \
it tells you what is missing.
- Prefer sources the accused cannot edit: archive captures, foreign funder \
records, audit reports, statistics, dated contributor uploads. Treat live \
official pages as claims by an interested party; compare them with archived \
versions.
- Record evidence as soon as you read it. A rejected record tells you why; fix \
the quote or find another document rather than arguing.
- Before finishing, challenge every supported sub-claim: search for the \
innocent explanation (emergency decree, force majeure, price shock, erratum, \
corrected figures). Record what you find, including evidence that clears \
someone.
- Several articles repeating one source count once. Look for independent origins.
- Never name, accuse or speculate about individuals in your summary. Describe \
documents, amounts, dates and procedures. Cite documents as [doc_id].
- When web search finds a relevant page, store it with ingest_url (and check \
the archive) before relying on it; you can only cite stored documents."""

SYSTEM = {
    Mode.FACTCHECK: _COMMON + """

Mode: fact-check. A member of the public asked whether a claim is accurate. \
Aim for the few strongest independent sources, then finish. Your summary is \
the basis of a short public reply: state what the documents show, plainly.""",
    Mode.INVESTIGATE: _COMMON + """

Mode: investigation. This is a multi-hop case. Trace the money (allocated, \
disbursed, benchmark, proven spend), the procedure (tender notice, award, \
signature dates), the physical output, and the record history. Your summary \
goes to a human reviewer, not to the public: list anomalies, the evidence for \
each, and what evidence would be needed to go further.""",
}


@dataclass
class InvestigationResult:
    verdict: Verdict
    summary: str | None
    unknown_citations: list[str]
    trace: list[TraceEntry]
    stop_reason: str


def _brief(ws: Workspace) -> str:
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
        f"Tool budget: {ws.budget} calls."
    )


class InvestigatorAgent:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL, web_search: bool = True):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.web_search = web_search

    def run(self, ws: Workspace) -> InvestigationResult:
        tools: list = build_tools(ws)
        if self.web_search:
            tools.append(WEB_SEARCH)
        messages: list = [{"role": "user", "content": _brief(ws)}]
        stop_reason = "end_turn"
        for _ in range(MAX_PAUSE_RESTARTS + 1):
            runner = self.client.beta.messages.tool_runner(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM[ws.mode],
                tools=tools,
                messages=messages,
                # Budget + finish end the loop; this only guards against a runaway.
                max_iterations=ws.budget + 20,
                betas=[FALLBACK_BETA, CONTEXT_BETA],
                fallbacks="default",
                # Old tool results can be cleared: everything that matters is in the workspace.
                context_management={"edits": [{"type": "clear_tool_uses_20250919"}]},
            )
            last = None
            for message in runner:
                last = message
                messages.append({"role": "assistant", "content": message.content})
                tool_response = runner.generate_tool_call_response()
                if tool_response is not None:
                    messages.append(tool_response)
            stop_reason = last.stop_reason if last else "no_response"
            # A long server-side web search can pause the turn; resume it.
            if stop_reason != "pause_turn" or ws.finished:
                break
        return self._result(ws, stop_reason)

    @staticmethod
    def _result(ws: Workspace, stop_reason: str) -> InvestigationResult:
        cited = set(re.findall(r"\[([\w.:-]+)\]", ws.summary or ""))
        unknown = sorted(c for c in cited if ws.store.get(c) is None)
        return InvestigationResult(
            verdict=ws.verdict(), summary=ws.summary, unknown_citations=unknown,
            trace=ws.trace, stop_reason=stop_reason,
        )
