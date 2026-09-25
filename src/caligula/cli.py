from __future__ import annotations

import argparse
import sys
from pathlib import Path

from caligula.case import run_case
from caligula.models import Verdict
from caligula.store import BlobStore, EvidenceStore, MemoryEvidenceStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="caligula")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="investigate a case directory")
    run.add_argument("case_dir", type=Path)
    run.add_argument("--live", action="store_true", help="use Claude instead of the recorded readings")
    run.add_argument("--blobs", type=Path, default=Path("blobs"), help="content-addressed blob store")
    run.add_argument("--json", action="store_true", help="print the full verdict as JSON")
    run.add_argument("--db", help="PostgreSQL DSN; default is an in-memory store")
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
    inv.add_argument("--rounds", type=int, default=2, help="collection rounds in team mode")
    inv.add_argument("--rubric", type=Path, help="expert review rubric (text file) for the reviewer")
    inv.add_argument("--ledger", type=Path, default=Path("ledger.jsonl"), help="evidence ledger file")
    inv.add_argument("--legal-approved", metavar="NAME", help="lawyer who approved the scope, when intake requires it")
    args = parser.parse_args(argv)

    if args.command == "investigate":
        return investigate(args)

    if args.command == "calibrate":
        return calibrate(args.root, BlobStore(args.blobs))
    if args.command == "screen":
        return screen_awards(args.awards_json)

    investigator = None
    if args.live:
        from caligula.llm.claude import ClaudeInvestigator

        investigator = ClaudeInvestigator()
    verdict = run_case(args.case_dir, open_store(args.db, BlobStore(args.blobs)), investigator)
    print(verdict.model_dump_json(indent=2) if args.json else summarize(verdict))
    return 0


def investigate(args: argparse.Namespace) -> int:
    from caligula.agent.reply import public_reply
    from caligula.agent.runner import InvestigatorAgent
    from caligula.agent.team import InvestigationTeam
    from caligula.agent.workspace import Connectors, Mode, Workspace
    from caligula.case import load_case
    from caligula.ingest.sources import LiveFetcher, WorldBankClient
    from caligula.ingest.telegram import TelegramClient
    from caligula.ingest.wayback import WaybackClient
    from caligula.ledger import Ledger
    from caligula.llm.claude import ClaudeInvestigator
    from caligula.policy import Decision, decide

    ledger = Ledger(args.ledger)
    llm = ClaudeInvestigator()
    intake = llm.classify(args.claim)
    decision = decide(intake)
    ledger.append("intake", "caligula", case_id=args.id, decision=decision.decision.value,
                  reasons=decision.reasons, intake=intake.model_dump(mode="json"))
    print(f"Intake: {decision.decision} ({intake.claim_type}; subjects {[str(s) for s in intake.subject_types]})")
    for reason in decision.reasons:
        print(f"  - {reason}")
    if decision.decision == Decision.REFUSE:
        return 2
    if decision.decision == Decision.LEGAL_REVIEW:
        if not args.legal_approved:
            print("Stopped: a lawyer must approve the scope first (re-run with --legal-approved NAME).")
            return 3
        ledger.append("legal_approval", args.legal_approved, case_id=args.id, scope=args.claim)

    store = open_store(args.db, BlobStore(args.blobs))
    if args.case_dir:
        load_case(args.case_dir, store)
    mode = Mode(args.mode)
    allegation = llm.decompose(args.id, args.claim)
    connectors = Connectors(wayback=WaybackClient(), live=LiveFetcher(), funders=WorldBankClient(),
                            telegram=TelegramClient())
    ws = Workspace(store=store, allegation=allegation, mode=mode, connectors=connectors, ledger=ledger)
    if args.team:
        rubric = args.rubric.read_text(encoding="utf-8") if args.rubric else ""
        result = InvestigationTeam(web_search=not args.no_web, rubric=rubric, max_rounds=args.rounds).run(ws)
        narrative = result.review
        for name, reports in result.reports.items():
            print(f"\n[{name}] " + "\n  ".join(reports))
    else:
        result = InvestigatorAgent(web_search=not args.no_web).run(ws)
        narrative = result.summary

    print("\n" + summarize(result.verdict))
    print(f"\n{'Review' if args.team else 'Agent summary'} ({len(result.trace)} tool calls):\n{narrative}")
    if result.unknown_citations:
        print(f"\nWARNING: summary cites unknown documents: {result.unknown_citations}")
    print(f"\nPublic reply:\n{public_reply(result, mode, store, args.claim)}")
    broken = ledger.verify()
    print(f"\nLedger: {len(ledger.entries)} entries, head {ledger.head[:16]}, "
          f"{'intact' if broken is None else f'BROKEN at entry {broken}'}")
    if hasattr(store, "save_investigation"):
        store.save_investigation(
            args.id, mode.value, allegation.model_dump(mode="json"), result.verdict.model_dump(mode="json"),
            [vars(t) for t in result.trace],
        )
    return 0


def calibrate(root: Path, blobs: BlobStore) -> int:
    from caligula.calibration import evaluate, labelled_cases, sweep

    cases = labelled_cases(root)
    if not cases:
        print(f"no labels.json under {root}")
        return 1
    print(f"{len(cases)} labelled case(s); current parameters: {evaluate(cases, blobs)}")
    for params, metrics in sweep(cases, blobs)[:5]:
        print(f"  strong={params.strong} weak={params.weak} retcon_penalty={params.retconned_penalty}: {metrics}")
    return 0


def screen_awards(path: Path) -> int:
    import json

    from caligula.redflags import Award, screen

    awards = {a["id"]: Award.model_validate(a) for a in json.loads(path.read_text(encoding="utf-8"))["awards"]}
    for s in screen(list(awards.values())):
        a = awards[s.subject_id]
        print(f"{s.score:5.2f}  {a.id}  {a.buyer} -> {a.supplier}  {a.amount_tnd:,.0f} TND  {a.object}")
        for f in s.flags:
            print(f"         - {f.code}: {f.detail}")
    print("\nRed flags are reasons to look, not evidence of wrongdoing.")
    return 0


def open_store(dsn: str | None, blobs: BlobStore) -> EvidenceStore:
    if not dsn:
        return MemoryEvidenceStore(blobs)
    from caligula.pg import PostgresEvidenceStore

    store = PostgresEvidenceStore(dsn, blobs)
    store.init_schema()
    return store


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
