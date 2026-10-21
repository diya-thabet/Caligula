"""The judgment part of the case file, in the analytic order editors and lawyers expect.

ICD 203 and the analytic tradecraft primers put the bottom line first, then
key judgments with their likelihood and confidence, the alternatives
considered, key assumptions, what the conclusion depends on, gaps, and the
indicators that would change the assessment. Every line is computed by code
from the verdict and the workspace; evidence is cited by id (E1, E2...), so
each judgment points at the exact quote or search behind it.
"""

from __future__ import annotations

from collections import Counter

from caligula.adapters.presenters.analysis import likelihood_text
from caligula.application.investigation.plan import TaskStatus
from caligula.application.investigation.suspicions import SuspicionStatus
from caligula.application.investigation.team import STOP_REASONS
from caligula.application.investigation.workspace import Workspace
from caligula.domain.model.attribution import AttributionReport
from caligula.domain.model.claims import Allegation, Hypothesis, HypothesisKind
from caligula.domain.model.evidence import AbsenceFinding, FinancialFigure, Relation
from caligula.domain.model.registers import REGISTERS
from caligula.domain.model.verdict import AchMatrix, Verdict
from caligula.domain.services.judgment import subclaim_judgment
from caligula.domain.services.provenance import origin_clusters

VERDICT_WORDS = {
    "high_suspicion": "High suspicion",
    "partially_supported": "Partly supported",
    "contradicted": "Contradicted",
    "unverified": "Unverified",
}


def _register(register_id: str) -> str:
    return REGISTERS[register_id].name.split(":")[0]


def _percent(p: float) -> str:
    return "over 99%" if p >= 0.995 else "under 1%" if p < 0.005 else f"{p:.0%}"


def _side(ids: list[str], origins: int) -> str:
    return f"{', '.join(ids)} ({origins} independent origin(s))" if ids else "none"


def _ids(ids: list[str]) -> str:
    return ", ".join(ids) if ids else "none"


def _docs(ids: list[str]) -> str:
    return ", ".join(f"`{d}`" for d in ids)


def _tests(h: Hypothesis, a: Allegation) -> list[str]:
    """The sub-claims that tell an explanation apart from the allegation: where their predictions differ."""
    alleged = {c: v for x in a.hypotheses if x.kind == HypothesisKind.ALLEGATION for c, v in x.predicts.items()}
    return [c for c, v in h.predicts.items() if alleged.get(c, not v) != v]


def _main_matrix(v: Verdict, ws: Workspace) -> AchMatrix | None:
    """The matrix that contains the allegation itself, else the first with a choice to make."""
    allegations = {h.id for h in ws.allegation.hypotheses if h.kind == HypothesisKind.ALLEGATION}
    choices = [m for m in v.ach if len(m.hypotheses) > 1]
    return next((m for m in choices if allegations & set(m.hypotheses)), choices[0] if choices else None)


def _innocent_status(v: Verdict, ws: Workspace) -> tuple[list[str], list[str], list[str]]:
    """Innocent explanations: (refuted, fitting the evidence, untested or open)."""
    status = {h.id: h.status for h in v.hypotheses}
    innocent = [h.id for h in ws.allegation.hypotheses if h.kind == HypothesisKind.INNOCENT]
    refuted = [h for h in innocent if status.get(h) == "falsified"]
    fitting = [h for h in innocent if status.get(h) == "consistent"]
    return refuted, fitting, [h for h in innocent if h not in refuted and h not in fitting]


def bottom_line(ws: Workspace, v: Verdict, stop_reason: str | None = None) -> list[str]:
    a = ws.allegation
    statements = {h.id: h.statement for h in a.hypotheses}
    out = ["## Bottom line", "",
           f"**{VERDICT_WORDS.get(v.verdict, v.verdict)}.** The core facts ({', '.join(a.core_subclaims)}) are, "
           f"taken together, {likelihood_text(v)} true, with **{v.confidence}** confidence.", ""]
    m = _main_matrix(v, ws)
    if m and m.ranking:
        out.append(f"- Least contradicted explanation: **{m.ranking[0]}**, {statements[m.ranking[0]]}")
    refuted, fitting, open_ = _innocent_status(v, ws)
    if fitting:
        out.append(f"- Innocent explanation(s) that fit the evidence: {_ids(fitting)}. The facts may have a lawful "
                   "explanation.")
    if refuted:
        out.append(f"- Innocent explanation(s) refuted: {_ids(refuted)}.")
    if open_:
        out.append(f"- Innocent explanation(s) not yet settled: {_ids(open_)}.")
    decisive = [d for d in v.depends_on if d.changes_verdict]
    if decisive:
        out.append("- The verdict rests on single origins: it would change without "
                   + " or without ".join(_docs(d.origin) for d in decisive) + ".")
    unverified = [c.id for c in v.by_subclaim if c.status == "unverified"]
    if unverified:
        out.append(f"- No evidence yet on: {_ids(unverified)}.")
    if stop_reason:
        out.append(f"- Investigation stopped: {STOP_REASONS.get(stop_reason, stop_reason)}.")
    return out + [""]


def _evidence_by_side(ws: Workspace, v: Verdict, subclaim_id: str) -> dict[Relation, list[str]]:
    sides: dict[Relation, list[str]] = {r: [] for r in Relation}
    for eid, item in ws.counted().items():
        if not isinstance(item, FinancialFigure) and item.subclaim_id == subclaim_id:
            sides[item.relation].append(eid)
    if subclaim_id == ws.allegation.financial_subclaim and v.financial and v.financial.flagged:
        used = v.financial.figures
        sides[Relation.SUPPORTS] += [eid for eid, item in ws.counted().items() if item in used]
    return sides


def key_judgments(ws: Workspace, v: Verdict) -> list[str]:
    a = ws.allegation
    unchallenged = ws.unchallenged(v)
    out = ["## Key judgments", "",
           "One per sub-claim that is core or has evidence: how likely it is true, how much confidence the basis "
           "deserves, and the evidence behind it (ids refer to the annex *Evidence by sub-claim*).", ""]
    ordered = sorted(v.by_subclaim, key=lambda c: c.id not in a.core_subclaims)
    for c in ordered:
        sides = _evidence_by_side(ws, v, c.id)
        if c.id not in a.core_subclaims and not any(sides.values()):
            continue
        p, term, level, reasons = subclaim_judgment(c, v, a, ws.params, unchallenged)
        likely = f"{term} ({_percent(p)})" if p is not None else term
        core = " (core)" if c.id in a.core_subclaims else ""
        out += [f"### {c.id}{core}. {c.statement}", "",
                f"**{c.status}** · {likely} true · confidence **{level.value}**", "",
                f"- For: {_side(sides[Relation.SUPPORTS], len(c.supporting_clusters))}",
                f"- Against: {_side(sides[Relation.CONTRADICTS], len(c.contradicting_clusters))}"]
        if sides[Relation.QUALIFIES]:
            out.append(f"- Qualifying: {_ids(sides[Relation.QUALIFIES])}")
        if level.value != "high":
            out.append(f"- Confidence capped by: {'; '.join(r.replace(' -> ', ' → ') for r in reasons)}")
        out.append("")
    return out


def alternatives(v: Verdict, ws: Workspace) -> list[str]:
    a = ws.allegation
    kinds = {h.id: h.kind.value for h in a.hypotheses}
    out = ["## Alternatives considered", "",
           "Each explanation is rated by code against its own predictions; the matrices are in the annex "
           "*Competing hypotheses*.", ""]
    for m in v.ach:
        rank = {h: i for i, h in enumerate(m.ranking)}
        for h in sorted((h for h in v.hypotheses if h.id in m.hypotheses), key=lambda h: rank.get(h.id, 99)):
            against = f", evidence against {m.inconsistency[h.id]:.2f}" if h.id in m.inconsistency else ""
            untested = ", untested" if h.id in m.untested else ""
            out.append(f"- **{h.id}** ({kinds.get(h.id, 'alternative')}) {h.status}{against}{untested}: "
                       f"{h.statement}")
        out.append("")
    out += [f"- Innocent explanation *{r.explanation_id}* ruled out: {r.reason}" for r in a.ruled_out]
    return out + ([""] if a.ruled_out else [])


def key_assumptions(ws: Workspace, v: Verdict) -> list[str]:
    """The premises the scoring relies on in this case; each one, if false, would change the result."""
    p = ws.params
    out = ["## Key assumptions", ""]
    used = {w.doc_id for w in v.weighed if w.kind == "edge"}
    kinds = sorted({ws.store.get(d).source_kind for d in used}, key=lambda k: (-p.weights[k], k.value))
    if kinds:
        out.append("- Sources are weighed by how easily their publisher can silently change them: "
                   + ", ".join(f"{k} {p.weights[k]:.2f}" for k in kinds) + ".")
    clusters = origin_clusters(ws.store.documents)
    shared = {clusters[d] for d in used if sum(clusters[o] == clusters[d] for o in used) > 1}
    if shared:
        out.append(f"- Documents that cite, copy or derive from one another share an origin and count once "
                   f"({len(shared)} such group(s) here).")
    stakes = {w.interest for w in v.weighed}
    if "self_serving" in stakes:
        out.append(f"- A party's statement in its own favour weighs {p.self_serving_factor:.0%} of its usual weight.")
    if "against_interest" in stakes:
        out.append(f"- A party conceding a point against its own interest weighs at least {p.against_interest_floor}.")
    for eid, item in ws.counted().items():
        if isinstance(item, AbsenceFinding):
            register = REGISTERS[item.register_id]
            capture = "" if item.doc_id else "; no capture of the empty result was stored, so it counts half"
            out.append(f"- {eid}: {register.name} is complete enough (prior {p.completeness[item.register_id]}) "
                       f"that a record missing from it is evidence{capture}.")
    if v.financial:
        out.append(f"- The {v.financial.reference_role} amount and the benchmark describe comparable works; a gap "
                   f"above {p.anomaly_ratio:.0%} backed by {p.anomaly_min_clusters} independent origins is an "
                   "anomaly.")
    out += [f"- The standard innocent explanations for *{ws.allegation.claim_type}* are the ones worth testing; "
            "others may exist.",
            "- All weights and thresholds are uncalibrated priors until a labelled set of cases exists.", ""]
    return out


def gaps(ws: Workspace, v: Verdict) -> list[str]:
    a = ws.allegation
    out = ["## Gaps and collection requests", ""]
    out += [f"- {m}" for m in v.missing_evidence]
    _, _, open_ = _innocent_status(v, ws)
    tests = {h.id: _tests(h, a) for h in a.hypotheses}
    out += [f"- Innocent explanation {h} not settled: test {', '.join(tests[h])}." for h in open_]
    counted_absences = {(i.subclaim_id, i.register_id) for i in ws.counted().values() if isinstance(i, AbsenceFinding)}
    for eid, (cid, record) in a.expected().items():
        searched = any(t.expectation_id == eid and t.status == TaskStatus.DONE for t in ws.tasks)
        if not searched and (cid, record.register_id) not in counted_absences:
            out.append(f"- Expected record not searched yet ({eid}, {_register(record.register_id)}): "
                       f"{record.description}.")
    unchallenged = ws.unchallenged(v)
    if unchallenged:
        out.append(f"- Supported but never challenged: {', '.join(unchallenged)}.")
    out += [f"- Suspicion {s.id} still open: {s.statement}" for s in ws.suspicions if s.status == SuspicionStatus.OPEN]
    queued = [t for t in ws.tasks if t.status == TaskStatus.OPEN]
    if queued:
        out.append(f"- Collection tasks not run: {', '.join(t.id for t in queued)}.")
    return out + (["- None found."] if len(out) == 2 else []) + [""]


def indicators(ws: Workspace, v: Verdict) -> list[str]:
    """What, if it appeared, would change the assessment: the watch list for this case."""
    a = ws.allegation
    claims = {c.id: c for c in a.subclaims}
    status = {h.id: h.status for h in v.hypotheses}
    counted = {(i.subclaim_id, i.register_id) for i in ws.counted().values() if isinstance(i, AbsenceFinding)}
    weaken, strengthen = [], []
    for h in a.hypotheses:
        if h.kind != HypothesisKind.INNOCENT:
            continue
        for cid in _tests(h, a):
            records = [r for r in claims[cid].expected_records if r.absence_means == Relation.CONTRADICTS]
            found = "; ".join(f"{r.description} ({_register(r.register_id)})" for r in records)
            reopen = " (would reopen it)" if status.get(h.id) == "falsified" else ""
            weaken.append(f"Evidence for {h.id}{reopen}: {claims[cid].statement}"
                          + (f" For instance: {found}." if found else ""))
    for d in v.depends_on:
        if d.changes_verdict:
            weaken.append(f"Anything showing {_docs(d.origin)} is wrong, not comparable or not independent.")
    for cid in a.core_subclaims:
        for r in claims[cid].expected_records:
            where = _register(r.register_id)
            if r.absence_means == Relation.SUPPORTS:
                weaken.append(f"{cid} would be contradicted by finding: {r.description} ({where}).")
                if (cid, r.register_id) not in counted:
                    strengthen.append(f"{cid} would be supported if a proper search of {where} finds no: "
                                      f"{r.description}.")
            elif (cid, r.register_id) not in counted:
                weaken.append(f"{cid} would be contradicted if a proper search of {where} finds no: "
                              f"{r.description}.")
    for s in ws.suspicions:
        if s.status == SuspicionStatus.OPEN:
            strengthen.append(f"Suspicion {s.id} confirmed by: {s.confirm_by}")
            weaken.append(f"Suspicion {s.id} refuted by: {s.refute_by}")
    out = ["## Indicators that would change the assessment", ""]
    if weaken:
        out += ["Would weaken the allegation:", "", *[f"- {w}" for w in weaken], ""]
    if strengthen:
        out += ["Would strengthen it:", "", *[f"- {s}" for s in strengthen], ""]
    return out + (["None identified.", ""] if not weaken and not strengthen else [])


_CHECK_NOTE = {
    "supported": "the judge found it in the cited quotes",
    "partial": "partly in the cited quotes: published with a mark",
    "unsupported": "removed: not in its evidence",
    "uncited": "removed: a fact without evidence",
    "unjudged": "passed the checks in code; no judge model read it",
    "analysis": "the writer's analysis: no fact to check",
}


def checked_summary(report: AttributionReport) -> list[str]:
    """The summary as published, then every sentence with what the check found."""
    counts = Counter(s.status.value for s in report.sentences)
    out = ["## Summary", "",
           "Written by the reviewer, checked sentence by sentence against the evidence it cites; "
           "sentences that fail are removed, partly supported ones marked.", "",
           report.published() or "(nothing left after the check)", "",
           "### Sentence check", "",
           ", ".join(f"{n} {status}" for status, n in sorted(counts.items())) + ".", "",
           "| # | Sentence | Cites | Check | Why |", "|---|---|---|---|---|"]
    for i, s in enumerate(report.sentences, 1):
        why = "; ".join(s.reasons) or _CHECK_NOTE[s.status.value]
        text = s.text.replace("|", "\\|")
        out.append(f"| {i} | {text} | {', '.join(s.cited) or '–'} | {s.status.value} | {why.replace('|', '/')} |")
    return out + [""]
