"""Likelihood and confidence: two statements, never one number.

US intelligence analytic standards (ICD 203) require a judgment to say how
likely it is, in a fixed estimative vocabulary, and separately how much
confidence its basis deserves. "Very likely, low confidence" is a coherent
statement: the few documents we have agree, but there are few of them.

- Likelihood: the probability that every core sub-claim is true, from the
  support and contradiction scores. Without any evidence on a core sub-claim
  it cannot be assessed, and we say so rather than guess.
- Confidence: high, moderate or low, capped by every weakness found, each
  one listed: a sub-claim resting on one origin or on weak sources, a verdict
  that one document could overturn, an innocent explanation not yet tested,
  a supported sub-claim nobody tried to refute.

Both use uncalibrated priors until the labelled set exists (roadmap D1-D3).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from enum import StrEnum

from caligula.domain.model.claims import Allegation, HypothesisKind
from caligula.domain.model.evidence import Relation
from caligula.domain.model.verdict import SubClaimResult, Verdict
from caligula.domain.services.scoring import (
    CONTESTED,
    CONTRADICTED,
    DEFAULT_PARAMS,
    PARTIAL,
    SUPPORTED,
    UNVERIFIED,
    Params,
)

# ICD 203 estimative language: upper bound of each band.
TERMS = [
    (0.05, "almost no chance"), (0.20, "very unlikely"), (0.45, "unlikely"), (0.55, "roughly even chance"),
    (0.80, "likely"), (0.95, "very likely"), (1.01, "almost certain"),
]
CANNOT_ASSESS = "cannot be assessed"


class Level(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


def estimative_term(p: float) -> str:
    return next(term for bound, term in TERMS if p < bound)


def likelihood(allegation: Allegation, subclaims: dict[str, SubClaimResult]) -> tuple[float | None, str]:
    core = [subclaims[i] for i in allegation.core_subclaims if i in subclaims]
    if not core or any(c.support == 0 and c.contradiction == 0 for c in core):
        return None, CANNOT_ASSESS
    p = math.prod(0.5 + (c.support - c.contradiction) / 2 for c in core)
    return round(p, 3), estimative_term(p)


def _origins(c: SubClaimResult) -> int:
    if c.status == SUPPORTED:
        return len(c.supporting_clusters)
    return len(c.contradicting_clusters) if c.status == CONTRADICTED else 0


def confidence(
    v: Verdict, allegation: Allegation, params: Params = DEFAULT_PARAMS, unchallenged: Iterable[str] = ()
) -> tuple[Level, list[str]]:
    low: list[str] = []
    moderate: list[str] = []
    core = [c for c in v.by_subclaim if c.id in allegation.core_subclaims]
    financial_check = v.financial is not None and v.financial.flagged
    for c in core:
        if c.status == UNVERIFIED:
            low.append(f"{c.id} has no evidence")
            continue
        if c.status == PARTIAL:
            low.append(f"{c.id}: evidence too weak to settle it")
            continue
        if c.status == CONTESTED:
            moderate.append(f"{c.id}: credible evidence on both sides")
            continue
        if c.status in (SUPPORTED, CONTRADICTED) and _origins(c) < 2:
            moderate.append(f"{c.id} rests on a single independent origin")
        side = Relation.CONTRADICTS if c.status == CONTRADICTED else Relation.SUPPORTS
        weights = [i.weight for i in v.weighed if i.subclaim_id == c.id and i.relation == side]
        if c.id == allegation.financial_subclaim and financial_check:
            weights.append(params.financial_check_weight)
        if weights and max(weights) < params.weak_source:
            moderate.append(f"{c.id} rests only on weak or self-serving sources")
    for d in v.depends_on:
        if d.changes_verdict:
            moderate.append(f"the verdict would change without {', '.join(d.origin)}")
    untested = {h for m in v.ach for h in m.untested}
    status = {h.id: h.status for h in v.hypotheses}
    for h in allegation.hypotheses:
        if h.kind != HypothesisKind.INNOCENT:
            continue
        if status.get(h.id) == "consistent":
            low.append(f"innocent explanation {h.id} fits the evidence")
        elif h.id in untested:
            moderate.append(f"innocent explanation {h.id} not yet tested")
        elif status.get(h.id) == "open":
            moderate.append(f"innocent explanation {h.id} neither confirmed nor refuted")
    moderate += [f"{cid} supported but never challenged" for cid in unchallenged if cid in allegation.core_subclaims]
    if low:
        return Level.LOW, low + moderate
    if moderate:
        return Level.MODERATE, moderate
    return Level.HIGH, ["no weakness found: every core sub-claim rests on strong, independent origins, "
                        "no single origin decides the verdict, and no innocent explanation is open"]
