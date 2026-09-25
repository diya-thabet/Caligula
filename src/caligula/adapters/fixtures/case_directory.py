"""Case directories on disk: case.json, document files, optional labels.json.

Offline mode replays the readings recorded in case.json; live mode asks an
analyst to decompose the allegation and read every document.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from caligula.adapters.media.text_extraction import extract_text
from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.application.evidence_store import EvidenceStore
from caligula.application.investigation.workspace import Mode, Workspace
from caligula.application.ports.llm import ClaimAnalyst
from caligula.application.usecases.calibration import LabelledCase
from caligula.application.usecases.evaluate_case import evaluate_readings, evaluate_with_analyst
from caligula.domain.model.claims import Allegation
from caligula.domain.model.documents import SourceKind
from caligula.domain.model.evidence import EvidenceEdge, FinancialFigure
from caligula.domain.model.verdict import Verdict
from caligula.domain.services.scoring import DEFAULT_PARAMS, Params


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


def recorded_readings(case: dict) -> tuple[Allegation, list[EvidenceEdge], list[FinancialFigure]]:
    readings = case["recorded_readings"]
    return (
        Allegation.model_validate(case["allegation"]),
        [EvidenceEdge.model_validate(e) for e in readings["edges"]],
        [FinancialFigure.model_validate(f) for f in readings["figures"]],
    )


def run_case(
    case_dir: Path,
    store: EvidenceStore,
    analyst: ClaimAnalyst | None = None,
    params: Params = DEFAULT_PARAMS,
) -> Verdict:
    case = load_case(case_dir, store)
    allegation, edges, figures = recorded_readings(case)
    if analyst is None:
        return evaluate_readings(store, allegation, edges, figures, params)
    return evaluate_with_analyst(store, analyst, allegation.id, allegation.text, params)


def case_workspace(case_dir: Path, store: EvidenceStore) -> Workspace:
    """The recorded case as a workspace (for reports on offline runs)."""
    allegation, edges, figures = recorded_readings(load_case(case_dir, store))
    ws = Workspace(store=store, allegation=allegation, mode=Mode.INVESTIGATE, ledger=JsonlLedger())
    for item in [*edges, *figures]:
        ws.record(item, "recorded")
    return ws


def labelled_cases(root: Path, new_store: Callable[[], EvidenceStore]) -> list[LabelledCase]:
    """Every case directory under `root` that has a labels.json."""
    cases = []
    for labels_path in sorted(root.rglob("labels.json")):
        case_dir = labels_path.parent

        def evaluate(params: Params, case_dir: Path = case_dir) -> Verdict:
            return run_case(case_dir, new_store(), params=params)

        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        cases.append(LabelledCase(name=case_dir.name, labels=labels, evaluate=evaluate))
    return cases


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
