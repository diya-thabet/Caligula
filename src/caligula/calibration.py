"""Fit the scoring parameters on cases whose outcome is known.

A labelled case is a case directory with a `labels.json`:

    {"verdict": "high_suspicion",
     "subclaims": {"C1": "supported", "C2": "contradicted"},
     "substantiated": true}

`substantiated` is the real-world outcome (a court ruling, an audit finding
confirmed later, an official correction). It is what the confidence score is
checked against: a Brier score near 0 means confidences mean what they say.

One synthetic case proves the harness works, not that the weights are right.
Real calibration needs dozens of historical cases, for example Cour des comptes
findings with known follow-up.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from caligula.case import run_case
from caligula.domain.services.scoring import DEFAULT_PARAMS, Params
from caligula.store import BlobStore, MemoryEvidenceStore

SUSPICIOUS = {"high_suspicion", "partially_supported"}


@dataclass(frozen=True)
class Metrics:
    cases: int
    verdict_accuracy: float
    subclaim_accuracy: float
    brier: float  # mean (p - outcome)^2, p = confidence if the verdict leans suspicious, else 1 - confidence


def labelled_cases(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.rglob("labels.json"))


def evaluate(cases: list[Path], blobs: BlobStore, params: Params = DEFAULT_PARAMS) -> Metrics:
    verdict_hits = claim_hits = claim_total = 0
    brier = 0.0
    for case_dir in cases:
        labels = json.loads((case_dir / "labels.json").read_text(encoding="utf-8"))
        v = run_case(case_dir, MemoryEvidenceStore(blobs), params=params)
        verdict_hits += v.verdict == labels["verdict"]
        status = {c.id: c.status for c in v.by_subclaim}
        for claim_id, expected in labels.get("subclaims", {}).items():
            claim_total += 1
            claim_hits += status.get(claim_id) == expected
        p = v.confidence if v.verdict in SUSPICIOUS else 1 - v.confidence
        brier += (p - float(labels["substantiated"])) ** 2
    n = len(cases)
    return Metrics(
        cases=n,
        verdict_accuracy=round(verdict_hits / n, 3) if n else 0.0,
        subclaim_accuracy=round(claim_hits / claim_total, 3) if claim_total else 0.0,
        brier=round(brier / n, 4) if n else 0.0,
    )


def sweep(cases: list[Path], blobs: BlobStore) -> list[tuple[Params, Metrics]]:
    """Grid search over status thresholds, best first (subclaim accuracy, then Brier)."""
    results = []
    for strong, weak, penalty in itertools.product((0.6, 0.7, 0.8), (0.2, 0.3, 0.4), (0.1, 0.3, 0.5)):
        params = DEFAULT_PARAMS.with_(strong=strong, weak=weak, retconned_penalty=penalty)
        results.append((params, evaluate(cases, blobs, params)))
    return sorted(results, key=lambda r: (-r[1].subclaim_accuracy, -r[1].verdict_accuracy, r[1].brier))
