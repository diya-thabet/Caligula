"""Command-line entry point: argument parsing only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from caligula.adapters.cli import commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="caligula")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="investigate a case directory")
    run.add_argument("case_dir", type=Path)
    run.add_argument("--live", action="store_true", help="use Claude instead of the recorded readings")
    run.add_argument("--blobs", type=Path, default=Path("blobs"), help="content-addressed blob store")
    run.add_argument("--json", action="store_true", help="print the full verdict as JSON")
    run.add_argument("--db", help="PostgreSQL DSN; default is an in-memory store")
    run.add_argument("--report", type=Path, help="write the Markdown case file here")
    cal = sub.add_parser("calibrate", help="score labelled cases and sweep thresholds")
    cal.add_argument("root", type=Path)
    cal.add_argument("--blobs", type=Path, default=Path("blobs"))
    scr = sub.add_parser("screen", help="rank procurement awards by red flags")
    scr.add_argument("awards_json", type=Path)
    inv = sub.add_parser("investigate", help="run the investigator agent on a claim (needs Claude API access)")
    inv.add_argument("claim", help="claim or allegation text")
    inv.add_argument("--mode", choices=["factcheck", "investigate"], default="factcheck")
    inv.add_argument("--id", default="claim", help="case id")
    inv.add_argument("--case-dir", type=Path, help="preload documents from a case directory")
    inv.add_argument("--no-web", action="store_true", help="disable web search")
    inv.add_argument("--blobs", type=Path, default=Path("blobs"))
    inv.add_argument("--db", help="PostgreSQL DSN; default is an in-memory store")
    inv.add_argument("--team", action="store_true", help="parallel source specialists + reviewer")
    inv.add_argument("--rounds", type=int, default=3, help="maximum collection rounds in team mode")
    inv.add_argument("--rubric", type=Path, help="expert review rubric (text file) for the reviewer")
    inv.add_argument("--ledger", type=Path, default=Path("ledger.jsonl"), help="evidence ledger file")
    inv.add_argument("--legal-approved", metavar="NAME", help="lawyer who approved the scope, when intake requires it")
    inv.add_argument("--poc", action=argparse.BooleanOptionalAction, default=True,
                     help="proof-of-concept mode: cases needing legal review proceed, outputs are marked "
                          "internal and not for publication (default on)")
    inv.add_argument("--report", type=Path, help="write the Markdown case file here (default out/<id>.md)")
    args = parser.parse_args(argv)

    handlers = {"run": commands.run, "investigate": commands.investigate,
                "calibrate": commands.calibrate, "screen": commands.screen}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
