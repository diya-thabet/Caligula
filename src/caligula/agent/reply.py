"""Turn an investigation result into what a public channel may show.

Fact-checks can answer publicly with the verdict and its sources. Anything
that points at wrongdoing (high_suspicion, or any investigation) is held for
human review; the public reply only acknowledges that a case exists.
"""

from __future__ import annotations

import re

from caligula.agent.runner import InvestigationResult
from caligula.agent.team import TeamResult
from caligula.agent.workspace import Mode
from caligula.store import EvidenceStore

TEXT = {
    "en": {
        "supported": "Supported by the documents",
        "contradicted": "Contradicted by the documents",
        "partially_supported": "Partly supported",
        "unverified": "Could not be verified with available sources",
        "sources": "Sources",
        "missing": "Still missing",
        "hold": "Caligula opened case {case}. Findings that concern possible wrongdoing are "
                "published only after human review and a right of reply.",
    },
    "fr": {
        "supported": "Confirmé par les documents",
        "contradicted": "Contredit par les documents",
        "partially_supported": "Partiellement confirmé",
        "unverified": "Invérifiable avec les sources disponibles",
        "sources": "Sources",
        "missing": "Manque encore",
        "hold": "Caligula a ouvert le dossier {case}. Les constats qui concernent d'éventuels manquements "
                "ne sont publiés qu'après vérification humaine et droit de réponse.",
    },
}
_FR = re.compile(r"\b(le|la|les|des|du|est|une|et|à|au|pour|dans|qui|sur|pas)\b", re.I)
_EN = re.compile(r"\b(the|is|are|of|and|to|in|that|for|was|on|not|with)\b", re.I)


def language(text: str) -> str:
    return "fr" if len(_FR.findall(text)) > len(_EN.findall(text)) else "en"


def public_reply(result: InvestigationResult | TeamResult, mode: Mode, store: EvidenceStore,
                 claim_text: str = "", max_chars: int = 600) -> str:
    v = result.verdict
    t = TEXT[language(claim_text)]
    if mode == Mode.INVESTIGATE or v.verdict == "high_suspicion":
        return t["hold"].format(case=v.allegation_id)
    verdict = v.verdict if v.verdict in t else "unverified"
    # Fact-checks are usually one core claim; report the decisive sources for it.
    lines = [f"{t[verdict]}."]
    sources = []
    for claim in v.by_subclaim:
        clusters = claim.supporting_clusters if claim.status == "supported" else claim.contradicting_clusters
        for cluster in clusters:
            d = store.get(cluster[0])
            sources.append(f"{d.publisher}, {d.observed_at:%Y-%m-%d}")
    if sources:
        lines.append(f"{t['sources']}: " + "; ".join(dict.fromkeys(sources)))
    if v.missing_evidence:
        lines.append(f"{t['missing']}: " + v.missing_evidence[0].split(": ", 1)[-1])
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"
