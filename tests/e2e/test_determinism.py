"""Same evidence, same verdict: the output must not depend on Python's hash seed.

Set iteration order changes between processes. Anything that leaks it into
the verdict (order of clusters, rows, dependencies) makes runs impossible to
compare or replay, so the offline case runs in separate processes with
different seeds and the full JSON verdicts, and the case files, must be
identical.
"""

import os
import re
import subprocess
import sys

from conftest import FIXTURE


def _run(seed: int, tmp_path) -> tuple[str, str]:
    """The JSON verdict and the case file (its generation time and ledger head masked)."""
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    report = tmp_path / f"case{seed}.md"
    out = subprocess.run([sys.executable, "-m", "caligula.adapters.cli.main", "run", str(FIXTURE), "--json",
                          "--blobs", str(tmp_path / f"blobs{seed}"), "--report", str(report)],
                         env=env, capture_output=True, text=True, check=True)
    verdict = out.stdout.split("\nCase file written to")[0]
    text = re.sub(r"^Generated .* UTC", "Generated", report.read_text(encoding="utf-8"), flags=re.M)
    return verdict, re.sub(r"head `[0-9a-f]+…`", "head", text)


def test_verdict_and_case_file_are_identical_across_hash_seeds(tmp_path):
    runs = [_run(seed, tmp_path) for seed in (0, 1, 2, 3)]
    assert len({verdict for verdict, _ in runs}) == 1, "the verdict depends on set iteration order"
    assert len({case_file for _, case_file in runs}) == 1, "the case file depends on set iteration order"
