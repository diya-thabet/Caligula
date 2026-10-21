"""The offline STEG case file, compared line by line with a reviewed copy.

Any change to validation, scoring, judgment or presentation that alters the
output shows up here as a diff. When the change is intended, regenerate with
`UPDATE_GOLDEN=1 pytest tests/e2e/test_golden_case_file.py` and review the diff
of the golden file in the same commit.
"""

import os
import re
from pathlib import Path

from caligula.adapters.fixtures.case_directory import case_workspace
from caligula.adapters.presenters.markdown_report import build_report
from conftest import FIXTURE
from support import assert_invariants

GOLDEN = Path(__file__).parent / "golden" / "steg_case_file.md"


def _stable(report: str) -> str:
    """Mask what legitimately changes between runs: the generation time and the
    ledger head (its entries carry timestamps)."""
    report = re.sub(r"^Generated \d{4}-\d\d-\d\d \d\d:\d\d UTC", "Generated <time> UTC", report, flags=re.M)
    return re.sub(r"head `[0-9a-f]{16}…`", "head `<hash>`", report)


def test_offline_case_file_matches_golden(store):
    ws = case_workspace(FIXTURE, store)
    report = _stable(build_report(ws, ws.verdict()))
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(report, encoding="utf-8")
    assert report == GOLDEN.read_text(encoding="utf-8")
    assert_invariants(ws)
