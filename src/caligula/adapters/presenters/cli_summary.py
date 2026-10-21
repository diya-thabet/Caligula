"""Plain-text verdict summary for the terminal."""

from __future__ import annotations

from caligula.domain.model.verdict import Verdict


def summarize(v: Verdict) -> str:
    likelihood = f"{v.likelihood_term} ({v.likelihood:.0%})" if v.likelihood is not None else v.likelihood_term
    lines = [f"Allegation {v.allegation_id}: {v.verdict.upper()}",
             f"  Core facts: {likelihood}. Confidence: {v.confidence}.",
             *[f"    - {r}" for r in v.confidence_reasons], ""]
    lines.append("Sub-claims:")
    for c in v.by_subclaim:
        clusters = f"{len(c.supporting_clusters)} supporting / {len(c.contradicting_clusters)} contradicting clusters"
        lines.append(f"  {c.id} {c.status:<20} {clusters}  {c.statement}")
        if c.qualifying_docs:
            lines.append(f"     qualified by: {', '.join(c.qualifying_docs)}")
    lines += ["", "Hypotheses:"]
    lines += [f"  {h.id} {h.status:<11} {h.statement}  [{'; '.join(h.reasons)}]" for h in v.hypotheses]
    for m in v.ach:
        if len(m.hypotheses) > 1 and m.ranking:
            against = ", ".join(f"{h} {m.inconsistency[h]:.2f}" for h in m.ranking)
            untested = f"; untested: {', '.join(m.untested)}" if m.untested else ""
            lines.append(f"  Least contradicted: {m.ranking[0]} (evidence against: {against}{untested})")
    if v.depends_on:
        lines += ["", "Depends on:"]
        lines += [f"  without {', '.join(d.origin)}: {'; '.join(d.changes)}" for d in v.depends_on]
    if v.retcon_flags:
        lines += ["", "Retcon flags:"]
        for f in v.retcon_flags:
            changes = "; ".join(f"{c.kind}: {c.removed} -> {c.added}" for c in f.changes)
            changes += " (OCR: verify against the scan)" if f.needs_review else ""
            lines.append(
                f"  {f.canonical_url}: {f.earlier_doc_id} ({f.earlier_observed_at:%Y-%m-%d}) -> "
                f"{f.later_doc_id} ({f.later_observed_at:%Y-%m-%d}): {changes}"
            )
    if v.financial:
        f = v.financial
        lines += [
            "",
            f"Financial: {f.reference_role} {f.reference_amount_tnd:,.0f} TND vs proven/benchmark "
            f"{f.proven_spend_tnd:,.0f} TND -> discrepancy {f.discrepancy_tnd:,.0f} TND "
            f"({f.discrepancy_ratio:.0%}, {f.independent_clusters} independent clusters, "
            f"{'FLAGGED' if f.flagged else 'not flagged'})",
        ]
    if v.rejected_evidence:
        lines += ["", "Rejected evidence:"]
        lines += [f"  {r.item}: {r.reason}" for r in v.rejected_evidence]
    if v.missing_evidence:
        lines += ["", "Missing evidence:"]
        lines += [f"  {m}" for m in v.missing_evidence]
    lines += ["", v.disclaimer]
    return "\n".join(lines)
