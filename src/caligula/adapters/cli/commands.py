"""CLI commands. Each one wires adapters (via bootstrap) to a use case and prints the result."""

from __future__ import annotations

import argparse
from pathlib import Path

from caligula.adapters.cli.bootstrap import claude, live_connectors, memory_store, open_store
from caligula.adapters.fixtures.case_directory import case_workspace, run_case
from caligula.adapters.presenters.cli_summary import summarize
from caligula.adapters.presenters.markdown_report import build_report


def run(args: argparse.Namespace) -> int:
    analyst = claude()[0] if args.live else None
    store = open_store(args.db, args.blobs)
    verdict = run_case(args.case_dir, store, analyst)
    print(verdict.model_dump_json(indent=2) if args.json else summarize(verdict))
    if args.report:
        ws = case_workspace(args.case_dir, store)
        write_report(args.report, build_report(ws, ws.verdict()))
    return 0


def write_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"\nCase file written to {path}")


def investigate(args: argparse.Namespace) -> int:
    from caligula.adapters.fixtures.case_directory import load_case
    from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
    from caligula.adapters.presenters.public_reply import public_reply
    from caligula.application.investigation.single_agent import InvestigatorAgent
    from caligula.application.investigation.team import InvestigationTeam
    from caligula.application.investigation.workspace import Mode, Workspace
    from caligula.application.usecases.intake import admit
    from caligula.domain.model.intake import Decision

    ledger = JsonlLedger(args.ledger)
    llm, runner = claude()
    admission = admit(llm, ledger, args.id, args.claim, args.legal_approved, args.poc)
    intake, decision = admission.intake, admission.decision
    print(f"Intake: {decision.decision} ({intake.claim_type}; subjects {[str(s) for s in intake.subject_types]})")
    for reason in decision.reasons + ([admission.note] if admission.note else []):
        print(f"  - {reason}")
    if not admission.proceed:
        return 2 if decision.decision == Decision.REFUSE else 3

    store = open_store(args.db, args.blobs)
    if args.case_dir:
        load_case(args.case_dir, store)
    mode = Mode(args.mode)
    allegation = llm.decompose(args.id, args.claim)
    ws = Workspace(store=store, allegation=allegation, mode=mode, connectors=live_connectors(), ledger=ledger)
    if args.team:
        rubric = args.rubric.read_text(encoding="utf-8") if args.rubric else ""
        team = InvestigationTeam(runner=runner, analyst=llm, web_search=not args.no_web,
                                 rubric=rubric, max_rounds=args.rounds,
                                 on_event=lambda phase, detail: print(f"[{phase}] {detail}", flush=True))
        result = team.run(ws)
        narrative = result.review
        print(f"\nStopped after {len(result.rounds)} round(s): {result.stop_reason}")
    else:
        result = InvestigatorAgent(runner, web_search=not args.no_web).run(ws)
        narrative = result.summary

    print("\n" + summarize(result.verdict))
    print(f"\n{'Review' if args.team else 'Agent summary'} ({len(result.trace)} tool calls):\n{narrative}")
    if result.unknown_citations:
        print(f"\nWARNING: summary cites unknown documents: {result.unknown_citations}")
    print(f"\nPublic reply:\n{public_reply(result, mode, store, args.claim)}")
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


def calibrate(args: argparse.Namespace) -> int:
    from caligula.adapters.fixtures.case_directory import labelled_cases
    from caligula.application.usecases.calibration import evaluate, sweep

    cases = labelled_cases(args.root, lambda: memory_store(args.blobs))
    if not cases:
        print(f"no labels.json under {args.root}")
        return 1
    print(f"{len(cases)} labelled case(s); current parameters: {evaluate(cases)}")
    for params, metrics in sweep(cases)[:5]:
        print(f"  strong={params.strong} weak={params.weak} retcon_penalty={params.retconned_penalty}: {metrics}")
    return 0


def screen(args: argparse.Namespace) -> int:
    import json

    from caligula.domain.model.procurement import Award
    from caligula.domain.services.red_flags import screen as screen_awards

    records = json.loads(args.awards_json.read_text(encoding="utf-8"))["awards"]
    awards = {a["id"]: Award.model_validate(a) for a in records}
    for s in screen_awards(list(awards.values())):
        a = awards[s.subject_id]
        print(f"{s.score:5.2f}  {a.id}  {a.buyer} -> {a.supplier}  {a.amount_tnd:,.0f} TND  {a.object}")
        for f in s.flags:
            print(f"         - {f.code}: {f.detail}")
    print("\nRed flags are reasons to look, not evidence of wrongdoing.")
    return 0



