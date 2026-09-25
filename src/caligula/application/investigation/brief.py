"""What every agent is told about the case, and citation checks on what it writes."""

from __future__ import annotations

import json
import re

from caligula.application.evidence_store import EvidenceStore
from caligula.application.investigation.workspace import Workspace


def case_brief(ws: Workspace, budget: int) -> str:
    a = ws.allegation
    claims = [
        {"id": c.id, "statement": c.statement, "verification_questions": c.verification_questions,
         "event_date": c.event_date.isoformat() if c.event_date else None,
         "attested_before": c.attested_before.isoformat() if c.attested_before else None,
         "bearing": a.bearing_of(c.id)}
        for c in a.subclaims
    ]
    parties = [p.model_dump(mode="json") for p in a.parties]
    return (
        f"<claim id=\"{a.id}\">\n{a.text}\n</claim>\n\n"
        f"<subclaims>\n{json.dumps(claims, ensure_ascii=False, indent=1)}\n</subclaims>\n\n"
        f"<hypotheses>\n{json.dumps([h.model_dump() for h in a.hypotheses], ensure_ascii=False)}\n</hypotheses>\n\n"
        f"<parties>\n{json.dumps(parties, ensure_ascii=False)}\n</parties>\n\n"
        f"Core sub-claims: {a.core_subclaims}. Documents already in the store: {len(ws.store.documents)}. "
        f"Tool budget: {budget} calls."
    )


def unknown_citations(text: str | None, store: EvidenceStore) -> list[str]:
    cited = set(re.findall(r"\[([\w.:-]+)\]", text or ""))
    return sorted(c for c in cited if store.get(c) is None)
