"""Load a case directory (case.json + document files) and run it.

Offline mode replays the readings recorded in case.json; live mode asks Claude
to decompose the allegation and read every document. Both go through the same
validation and scoring.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from caligula.llm.claude import ClaudeInvestigator
from caligula.models import Allegation, EvidenceEdge, FinancialFigure, SourceKind, Verdict
from caligula.store import BlobStore, EvidenceStore
from caligula.verdict import build_verdict


def load_store(case_dir: Path, blobs: BlobStore) -> tuple[EvidenceStore, dict]:
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    store = EvidenceStore(blobs)
    for meta in case["documents"]:
        raw = (case_dir / meta["file"]).read_bytes()
        store.add(
            doc_id=meta["id"],
            raw=raw,
            text=raw.decode("utf-8"),
            canonical_url=meta["canonical_url"],
            url=meta["url"],
            source_kind=SourceKind(meta["source_kind"]),
            publisher=meta["publisher"],
            title=meta.get("title", ""),
            published_at=_dt(meta.get("published_at")),
            observed_at=_dt(meta["observed_at"]),
            cites=meta.get("cites", []),
            derived_from=meta.get("derived_from", []),
        )
    return store, case


def run_case(case_dir: Path, blobs: BlobStore, investigator: ClaudeInvestigator | None = None) -> Verdict:
    store, case = load_store(case_dir, blobs)
    recorded = Allegation.model_validate(case["allegation"])
    if investigator is None:
        allegation = recorded
        edges = [EvidenceEdge.model_validate(e) for e in case["recorded_readings"]["edges"]]
        figures = [FinancialFigure.model_validate(f) for f in case["recorded_readings"]["figures"]]
    else:
        allegation = investigator.decompose(recorded.id, recorded.text)
        edges, figures = [], []
        for doc in store.documents.values():
            doc_edges, doc_figures = investigator.read(allegation, doc)
            edges += doc_edges
            figures += doc_figures
    return build_verdict(store, allegation, edges, figures)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
