"""Same evidence, same verdict: the output must not depend on Python's hash seed.

Set iteration order changes between processes. Anything that leaks it into
the verdict (order of clusters, rows, dependencies) makes runs impossible to
compare or replay, so the offline case runs in separate processes with
different seeds and the full JSON verdicts must be identical.
"""

import os
import subprocess
import sys

from conftest import FIXTURE


def _verdict_json(seed: int, tmp_path) -> str:
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    out = subprocess.run([sys.executable, "-m", "caligula.adapters.cli.main", "run", str(FIXTURE), "--json",
                          "--blobs", str(tmp_path / f"blobs{seed}")],
                         env=env, capture_output=True, text=True, check=True)
    return out.stdout


def test_verdict_is_identical_across_hash_seeds(tmp_path):
    runs = {seed: _verdict_json(seed, tmp_path) for seed in (0, 1, 2, 3)}
    assert len(set(runs.values())) == 1, "the verdict depends on set iteration order"
