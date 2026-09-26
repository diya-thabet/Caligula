"""CLI commands. Each one wires adapters (via bootstrap) to a use case and prints the result."""

from __future__ import annotations

import argparse
from pathlib import Path

from caligula.adapters.cli.bootstrap import live_connectors, memory_store, open_store
from caligula.adapters.cli.models import analyst_for, check_web_search, models_from, parse_spec, search_from
from caligula.adapters.fixtures.case_directory import case_workspace, run_case
from caligula.adapters.presenters.cli_summary import summarize
from caligula.adapters.presenters.markdown_report import build_report


def run(args: argparse.Namespace) -> int:
    analyst = analyst_for(parse_spec(args.llm)) if args.llm else None
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
    from caligula.application.investigation.team import STOP_REASONS, InvestigationTeam
    from caligula.application.investigation.workspace import Mode, Workspace
    from caligula.application.usecases.decompose import decompose_case
    from caligula.application.usecases.intake import admit
    from caligula.domain.model.intake import Decision

    ledger = JsonlLedger(args.ledger)
    models = models_from(args.llm, args.analyst_llm, args.collector_llm, args.reviewer_llm)
    search = search_from(args.search)
    check_web_search(models, search, web=not args.no_web)
    llm = models.analyst
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
    allegation, added = decompose_case(llm, args.id, args.claim)
    for note in added:
        print(f"  + {note}")
    ws = Workspace(store=store, allegation=allegation, mode=mode, connectors=live_connectors(search), ledger=ledger,
                   poc=args.poc)
    if args.team:
        rubric = args.rubric.read_text(encoding="utf-8") if args.rubric else ""
        team = InvestigationTeam(runner=models.collectors, reviewer_runner=models.reviewer, analyst=llm,
                                 web_search=not args.no_web,
                                 rubric=rubric, max_rounds=args.rounds, max_tool_calls=args.max_tool_calls,
                                 on_event=lambda phase, detail: print(f"[{phase}] {detail}", flush=True),
                                 judge=llm)
        result = team.run(ws)
        narrative = result.review
        print(f"\nStopped after {len(result.rounds)} round(s): {STOP_REASONS[result.stop_reason]}")
    else:
        result = InvestigatorAgent(models.collectors, web_search=not args.no_web, judge=llm).run(ws)
        narrative = result.summary

    print("\n" + summarize(result.verdict))
    print(f"\n{'Review' if args.team else 'Agent summary'} ({len(result.trace)} tool calls), as published "
          f"after the citation check:\n{ws.attribution.published() if ws.attribution else narrative}")
    if ws.attribution and ws.attribution.failures:
        print(f"  ({len(ws.attribution.failures)} sentence(s) removed; see the case file's sentence check)")
    if result.unknown_citations:
        print(f"\nWARNING: summary cites unknown documents: {result.unknown_citations}")
    print(f"\nPublic reply:\n{public_reply(result, mode, store, args.claim)}")
    write_report(args.report or Path("out") / f"{args.id}.md",
                 build_report(ws, result.verdict, narrative, poc=args.poc,
                              stop_reason=getattr(result, "stop_reason", None),
                              rounds=getattr(result, "rounds", None)))
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





def case_service(args: argparse.Namespace):
    """The case service the API serves: with an engine when a model is configured, and the
    replayed case directories added for review."""
    from caligula.adapters.fixtures.case_directory import case_workspace
    from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
    from caligula.application.cases.service import CaseService, Engine
    from caligula.application.investigation.team import InvestigationTeam

    store = open_store(args.db, args.blobs)
    engine = None
    if args.llm or args.analyst_llm:
        models = models_from(args.llm, args.analyst_llm, args.collector_llm, args.reviewer_llm)
        search = search_from(args.search)
        check_web_search(models, search, web=not args.no_web)

        def new_team(on_event):
            return InvestigationTeam(runner=models.collectors, reviewer_runner=models.reviewer,
                                     analyst=models.analyst, judge=models.analyst, web_search=not args.no_web,
                                     max_rounds=args.rounds, max_tool_calls=args.max_tool_calls, on_event=on_event)

        engine = Engine(analyst=models.analyst, new_team=new_team, store=store, connectors=live_connectors(search))
    if args.ledgers:
        args.ledgers.mkdir(parents=True, exist_ok=True)
    service = CaseService(engine, new_ledger=lambda case_id: JsonlLedger(
        args.ledgers / f"{case_id}.jsonl" if args.ledgers else None))
    for case_dir in args.replay:
        ws = case_workspace(case_dir, store)
        service.add_reviewed(ws, ws.allegation.text, by="replay")
    return service


def serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from caligula.adapters.api.app import create_app
    except ImportError:
        print("The API needs its extra: pip install -e '.[api]'")
        return 1
    service = case_service(args)
    if service.engine is None:
        print("No model configured (--llm or $CALIGULA_LLM): serving replayed cases only.")
    web = args.web if args.web and (args.web / "index.html").is_file() else None
    print(f"{len(service.cases)} case(s) loaded; API on http://{args.host}:{args.port}/api (docs at /docs)")
    print(f"Interface at http://{args.host}:{args.port}/" if web else
          "Interface not built (cd web && npm ci && npm run build): API only.")
    uvicorn.run(create_app(service, cors_origins=args.cors, static_dir=web), host=args.host, port=args.port)
    return 0
