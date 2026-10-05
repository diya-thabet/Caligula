"""A reviewer's summary checked sentence by sentence against the case's evidence,
with a scripted judge standing in for the model."""

from caligula.adapters.fixtures.case_directory import case_workspace
from caligula.application.investigation.attribution import check_summary, citables
from caligula.domain.model.attribution import JudgeRating
from conftest import FIXTURE


class Judge:
    """Rates by rule: supported with a span when the span is given for the sentence, else unsupported."""

    def __init__(self, spans, fail=False):
        self.spans, self.fail, self.calls = spans, fail, []

    def judge(self, sentence, evidence):
        self.calls.append((sentence, evidence))
        if self.fail:
            raise RuntimeError("rate limited")
        span = next((s for key, s in self.spans.items() if key in sentence), "")
        return JudgeRating(rating="supported" if span else "unsupported", support_span=span,
                           missing="" if span else "the claim")


SUMMARY = """The award of market 2026-017 was made by direct agreement [E13].
It was worth 120 million TND [E19], twice the benchmark of 60 million TND [E22].
The contract went to Karim Ben Salah's company [E13].
The emergency decree was never published in the JORT [E23].
Nothing was built on the site [E12].
Further collection is needed on the price shock explanation."""


def test_each_sentence_is_checked_in_code_then_by_the_judge(store):
    ws = case_workspace(FIXTURE, store)
    judge = Judge({"direct agreement": "par procédure de gré à gré",
                   "120 million": "pour un montant de 120 000 000 TND",
                   "decree": "nothing found",
                   "built": "a vague paraphrase"})
    report = check_summary(ws, SUMMARY, judge)
    statuses = [(s.status.value, s.reasons) for s in report.sentences]
    assert statuses == [
        ("supported", []),
        ("supported", []),
        ("unsupported", ["names Karim, Ben, Salah's, which the cited sources do not name"]),
        ("supported", []),
        ("partial", ["the judge could not point to words of a cited quote that carry the claim"]),
        ("analysis", []),
    ]
    # Only sentences that passed the checks in code reach the judge, with the quotes they cite.
    assert len(judge.calls) == 4
    assert judge.calls[0] == ("The award of market 2026-017 was made by direct agreement [E13].",
                              [("E13", "par procédure de gré à gré")])
    published = report.published()
    assert "Karim" not in published and "Nothing was built on the site [E12]. [partly supported]" in published


def test_the_financial_check_vouches_for_its_own_results(store):
    ws = case_workspace(FIXTURE, store)
    ids = citables(ws)
    assert 60_000_000 in ids["E19"].numbers and 50.0 in ids["E19"].numbers  # the gap, and the gap in percent
    report = check_summary(ws, "The gap is 60 million TND, 50% of the award [E19, E22].")
    assert report.sentences[0].status == "unjudged"


def test_without_a_judge_or_when_it_fails_sentences_stay_unjudged_and_say_why(store):
    ws = case_workspace(FIXTURE, store)
    [s] = check_summary(ws, "The award was made by direct agreement [E13].").sentences
    assert (s.status, s.reasons) == ("unjudged", [])
    [s] = check_summary(ws, "The award was made by direct agreement [E13].", Judge({}, fail=True)).sentences
    assert (s.status, s.reasons) == ("unjudged", ["judge unavailable: RuntimeError: rate limited"])


def test_withdrawn_evidence_cannot_be_cited(store):
    ws = case_workspace(FIXTURE, store)
    ws.edges.remove(ws.evidence_ids["E13"])  # as if the reviewer had disputed it
    [s] = check_summary(ws, "The award was made by direct agreement [E13].").sentences
    assert (s.status, s.reasons) == ("unsupported", ["E13 no longer counts (disputed after review)"])
