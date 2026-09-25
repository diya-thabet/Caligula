"""Markdown for the analytic judgment: assessment, dependencies, competing hypotheses.

Shared by the case file; every line is computed by code from the verdict.
"""

from __future__ import annotations

from caligula.domain.model.claims import Allegation
from caligula.domain.model.verdict import AchMatrix, Verdict

_CELL = {"C": "C", "I": "**I**", "N": "–"}


def likelihood_text(v: Verdict) -> str:
    return f"{v.likelihood_term} ({v.likelihood:.0%})" if v.likelihood is not None else v.likelihood_term


def _docs(ids: list[str]) -> str:
    return ", ".join(f"`{d}`" for d in ids)


def _leading(m: AchMatrix) -> str:
    if not m.ranking:
        return f"none tested yet ({', '.join(m.hypotheses)})"
    against = " · ".join(f"{h} {m.inconsistency[h]:.2f}" for h in m.ranking)
    untested = f"; untested: {', '.join(m.untested)}" if m.untested else ""
    return f"**{m.ranking[0]}** (evidence against: {against}{untested})"


def assessment(v: Verdict, a: Allegation) -> list[str]:
    out = ["## Assessment", "",
           f"- Verdict: **{v.verdict}**",
           f"- Core facts ({', '.join(a.core_subclaims)}) all true: {likelihood_text(v)}",
           f"- Confidence: **{v.confidence}**" + (", because:" if v.confidence != "high" else "")]
    out += [f"  - {r}" for r in v.confidence_reasons]
    out += [f"- Least contradicted explanation among {', '.join(m.hypotheses)}: {_leading(m)}"
            for m in v.ach if len(m.hypotheses) > 1]
    out += ["", "### What the conclusion depends on", ""]
    if not v.depends_on:
        out.append("No single origin changes the verdict, a sub-claim or the leading explanation.")
    for d in v.depends_on:
        mark = "**changes the verdict**: " if d.changes_verdict else ""
        out.append(f"- Without {_docs(d.origin)}: {mark}{'; '.join(c.replace(' -> ', ' → ') for c in d.changes)}")
    return out + [""]


def competing_hypotheses(v: Verdict, a: Allegation) -> list[str]:
    kinds = {h.id: h.kind.value for h in a.hypotheses}
    results = {h.id: h for h in v.hypotheses}
    out = ["## Competing hypotheses", "",
           "Ratings are computed from each hypothesis's predictions: C consistent, **I** inconsistent, "
           "– no prediction. ◆ marks diagnostic evidence, which tells the hypotheses apart. "
           "The least contradicted hypothesis leads, not the most supported.", ""]
    for m in v.ach:
        for hid in m.hypotheses:
            h = results[hid]
            out.append(f"- **{hid}** ({kinds.get(hid, 'alternative')}) {h.status}: {h.statement} "
                       f"({'; '.join(h.reasons)})")
        if m.rows:
            out += ["", "| Evidence | Weight | " + " | ".join(m.hypotheses) + " |",
                    "|---|---|" + "---|" * len(m.hypotheses)]
            for r in sorted(m.rows, key=lambda r: (not r.diagnostic, r.subclaim_id)):
                label = f"{'◆ ' if r.diagnostic else ''}{r.subclaim_id} {r.relation} · {_docs(r.doc_ids)}"
                out.append(f"| {label} | {r.weight:.2f} | " + " | ".join(_CELL[r.ratings[h]] for h in m.hypotheses)
                           + " |")
            out += ["", f"Leading: {_leading(m)}"]
        out.append("")
    out += [f"- Innocent explanation *{r.explanation_id}* ruled out: {r.reason}" for r in a.ruled_out]
    return out + ([""] if a.ruled_out else [])
