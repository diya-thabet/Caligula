import json
from pathlib import Path

from caligula.calibration import evaluate, labelled_cases, sweep
from caligula.redflags import Award, screen

AWARDS = Path(__file__).parent.parent / "fixtures" / "awards_synthetic.json"


def load_awards():
    return [Award.model_validate(a) for a in json.loads(AWARDS.read_text())["awards"]]


def test_screening_ranks_and_explains():
    results = {s.award_id: s for s in screen(load_awards())}
    top = results["2026-017"]
    assert {f.code for f in top.flags} == {
        "non_competitive_procedure", "no_prior_notice", "new_supplier", "price_above_estimate",
    }
    assert "2024-088" not in results  # open tender, 5 bids, near estimate: clean
    split = {f.code for f in results["2026-11"].flags}
    assert {"possible_splitting", "single_bidder", "supplier_dominance", "no_prior_notice"} <= split
    late = {f.code: f.detail for f in results["2026-020"].flags}
    assert late == {"short_submission_period": "10 days to submit", "inflating_amendments": "amendments add 38% to the award"}
    assert next(iter(screen(load_awards()))).award_id == "2026-017"


def test_calibration_harness_on_synthetic_case(blobs):
    cases = labelled_cases(Path(__file__).parent.parent / "fixtures")
    assert [c.name for c in cases] == ["steg_synthetic"]
    m = evaluate(cases, blobs)
    assert (m.verdict_accuracy, m.subclaim_accuracy) == (1.0, 1.0)
    assert m.brier < 0.01
    best_params, best = sweep(cases, blobs)[0]
    assert best.subclaim_accuracy == 1.0
