"""Markdown for how an investigation unfolded: suspicions and rounds.

Every line comes from the workspace and the round summaries code kept.
"""

from __future__ import annotations

from collections import Counter

from caligula.application.investigation.team import STOP_REASONS, RoundSummary
from caligula.application.investigation.workspace import Workspace


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def suspicions(ws: Workspace) -> list[str]:
    if not ws.suspicions:
        return []
    out = ["## Suspicions", "",
           "Raised by the reviewer during the investigation; each is tested both ways and its status follows "
           "the evidence on the sub-claim that states it.", "",
           "| | Suspicion | Raised | Tested by | Status | Tasks | Note |", "|---|---|---|---|---|---|---|"]
    for s in ws.suspicions:
        status = s.status.value + (f" (round {s.resolved_round})" if s.resolved_round else "")
        out.append(f"| {s.id} | {_cell(s.statement)} | round {s.round} | {s.subclaim_id or '–'} | {status} | "
                   f"{', '.join(s.task_ids) or '–'} | {_cell(s.note) or '–'} |")
    return out + [""]


def evolution(rounds: list[RoundSummary], stop_reason: str | None) -> list[str]:
    if not rounds:
        return []
    out = ["## How the case evolved", "",
           "| Round | Specialists | Tasks closed | New evidence | Suspicions raised | Suspicions resolved | "
           "Verdict | Confidence |", "|---|---|---|---|---|---|---|---|"]
    for r in rounds:
        closed = ", ".join(f"{n} {o}" for o, n in sorted(Counter(r.tasks_closed.values()).items())) or "–"
        resolved = ", ".join(f"{sid} {status}" for sid, status in r.suspicions_changed.items()) or "–"
        out.append(f"| {r.round} | {', '.join(r.specialists)} | {closed} | {r.new_accepted} | "
                   f"{', '.join(r.suspicions_raised) or '–'} | {resolved} | {r.verdict} | {r.confidence} |")
    if stop_reason:
        out += ["", f"Stopped after {len(rounds)} round(s): {STOP_REASONS.get(stop_reason, stop_reason)}."]
    return out + [""]
