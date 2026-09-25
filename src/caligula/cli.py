from __future__ import annotations

import argparse
import sys
from pathlib import Path

from caligula.adapters.fixtures.case_directory import run_case
from caligula.adapters.persistence.blob_fs import FileBlobStorage
from caligula.adapters.persistence.memory import MemoryDocumentRepository
from caligula.application.evidence_store import EvidenceStore
from caligula.domain.model.verdict import Verdict


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

    if args.command == "investigate":
        return investigate(args)

    if args.command == "calibrate":
        return calibrate(args.root, FileBlobStorage(args.blobs))
    if args.command == "screen":
        return screen_awards(args.awards_json)

    investigator = None
    if args.live:
        from caligula.adapters.llm.claude_analyst import ClaudeAnalyst

        investigator = ClaudeAnalyst()
    store = open_store(args.db, FileBlobStorage(args.blobs))
    verdict = run_case(args.case_dir, store, investigator)
    print(verdict.model_dump_json(indent=2) if args.json else summarize(verdict))
    if args.report:
        from caligula.adapters.fixtures.case_directory import case_workspace
        from caligula.report import build_report

        ws = case_workspace(args.case_dir, store)
        write_report(args.report, build_report(ws, ws.verdict()))
    return 0


def write_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"\nCase file written to {path}")


def investigate(args: argparse.Namespace) -> int:
    from caligula.adapters.fixtures.case_directory import load_case
    from caligula.adapters.llm.claude_analyst import ClaudeAnalyst
    from caligula.adapters.llm.claude_runner import ClaudeAgentRunner
    from caligula.adapters.media.text_extraction import PopplerTesseractExtractor
    from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
    from caligula.adapters.presenters.public_reply import public_reply
    from caligula.adapters.sources.telegram import TelegramClient
    from caligula.adapters.sources.wayback import WaybackClient
    from caligula.adapters.sources.web import LiveFetcher
    from caligula.adapters.sources.worldbank import WorldBankClient
    from caligula.application.investigation.single_agent import InvestigatorAgent
    from caligula.application.investigation.team import InvestigationTeam
    from caligula.application.investigation.workspace import Connectors, Mode, Workspace
    from caligula.application.usecases.intake import admit
    from caligula.domain.model.intake import Decision

    ledger = JsonlLedger(args.ledger)
    llm = ClaudeAnalyst()
    admission = admit(llm, ledger, args.id, args.claim, args.legal_approved, args.poc)
    intake, decision = admission.intake, admission.decision
    print(f"Intake: {decision.decision} ({intake.claim_type}; subjects {[str(s) for s in intake.subject_types]})")
    for reason in decision.reasons + ([admission.note] if admission.note else []):
        print(f"  - {reason}")
    if not admission.proceed:
        return 2 if decision.decision == Decision.REFUSE else 3

    store = open_store(args.db, FileBlobStorage(args.blobs))
    if args.case_dir:
        load_case(args.case_dir, store)
    mode = Mode(args.mode)
    allegation = llm.decompose(args.id, args.claim)
    connectors = Connectors(wayback=WaybackClient(), live=LiveFetcher(), funders=WorldBankClient(),
                            telegram=TelegramClient(), extractor=PopplerTesseractExtractor())
    ws = Workspace(store=store, allegation=allegation, mode=mode, connectors=connectors, ledger=ledger)
    if args.team:
        rubric = args.rubric.read_text(encoding="utf-8") if args.rubric else ""
        team = InvestigationTeam(runner=ClaudeAgentRunner(), analyst=llm, web_search=not args.no_web,
                                 rubric=rubric, max_rounds=args.rounds,
                                 on_event=lambda phase, detail: print(f"[{phase}] {detail}", flush=True))
        result = team.run(ws)
        narrative = result.review
        print(f"\nStopped after {len(result.rounds)} round(s): {result.stop_reason}")
    else:
        result = InvestigatorAgent(ClaudeAgentRunner(), web_search=not args.no_web).run(ws)
        narrative = result.summary

    print("\n" + summarize(result.verdict))
    print(f"\n{'Review' if args.team else 'Agent summary'} ({len(result.trace)} tool calls):\n{narrative}")
    if result.unknown_citations:
        print(f"\nWARNING: summary cites unknown documents: {result.unknown_citations}")
    print(f"\nPublic reply:\n{public_reply(result, mode, store, args.claim)}")
    from caligula.report import build_report

    write_report(args.report or Path("out") / f"{args.id}.md",
                 build_report(ws, result.verdict, narrative, poc=args.poc,
                              stop_reason=getattr(result, "stop_reason", None)))
    broken = ledger.verify()
    print(f"\nLedger: {len(ledger.entries)} entries, head {ledger.head[:16]}, "
          f"{'intact' if broken is None else f'BROKEN at entry {broken}'}")
    if hasattr(store.repository, "save_investigation"):
        store.repository.save_investigation(
            args.id, mode.value, allegation.model_dump(mode="json"), result.verdict.model_dump(mode="json"),
            [vars(t) for t in result.trace],
        )
    return 0


def calibrate(root: Path, blobs: FileBlobStorage) -> int:
    from caligula.adapters.fixtures.case_directory import labelled_cases
    from caligula.application.usecases.calibration import evaluate, sweep

    def new_store() -> EvidenceStore:
        return EvidenceStore(MemoryDocumentRepository(), blobs)

    cases = labelled_cases(root, new_store)
    if not cases:
        print(f"no labels.json under {root}")
        return 1
    print(f"{len(cases)} labelled case(s); current parameters: {evaluate(cases)}")
    for params, metrics in sweep(cases)[:5]:
        print(f"  strong={params.strong} weak={params.weak} retcon_penalty={params.retconned_penalty}: {metrics}")
    return 0


def screen_awards(path: Path) -> int:
    import json

    from caligula.domain.model.procurement import Award
    from caligula.domain.services.red_flags import screen

    awards = {a["id"]: Award.model_validate(a) for a in json.loads(path.read_text(encoding="utf-8"))["awards"]}
    for s in screen(list(awards.values())):
        a = awards[s.subject_id]
        print(f"{s.score:5.2f}  {a.id}  {a.buyer} -> {a.supplier}  {a.amount_tnd:,.0f} TND  {a.object}")
        for f in s.flags:
            print(f"         - {f.code}: {f.detail}")
    print("\nRed flags are reasons to look, not evidence of wrongdoing.")
    return 0


def open_store(dsn: str | None, blobs: FileBlobStorage) -> EvidenceStore:
    if not dsn:
        return EvidenceStore(MemoryDocumentRepository(), blobs)
    from caligula.adapters.persistence.postgres import PostgresDocumentRepository

    repository = PostgresDocumentRepository(dsn)
    repository.init_schema()
    return EvidenceStore(repository, blobs)


def summarize(v: Verdict) -> str:
    lines = [f"Allegation {v.allegation_id}: {v.verdict.upper()} (confidence {v.confidence:.2f})", ""]
    lines.append("Sub-claims:")
    for c in v.by_subclaim:
        clusters = f"{len(c.supporting_clusters)} supporting / {len(c.contradicting_clusters)} contradicting clusters"
        lines.append(f"  {c.id} {c.status:<20} {clusters}  {c.statement}")
        if c.qualifying_docs:
            lines.append(f"     qualified by: {', '.join(c.qualifying_docs)}")
    lines += ["", "Hypotheses:"]
    lines += [f"  {h.id} {h.status:<11} {h.statement}  [{'; '.join(h.reasons)}]" for h in v.hypotheses]
    if v.retcon_flags:
        lines += ["", "Retcon flags:"]
        for f in v.retcon_flags:
            changes = "; ".join(f"{c.kind}: {c.removed} -> {c.added}" for c in f.changes)
            changes += " (OCR: verify against the scan)" if f.needs_review else ""
            lines.append(
                f"  {f.canonical_url}: {f.earlier_doc_id} ({f.earlier_observed_at:%Y-%m-%d}) -> "
                f"{f.later_doc_id} ({f.later_observed_at:%Y-%m-%d}): {changes}"
            )
    if v.financial:
        f = v.financial
        lines += [
            "",
            f"Financial: {f.reference_role} {f.reference_amount_tnd:,.0f} TND vs proven/benchmark "
            f"{f.proven_spend_tnd:,.0f} TND -> discrepancy {f.discrepancy_tnd:,.0f} TND "
            f"({f.discrepancy_ratio:.0%}, {f.independent_clusters} independent clusters, "
            f"{'FLAGGED' if f.flagged else 'not flagged'})",
        ]
    if v.rejected_evidence:
        lines += ["", "Rejected evidence:"]
        lines += [f"  {r.item}: {r.reason}" for r in v.rejected_evidence]
    if v.missing_evidence:
        lines += ["", "Missing evidence:"]
        lines += [f"  {m}" for m in v.missing_evidence]
    lines += ["", v.disclaimer]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
