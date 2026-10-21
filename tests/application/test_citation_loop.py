"""The reviewer's summary in the loop: sent back once when code finds a sentence its
evidence does not carry, read by the judge at the end, rewritten once more if the
judge objects, and published without what still fails."""

from caligula.application.investigation.plan import Plan, Task
from caligula.application.investigation.team import InvestigationTeam, Specialist
from caligula.domain.model.attribution import JudgeRating
from support import assert_invariants, scripted_team, workspace

COLLECT = ["list_tasks", "complete_task", "search_evidence", "record_evidence", "report"]
TEAM = [Specialist("official", COLLECT, False)]
PLAN = Plan(entities=[], window=(None, None), budgets={"official": 30},
            tasks=[Task(id="T0", specialist="official", objective="award", subclaim_ids=["C3", "C5"])])


def collect(ws):
    return [("record_evidence", {"doc_id": "jort_award_v1", "subclaim_id": "C3", "relation": "supports",
                                 "quote": "extension de 450 MW", "rationale": "r"}),
            ("record_evidence", {"doc_id": "jort_award_v1", "subclaim_id": "C5", "relation": "supports",
                                 "quote": "par procédure de gré à gré", "rationale": "r"}),
            ("__expand__", lambda: [("complete_task", {"task_id": t.id, "outcome": "found", "note": "n"})
                                    for t in ws.open_tasks("official")]),
            ("report", {"summary": "award notice found"})]


def review(ws, *summaries):
    accept = ("__expand__", lambda: [("review_proposal", {"proposal_id": p.id, "decision": "accept", "note": "ok"})
                                     for p in ws.proposals if p.status == "pending"])
    return [accept, *[("complete_review", {"summary": s}) for s in summaries]]


class Judge:
    def __init__(self, supported):
        self.supported, self.calls = supported, []

    def judge(self, sentence, evidence):
        self.calls.append(sentence)
        span = next((span for key, span in self.supported.items() if key in sentence), "")
        return JudgeRating(rating="supported" if span else "unsupported", support_span=span,
                           missing="" if span else "not in the quote")


FIRST = "The award was worth 150 million TND [E1]."
SECOND = ("The award was made by direct agreement [E2]. It concerned a 450 MW extension [E1]. "
          "The contract was signed by Karim Ben Salah [E2].")
REWRITE = "The award was made by direct agreement [E2]. More collection is needed on the price."


def test_summary_is_sent_back_by_code_then_by_the_judge_then_published_clean(store):
    ws = workspace(store)
    record, briefs = {}, {}
    scripts = {("official", 1): collect(ws), ("reviewer", 1): review(ws, FIRST, SECOND),
               ("reviewer", "rewrite"): [("complete_review", {"summary": REWRITE})]}
    judge = Judge({"direct agreement": "par procédure de gré à gré"})
    team = InvestigationTeam(runner=scripted_team(scripts, record, briefs), specialists=TEAM, web_search=False,
                             max_rounds=1, judge=judge)
    result = team.run(ws, plan=PLAN)

    # 1. Code sends the first summary back: 150 million is in no cited quote.
    [(_, err, out), (_, second_err, _)] = [r for r in record[("reviewer", 1)] if r[0] == "complete_review"]
    assert err and "the figure 150 (150,000,000) is in none of the cited evidence" in out
    # 2. The second is accepted as is (one send-back per review); the judge reads it at the end
    #    and objects to the 450 MW sentence; code objects to the unnamed person.
    assert not second_err
    assert judge.calls[:2] == ["The award was made by direct agreement [E2].",
                               "It concerned a 450 MW extension [E1]."]
    # 3. The reviewer rewrites once, with the failing sentences and their reasons in its brief.
    rewrite_brief = briefs[("reviewer", "rewrite")]
    assert "« It concerned a 450 MW extension [E1]. »: missing: not in the quote" in rewrite_brief
    assert "names Karim, Ben, Salah, which the cited sources do not name" in rewrite_brief
    assert result.review == REWRITE
    assert [s.status.value for s in result.attribution.sentences] == ["supported", "analysis"]
    [entry] = [e for e in ws.ledger.entries if e.action == "attribution"]
    assert entry.data == {"statuses": {"analysis": 1, "supported": 1}, "removed": [], "judged": True}
    assert_invariants(ws, result.verdict)


def test_without_a_judge_what_fails_in_code_is_removed_from_the_published_summary(store):
    ws = workspace(store)
    scripts = {("official", 1): collect(ws), ("reviewer", 1): review(ws, FIRST, SECOND)}
    team = InvestigationTeam(runner=scripted_team(scripts), specialists=TEAM, web_search=False, max_rounds=1)
    result = team.run(ws, plan=PLAN)
    assert result.review == SECOND  # the reviewer's text is kept in the record...
    assert result.attribution.published() == ("The award was made by direct agreement [E2]. "
                                              "It concerned a 450 MW extension [E1].")  # ...not published
    [removed] = result.attribution.failures
    assert removed.reasons == ["names Karim, Ben, Salah, which the cited sources do not name"]
    assert_invariants(ws, result.verdict)
