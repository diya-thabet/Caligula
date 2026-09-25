"""Case file in Markdown, built by code from the workspace (no model involved).

Everything in it traces to a stored document, a task outcome or a ledger
entry, so an editor can check any line.
"""

from __future__ import annotations

from datetime import UTC, datetime

from caligula.application.investigation.plan import TaskStatus
from caligula.application.investigation.workspace import ProposalStatus, Workspace
from caligula.domain.model.evidence import EvidenceEdge
from caligula.domain.model.verdict import Verdict
from caligula.domain.services.interest import Interest, interest, role_of
from caligula.domain.services.provenance import origin_clusters

POC_BANNER = (
    "> **PROOF OF CONCEPT — internal working document.** Not reviewed by a lawyer or an editor. "
    "Not for publication or circulation outside the project."
)


def _doc_line(ws: Workspace, doc_id: str) -> str:
    d = ws.store.get(doc_id)
    date = (d.published_at or d.observed_at).date().isoformat()
    return f"`{d.id}` {d.publisher} ({d.source_kind}, {date})"


_STAKE = {
    Interest.SELF_SERVING: " · *self-serving: the publisher is a party and this helps it*",
    Interest.AGAINST_INTEREST: " · *against the publisher's own interest*",
}


def _stake_note(ws: Workspace, e: EvidenceEdge) -> str:
    d = ws.store.get(e.doc_id)
    stake = interest(role_of(d.publisher, ws.allegation.parties), ws.allegation.bearing_of(e.subclaim_id), e.relation)
    return _STAKE.get(stake, "")


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def build_report(ws: Workspace, verdict: Verdict, review: str | None = None, poc: bool = True,
                 stop_reason: str | None = None) -> str:
    a = ws.allegation
    out: list[str] = [f"# Case {a.id}", ""]
    if poc:
        out += [POC_BANNER, ""]
    out += [
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · verdict **{verdict.verdict}** · "
        f"confidence {verdict.confidence:.2f}" + (f" · stopped: {stop_reason}" if stop_reason else ""),
        "", "## Claim", "", a.text, "",
    ]
    if a.parties:
        out += ["Parties: " + "; ".join(f"{p.name} ({p.role.value})" for p in a.parties), ""]
    out += [
        "## Sub-claims", "",
        "| | Statement | Status | Support | Against | Independent sources (for / against) |",
        "|---|---|---|---|---|---|",
    ]
    for c in verdict.by_subclaim:
        core = " (core)" if c.id in a.core_subclaims else ""
        out.append(f"| {c.id}{core} | {_cell(c.statement)} | {c.status} | {c.support:.2f} | "
                   f"{c.contradiction:.2f} | {len(c.supporting_clusters)} / {len(c.contradicting_clusters)} |")
    out += ["", "## Hypotheses", ""]
    out += [f"- **{h.id}** {h.status}: {h.statement} ({'; '.join(h.reasons)})" for h in verdict.hypotheses]

    out += ["", "## Anomalies", ""]
    if not verdict.retcon_flags and not (verdict.financial and verdict.financial.flagged):
        out.append("None detected by code.")
    for f in verdict.retcon_flags:
        changes = "; ".join(f"{c.kind} {c.removed} → {c.added}" for c in f.changes)
        review_note = " (OCR text: verify against the scan)" if f.needs_review else ""
        out.append(f"- **Record rewritten**: {f.canonical_url} between {f.earlier_observed_at:%Y-%m-%d} "
                   f"(`{f.earlier_doc_id}`) and {f.later_observed_at:%Y-%m-%d} (`{f.later_doc_id}`): {changes}{review_note}")
    if verdict.financial:
        fin = verdict.financial
        out.append(f"- **Financial check** ({'flagged' if fin.flagged else 'not flagged'}): {fin.reference_role} "
                   f"{fin.reference_amount_tnd:,.0f} TND vs proven/benchmark {fin.proven_spend_tnd:,.0f} TND, "
                   f"gap {fin.discrepancy_tnd:,.0f} TND ({fin.discrepancy_ratio:.0%}), "
                   f"{fin.independent_clusters} independent origins")

    out += ["", "## Evidence by sub-claim", ""]
    clusters = origin_clusters(ws.store.documents)

    def origin_note(doc_id: str, siblings: list[str]) -> str:
        same = sorted(d for d in siblings if d != doc_id and clusters[d] == clusters[doc_id])
        return f" · same origin as {', '.join(f'`{d}`' for d in same)}" if same else ""

    for c in a.subclaims:
        props = [p for p in ws.proposals if isinstance(p.item, EvidenceEdge) and p.item.subclaim_id == c.id]
        direct = [e for e in ws.edges if e.subclaim_id == c.id and not any(p.item == e for p in props)]
        if not props and not direct:
            continue
        out += [f"### {c.id}. {c.statement}", ""]
        siblings = [p.item.doc_id for p in props] + [e.doc_id for e in direct]
        for p in props:
            e = p.item
            mark = {"accepted": "✓", "disputed": "✗", "pending": "?"}[p.status]
            note = f" — reviewer: {p.note}" if p.note and p.status != ProposalStatus.PENDING else ""
            out.append(f"- {mark} {e.relation} · {_doc_line(ws, e.doc_id)} · proposed by {p.by}: "
                       f"« {e.quote} »{_stake_note(ws, e)}{origin_note(e.doc_id, siblings)}{note}")
        for e in direct:
            out.append(f"- ✓ {e.relation} · {_doc_line(ws, e.doc_id)}: « {e.quote} »"
                       f"{_stake_note(ws, e)}{origin_note(e.doc_id, siblings)}")
        out.append("")

    out += ["## Timeline", ""]
    used = {e.doc_id for e in ws.edges} | {f.doc_id for f in ws.figures}
    events = []
    for doc_id in used:
        d = ws.store.get(doc_id)
        when = d.published_at or d.observed_at
        seen = f" (first seen {d.observed_at:%Y-%m-%d})" if abs((d.observed_at - when).days) > 1 else ""
        events.append((when, f"{_doc_line(ws, doc_id)}{seen}"))
    for c in a.subclaims:
        if c.event_date:
            events.append((c.event_date, f"**event** ({c.id}): {c.statement}"))
    for f in verdict.retcon_flags:
        events.append((f.later_observed_at, f"**rewritten version observed**: `{f.later_doc_id}` differs from "
                                            f"`{f.earlier_doc_id}`"))
    out += [f"- {when:%Y-%m-%d} {what}" for when, what in sorted(events, key=lambda x: x[0])] or ["(no dated evidence)"]

    if ws.tasks:
        out += ["", "## Collection tasks", "", "| Task | Specialist | Purpose | Objective | Outcome | Note |",
                "|---|---|---|---|---|---|"]
        for t in ws.tasks:
            outcome = t.outcome.value if t.status == TaskStatus.DONE else "not run"
            out.append(f"| {t.id} (r{t.round}, {t.created_by}) | {t.specialist} | {t.purpose} | "
                       f"{_cell(t.objective[:140])} | {outcome} | {_cell(t.note[:160])} |")

    unchallenged = ws.unchallenged(verdict)
    out += ["", "## Limits of this assessment", ""]
    if unchallenged:
        out.append(f"- Supported but not yet challenged: {', '.join(unchallenged)}.")
    out += [f"- Missing: {m}" for m in verdict.missing_evidence]
    if verdict.rejected_evidence:
        out.append(f"- {len(verdict.rejected_evidence)} proposed item(s) rejected by validation "
                   "(quotes not found, dates incompatible, unknown sub-claims).")
    out.append(f"- {verdict.disclaimer}")

    if review:
        out += ["", "## Reviewer summary", "", review]
    broken = ws.ledger.verify()
    out += ["", "## Integrity", "",
            f"- Documents in store: {len(ws.store.documents)}; ledger entries: {len(ws.ledger.entries)}; "
            f"head `{ws.ledger.head[:16]}…`; chain {'intact' if broken is None else f'BROKEN at entry {broken}'}."]
    return "\n".join(out) + "\n"
