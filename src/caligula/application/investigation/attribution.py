"""Sentence-level attribution check of a summary against the workspace's evidence.

Code checks every sentence first (`domain.services.attribution`); a judge
model then reads each sentence that passed against the quotes it cites.
Without a judge, those sentences stay "unjudged", and the case file says so.
"""

from __future__ import annotations

from datetime import datetime

from caligula.application.investigation.workspace import Workspace
from caligula.application.ports.llm import AttributionJudge
from caligula.domain.model.attribution import AttributionReport, Citable, SentenceStatus
from caligula.domain.model.evidence import AbsenceFinding, FinancialFigure
from caligula.domain.model.registers import REGISTERS
from caligula.domain.model.verdict import Verdict
from caligula.domain.services.attribution import apply_judgment, check_sentence, split_sentences


def _date_numbers(*dates: datetime | None) -> tuple[float, ...]:
    return tuple(float(n) for d in dates if d for n in (d.year, d.month, d.day))


def citables(ws: Workspace, verdict: Verdict | None = None) -> dict[str, Citable]:
    """Every counted item, as a summary may cite it."""
    fin = (verdict or ws.verdict(sensitivity=False)).financial
    out = {}
    for eid, item in ws.counted().items():
        if isinstance(item, AbsenceFinding):
            register = REGISTERS[item.register_id].name
            capture = ws.store.get(item.doc_id) if item.doc_id else None
            out[eid] = Citable(eid, f"{register}: nothing found for « {item.query} »",
                               context=f"{register} {capture.text if capture else ''}",
                               numbers=_date_numbers(item.searched_at, item.window_start, item.window_end))
            continue
        d = ws.store.get(item.doc_id)
        numbers = _date_numbers(d.published_at, d.observed_at)
        if isinstance(item, FinancialFigure):
            numbers += (item.amount_tnd,)
            if fin and item in fin.figures:  # the check's results are vouched for by the figures it used
                numbers += (fin.reference_amount_tnd, fin.proven_spend_tnd, fin.discrepancy_tnd,
                            round(fin.discrepancy_ratio * 100, 1))
        out[eid] = Citable(eid, item.quote, context=f"{d.publisher} {d.title} {d.text}", numbers=numbers)
    return out


def check_summary(ws: Workspace, summary: str, judge: AttributionJudge | None = None,
                  verdict: Verdict | None = None) -> AttributionReport:
    evidence = citables(ws, verdict)
    withdrawn = set(ws.evidence_ids) - set(evidence)
    documents = set(ws.store.documents)
    checks = []
    for sentence in split_sentences(summary):
        c = check_sentence(sentence, evidence, withdrawn, documents)
        if c.status == SentenceStatus.UNJUDGED and judge is not None:
            try:
                rating = judge.judge(sentence, [(i, evidence[i].text) for i in c.cited])
            except Exception as exc:  # a failed judgment leaves the sentence unjudged, and says why
                c = c.model_copy(update={"reasons": [f"judge unavailable: {type(exc).__name__}: {exc}"]})
            else:
                c = apply_judgment(c, rating, evidence)
        checks.append(c)
    return AttributionReport(sentences=checks)
