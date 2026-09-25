"""Load a case directory (case.json + document files) and run it.

Offline mode replays the readings recorded in case.json; live mode asks Claude
to decompose the allegation and read every document. Both go through the same
validation and scoring.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from caligula.adapters.media.text_extraction import extract_text
from caligula.application.evidence_store import EvidenceStore
from caligula.domain.model.claims import Allegation
from caligula.domain.model.documents import SourceKind
from caligula.domain.model.evidence import EvidenceEdge, FinancialFigure
from caligula.domain.model.verdict import Verdict
from caligula.domain.services.scoring import DEFAULT_PARAMS, Params
from caligula.domain.services.verdict import build_verdict
from caligula.llm.claude import ClaudeInvestigator


def load_case(case_dir: Path, store: EvidenceStore) -> dict:
    """Ingest the case's documents into `store` (skipping ones already there)."""
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    for meta in case["documents"]:
        if store.get(meta["id"]) is not None:
            continue
        path = case_dir / meta["file"]
        raw = path.read_bytes()
        extracted = extract_text(raw, path.name)
        store.add(
            doc_id=meta["id"],
            raw=raw,
            text=extracted.text,
            extraction=extracted.method,
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
    return case


def run_case(
    case_dir: Path,
    store: EvidenceStore,
    investigator: ClaudeInvestigator | None = None,
    params: Params = DEFAULT_PARAMS,
) -> Verdict:
    case = load_case(case_dir, store)
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
    return build_verdict(store.corpus(), allegation, edges, figures, params)


def case_workspace(case_dir: Path, store: EvidenceStore):
    """The recorded case as a workspace (for reports on offline runs)."""
    from caligula.agent.workspace import Mode, Workspace

    case = load_case(case_dir, store)
    from caligula.adapters.persistence.ledger_jsonl import JsonlLedger

    ws = Workspace(store=store, allegation=Allegation.model_validate(case["allegation"]), mode=Mode.INVESTIGATE,
                   ledger=JsonlLedger())
    for e in case["recorded_readings"]["edges"]:
        ws.record(EvidenceEdge.model_validate(e), "recorded")
    for f in case["recorded_readings"]["figures"]:
        ws.record(FinancialFigure.model_validate(f), "recorded")
    return ws


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
