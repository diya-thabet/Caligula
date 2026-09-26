"""Command-line entry point: argument parsing only."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from caligula.adapters.cli import commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="caligula")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="investigate a case directory")
    run.add_argument("case_dir", type=Path)
    run.add_argument("--live", dest="llm", nargs="?", const="claude", metavar="SPEC",
                     help="read the documents with a model instead of the recorded readings "
                          "(default claude; see --llm)")
    run.add_argument("--blobs", type=Path, default=Path("blobs"), help="content-addressed blob store")
    run.add_argument("--json", action="store_true", help="print the full verdict as JSON")
    run.add_argument("--db", help="PostgreSQL DSN; default is an in-memory store")
    run.add_argument("--report", type=Path, help="write the Markdown case file here")
    cal = sub.add_parser("calibrate", help="score labelled cases and sweep thresholds")
    cal.add_argument("root", type=Path)
    cal.add_argument("--blobs", type=Path, default=Path("blobs"))
    scr = sub.add_parser("screen", help="rank procurement awards by red flags")
    scr.add_argument("awards_json", type=Path)
    inv = sub.add_parser("investigate", help="run the investigator agents on a claim (needs a model API or server)")
    inv.add_argument("claim", help="claim or allegation text")
    inv.add_argument("--mode", choices=["factcheck", "investigate"], default="factcheck")
    inv.add_argument("--id", default="claim", help="case id")
    inv.add_argument("--case-dir", type=Path, help="preload documents from a case directory")
    inv.add_argument("--no-web", action="store_true", help="disable web search")
    inv.add_argument("--llm", metavar="SPEC", help="model for every role: claude[:MODEL] or openai:MODEL[@BASE_URL] "
                                                   "(default: $CALIGULA_LLM, else claude)")
    inv.add_argument("--analyst-llm", metavar="SPEC", help="model for intake, decomposition and planning")
    inv.add_argument("--collector-llm", metavar="SPEC", help="model for the source specialists / investigator")
    inv.add_argument("--reviewer-llm", metavar="SPEC", help="model for the reviewer (team mode)")
    inv.add_argument("--search", choices=["searxng", "brave"], default=os.environ.get("CALIGULA_SEARCH"),
                     help="our own web search engine (needed for OpenAI-compatible models; default: the "
                          "provider's built-in search, Claude only)")
    inv.add_argument("--blobs", type=Path, default=Path("blobs"))
    inv.add_argument("--db", help="PostgreSQL DSN; default is an in-memory store")
    inv.add_argument("--team", action="store_true", help="parallel source specialists + reviewer")
    inv.add_argument("--rounds", type=int, default=8,
                     help="hard cap on collection rounds in team mode (the loop stops earlier when the case is "
                          "settled or exhausted)")
    inv.add_argument("--max-tool-calls", type=int, default=600, help="hard cap on tool calls across all agents")
    inv.add_argument("--rubric", type=Path, help="expert review rubric (text file) for the reviewer")
    inv.add_argument("--ledger", type=Path, default=Path("ledger.jsonl"), help="evidence ledger file")
    inv.add_argument("--legal-approved", metavar="NAME", help="lawyer who approved the scope, when intake requires it")
    inv.add_argument("--poc", action=argparse.BooleanOptionalAction, default=True,
                     help="proof-of-concept mode: cases needing legal review proceed, outputs are marked "
                          "internal and not for publication (default on)")
    inv.add_argument("--report", type=Path, help="write the Markdown case file here (default out/<id>.md)")
    srv = sub.add_parser("serve", help="the HTTP API for the investigation interface (needs the api extra)")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    srv.add_argument("--llm", metavar="SPEC", default=os.environ.get("CALIGULA_LLM"),
                     help="model for every role, as for investigate; without one, the API only serves "
                          "replayed cases (default: $CALIGULA_LLM)")
    srv.add_argument("--analyst-llm", metavar="SPEC")
    srv.add_argument("--collector-llm", metavar="SPEC")
    srv.add_argument("--reviewer-llm", metavar="SPEC")
    srv.add_argument("--search", choices=["searxng", "brave"], default=os.environ.get("CALIGULA_SEARCH"))
    srv.add_argument("--no-web", action="store_true", help="disable web search")
    srv.add_argument("--rounds", type=int, default=8)
    srv.add_argument("--max-tool-calls", type=int, default=600)
    srv.add_argument("--replay", type=Path, action="append", default=[], metavar="CASE_DIR",
                     help="add a recorded case directory for review (repeatable)")
    srv.add_argument("--ledgers", type=Path, help="directory for one ledger file per case (default: in memory)")
    srv.add_argument("--cors", action="append", default=[], metavar="ORIGIN",
                     help="allow a browser interface served from this origin (repeatable)")
    srv.add_argument("--blobs", type=Path, default=Path("blobs"))
    srv.add_argument("--db", help="PostgreSQL DSN; default is an in-memory store")
    args = parser.parse_args(argv)

    handlers = {"run": commands.run, "investigate": commands.investigate,
                "calibrate": commands.calibrate, "screen": commands.screen, "serve": commands.serve}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
