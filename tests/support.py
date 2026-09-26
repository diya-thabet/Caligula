"""Helpers shared by application tests: a scripted AgentRunner and a workspace on the STEG fixture."""



from caligula.adapters.fixtures.case_directory import load_case
from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.application.investigation.workspace import Mode, Workspace
from caligula.application.ports.llm import ToolRefusal
from caligula.domain.model.claims import Allegation
from caligula.domain.services.innocent import ensure_innocent_explanations
from conftest import FIXTURE


def play(tools, script, record):
    """Plays scripted tool calls through the real tool functions, as a model would."""
    by_name = {t.__name__: t for t in tools}
    script = list(script)
    while script:
        name, args = script.pop(0)
        if name == "__expand__":  # decide the next calls from the live workspace state
            script[:0] = args()
            continue
        try:
            out, err = by_name[name](**args), False
        except ToolRefusal as exc:  # returned to the model as a tool error
            out, err = str(exc), True
        record.append((name, err, out))


class ScriptedAgentRunner:
    """Fake `AgentRunner`: `script_for(system, brief)` returns (script, record) for each agent run."""

    def __init__(self, script_for, calls=None):
        self.script_for = script_for
        self.calls = [] if calls is None else calls

    def run(self, system, tools, brief, max_iterations, done, web_search=False, deep=False):
        self.calls.append({"system": system, "tools": tools, "brief": brief, "web_search": web_search,
                           "max_iterations": max_iterations, "deep": deep})
        script, record = self.script_for(system, brief)
        play(tools, script, record)
        return "end_turn"


def workspace(store, mode=Mode.INVESTIGATE, **kw):
    """The synthetic case as `decompose_case` would hand it over: completed with the innocent explanations."""
    case = load_case(FIXTURE, store)
    allegation, _ = ensure_innocent_explanations(Allegation.model_validate(case["allegation"]))
    return Workspace(store=store, allegation=allegation, mode=mode, ledger=JsonlLedger(), **kw)


def assert_invariants(ws, verdict=None):
    """Properties that must hold after any run, whatever the agents did.

    Workflow tests call this on their final state, so a change anywhere in the
    chain that breaks one of the engine's guarantees fails loudly.
    """
    from caligula.adapters.presenters.markdown_report import build_report
    from caligula.application.investigation.plan import TaskStatus
    from caligula.application.investigation.workspace import ProposalStatus
    from caligula.domain.model.evidence import EvidenceEdge
    from caligula.domain.services.absence import validate_absences
    from caligula.domain.services.ach import rate
    from caligula.domain.services.validation import validate_edges, validate_figures

    v = verdict or ws.verdict()
    corpus = ws.store.corpus()
    # 1. What counts is valid: quotes verbatim, dates coherent, bytes intact, absences checkable.
    assert validate_edges(corpus, ws.allegation, ws.edges)[1] == []
    assert validate_figures(corpus, ws.figures)[1] == []
    assert validate_absences(corpus, ws.allegation, ws.absences)[1] == []
    # 2. With review, only accepted proposals count, and every accepted proposal counts.
    if ws.review_required:
        accepted = [p.item for p in ws.proposals if p.status == ProposalStatus.ACCEPTED]
        counted = [*ws.edges, *ws.figures, *ws.absences]
        assert all(item in counted for item in accepted) and all(item in accepted for item in counted)
    # 3. Weighed evidence is exactly the counted edges and absences.
    assert len(v.weighed) == len(ws.edges) + len(ws.absences)
    assert {w.doc_id for w in v.weighed if w.kind == "edge"} == {e.doc_id for e in ws.edges}
    # 4. Tasks: closed ones have an outcome, open ones do not.
    for t in ws.tasks:
        assert (t.status == TaskStatus.DONE) == (t.outcome is not None), t.id
    # 5. The ledger is intact and records every proposal and review decision.
    assert ws.ledger.verify() is None
    actions = [e.action for e in ws.ledger.entries]
    assert actions.count("proposal") == len(ws.proposals)
    # 6. The verdict follows its own rules.
    core = {c.id: c for c in v.by_subclaim if c.id in ws.allegation.core_subclaims}
    if v.verdict == "high_suspicion":
        assert all(c.status == "supported" for c in core.values())
        innocent = {h.id for h in ws.allegation.hypotheses if h.kind == "innocent"}
        assert not any(h.status == "consistent" for h in v.hypotheses if h.id in innocent)
    no_evidence = any(c.support == 0 and c.contradiction == 0 for c in core.values())
    assert (v.likelihood is None) == (no_evidence or not core)
    assert v.confidence in ("low", "moderate", "high") and v.confidence_reasons
    # 7. Every ACH rating follows from the hypotheses' predictions.
    hyps = {h.id: h for h in ws.allegation.hypotheses}
    for m in v.ach:
        for r in m.rows:
            assert r.ratings == {h: rate(hyps[h], r.subclaim_id, r.relation) for h in m.hypotheses}
        assert set(m.ranking) | set(m.untested) == set(m.hypotheses)
    # 8. Dependencies name origins the evidence actually used.
    used = {w.doc_id for w in v.weighed} | ({f.doc_id for f in v.financial.figures} if v.financial else set())
    assert all(set(d.origin) <= used for d in v.depends_on)
    # 9. Suspicions: every active one is tested both ways and its status follows its sub-claim;
    #    rejected or held ones get no work.
    statuses = {c.id: c.status for c in v.by_subclaim}
    expected = {"supported": "confirmed", "contradicted": "refuted"}
    for s in ws.suspicions:
        if s.status in ("rejected", "awaiting_scope"):
            assert not s.task_ids and s.subclaim_id is None, s.id
            continue
        purposes = sorted(t.purpose for t in ws.tasks if t.id in s.task_ids)
        assert purposes == ["challenge", "support"], s.id
        assert s.status == expected.get(statuses[s.subclaim_id], "open"), s.id
    # 10. The case file builds, has its sections in the analytic order (judgment first, annexes
    #     after), and every quoted edge appears in it.
    report = build_report(ws, v)
    sections = ["## Bottom line", "## Claim", "## Key judgments", "## Alternatives considered", "## Key assumptions",
                "## What the conclusion depends on", "## Gaps and collection requests",
                "## Indicators that would change the assessment", "## Limits of this assessment", "# Annexes",
                "## Sub-claims", "## Competing hypotheses", "## Timeline", "## Integrity"]
    positions = [report.find(f"\n{s}\n") for s in sections]
    assert -1 not in positions, [s for s, p in zip(sections, positions, strict=True) if p == -1]
    assert positions == sorted(positions), "sections out of order"
    for p in ws.proposals:
        if isinstance(p.item, EvidenceEdge):
            assert p.item.quote in report
    # 11. A checked summary publishes no failing sentence, and cites only evidence that counts.
    if ws.attribution is not None:
        import re

        published = ws.attribution.published()
        assert not any(s.text in published for s in ws.attribution.failures)
        assert set(re.findall(r"\bE\d+\b", published)) <= set(ws.counted())
    return report


def scripted_team(scripts, record=None, briefs=None):
    """A team runner whose agents play `scripts[(agent, round)]`, the round read from their brief
    (a specialist first called in round 2 plays its round-2 script); the reviewer's final rewrite
    plays `scripts[("reviewer", "rewrite")]`."""
    import re

    from caligula.application.investigation.prompts import SPECIALIST_FOCUS

    record = {} if record is None else record
    briefs = {} if briefs is None else briefs

    def script_for(system, brief):
        agent = "reviewer" if system.startswith("You are the reviewer") else next(
            name for name, focus in SPECIALIST_FOCUS.items() if focus in system)
        if "<your_summary>" in brief:  # the reviewer asked to rewrite sentences the judge did not find backed
            briefs[(agent, "rewrite")] = brief
            return scripts.get((agent, "rewrite"), []), record.setdefault((agent, "rewrite"), [])
        n = int(re.search(r'<your_tasks round="(\d+)">|Round (\d+) of at most', brief).group(1)
                or re.search(r"Round (\d+) of at most", brief).group(1))
        briefs[(agent, n)] = brief
        return scripts.get((agent, n), []), record.setdefault((agent, n), [])

    return ScriptedAgentRunner(script_for)
