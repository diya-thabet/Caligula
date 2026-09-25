from pathlib import Path

from caligula.adapters.fixtures.case_directory import labelled_cases
from caligula.adapters.persistence.memory import MemoryDocumentRepository
from caligula.application.evidence_store import EvidenceStore
from caligula.application.usecases.calibration import evaluate, sweep


def test_calibration_harness_on_synthetic_case(blobs):
    new_store = lambda: EvidenceStore(MemoryDocumentRepository(), blobs)  # noqa: E731
    cases = labelled_cases(Path(__file__).parents[2] / "fixtures", new_store)
    assert [c.name for c in cases] == ["steg_synthetic"]
    m = evaluate(cases)
    assert (m.verdict_accuracy, m.subclaim_accuracy) == (1.0, 1.0)
    assert m.brier < 0.01
    best_params, best = sweep(cases)[0]
    assert best.subclaim_accuracy == 1.0
