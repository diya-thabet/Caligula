"""The case file's judgment part: bottom line first, each key judgment citing the
evidence behind it, and indicators pointing the right way."""

import re

from caligula.adapters.fixtures.case_directory import case_workspace
from caligula.adapters.presenters.analytic import bottom_line, indicators, key_judgments
from caligula.adapters.presenters.markdown_report import build_report
from caligula.domain.model.evidence import EvidenceEdge, Relation
from conftest import FIXTURE


def section(report, title):
    body = report.split(f"\n{title}\n", 1)[1]
    return re.split(r"\n#{1,2} ", body, maxsplit=1)[0]


def test_the_bottom_line_comes_before_everything_else(store):
    ws = case_workspace(FIXTURE, store)
    report = build_report(ws, ws.verdict(), stop_reason="exhausted")
    first = re.findall(r"^## .+", report, flags=re.M)[0]
    assert first == "## Bottom line"
    top = section(report, "## Bottom line")
    assert top.lstrip().startswith("**High suspicion.** The core facts (C3, C4, C5, C6) are, taken together, "
                                   "very likely (87%) true, with **moderate** confidence.")
    assert "- Innocent explanation(s) refuted: H4." in top
    assert "it would change without `benchmark` or without `sentinel`" in top
    assert "- Investigation stopped: exhausted:" in top


def test_every_evidence_id_a_judgment_cites_is_in_the_annex(store):
    ws = case_workspace(FIXTURE, store)
    v = ws.verdict()
    report = build_report(ws, v)
    judgments = section(report, "## Key judgments")
    cited = set(re.findall(r"\bE\d+\b", judgments))
    # Every counted item backs some judgment, except the rewritten amount the financial check sets aside.
    unused = {eid for eid, item in ws.counted().items() if item in ws.figures and item not in v.financial.figures}
    assert unused == {"E20"} and cited == set(ws.counted()) - unused
    annex = report.split("# Annexes", 1)[1]
    assert all(f"**{eid}**" in annex for eid in cited)


def test_judgments_state_likelihood_and_confidence_and_what_caps_it(store):
    ws = case_workspace(FIXTURE, store)
    lines = "\n".join(key_judgments(ws, ws.verdict()))
    assert ("### C5 (core). The contract was awarded without a competitive tender.\n\n"
            "**supported** · almost certain (over 99%) true · confidence **moderate**") in lines
    assert "- For: E13, E14, E15 (3 independent origin(s))\n- Against: none\n- Qualifying: E16" in lines
    assert "- Confidence capped by: C5 supported but never challenged" in lines
    # Unverified side sub-claims with no evidence are gaps, not judgments.
    assert "### C7." not in lines and "### C9." in lines


def test_indicators_point_the_right_way(store):
    ws = case_workspace(FIXTURE, store)
    text = "\n".join(indicators(ws, ws.verdict()))
    weaken, strengthen = text.split("Would strengthen it:")
    # A tender notice would exist if C5 were false: finding it weakens, its absence strengthens.
    assert "C5 would be contradicted by finding: TUNEPS tender notice" in weaken
    assert "C5 would be supported if a proper search of TUNEPS finds no" in strengthen
    # An award notice would exist if C3 were true: its absence weakens.
    assert "C3 would be contradicted if a proper search of Journal Officiel (JORT) finds no" in weaken
    # The refuted emergency explanation is watched, but only on what tells it apart (C9, not C5).
    assert "Evidence for H4 (would reopen it): A documented emergency" in weaken
    assert "Evidence for H4 (would reopen it): The contract was awarded" not in weaken


def test_a_fitting_innocent_explanation_is_in_the_bottom_line(store):
    ws = case_workspace(FIXTURE, store)
    # A strong document supporting the emergency, and nothing against it any more.
    ws.edges = [e for e in ws.edges if e.subclaim_id != "C9"]
    ws.absences = [f for f in ws.absences if f.subclaim_id != "C9"]
    ws.record(EvidenceEdge(doc_id="steg_procedure", subclaim_id="C9", relation=Relation.SUPPORTS,
                           quote="procédure d'urgence prévue par le décret n° 2026-0412"), "t")
    v = ws.verdict()
    top = "\n".join(bottom_line(ws, v))
    if any(h.id == "H4" and h.status == "consistent" for h in v.hypotheses):
        assert "fit the evidence: H4" in top and v.verdict != "high_suspicion"
    else:
        assert "not yet settled: H4" in top
