"""Turn an investigation result into what a public channel may show.

Fact-checks can answer publicly with the verdict and its sources. Anything
that points at wrongdoing (high_suspicion, or any investigation) is held for
human review; the public reply only acknowledges that a case exists.
"""

from __future__ import annotations

from caligula.agent.runner import InvestigationResult
from caligula.agent.workspace import Mode
from caligula.store import EvidenceStore

LABELS = {
    "supported": "Supported by the documents",
    "contradicted": "Contradicted by the documents",
    "partially_supported": "Partly supported",
    "unverified": "Could not be verified with available sources",
}
HOLD = (
    "Caligula opened case {case}. Findings that concern possible wrongdoing are "
    "published only after human review and a right of reply."
)


def public_reply(result: InvestigationResult, mode: Mode, store: EvidenceStore, max_chars: int = 600) -> str:
    v = result.verdict
    if mode == Mode.INVESTIGATE or v.verdict == "high_suspicion":
        return HOLD.format(case=v.allegation_id)
    verdict = v.verdict if v.verdict in LABELS else "unverified"
    # Fact-checks are usually one core claim; report the decisive sources for it.
    lines = [f"{LABELS[verdict]}."]
    sources = []
    for claim in v.by_subclaim:
        clusters = claim.supporting_clusters if claim.status == "supported" else claim.contradicting_clusters
        for cluster in clusters:
            d = store.get(cluster[0])
            sources.append(f"{d.publisher}, {d.observed_at:%Y-%m-%d}")
    if sources:
        lines.append("Sources: " + "; ".join(dict.fromkeys(sources)))
    if v.missing_evidence:
        lines.append("Still missing: " + v.missing_evidence[0].split(": ", 1)[-1])
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"
