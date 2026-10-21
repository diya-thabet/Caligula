"""Sentence-level attribution, the checks done in code: each planted fault in a
summary must be caught, and correct sentences must pass."""

from caligula.domain.model.attribution import (
    AttributionReport,
    Citable,
    JudgeRating,
    SentenceCheck,
    SentenceStatus,
)
from caligula.domain.services.attribution import (
    apply_judgment,
    check_sentence,
    citations,
    is_factual,
    numbers,
    split_sentences,
)

EVIDENCE = {
    "E1": Citable("E1", "pour un montant de 120 000 000 TND",
                  context="JORT (fictif) Marché n° 2026-017 attribué à Société Zeta Travaux", numbers=(2026, 2, 20)),
    "E2": Citable("E2", "par procédure de gré à gré", context="JORT (fictif) Marché n° 2026-017"),
    "E3": Citable("E3", "pour un montant de 60 000 000 TND", context="Wayback Machine étude de référence",
                  numbers=(60_000_000, 50.0)),
}


def check(sentence, **kw):
    return check_sentence(sentence, EVIDENCE, **kw)


def test_sentences_are_split_with_their_citations():
    summary = ("## Findings\n"
               "- The award was made by direct agreement [E2]. It was worth 120 million TND. [E1]\n"
               "Dr. Nobody wrote nothing? More work is needed.\n")
    assert split_sentences(summary) == [
        "The award was made by direct agreement [E2].", "It was worth 120 million TND. [E1]",
        "Dr. Nobody wrote nothing?", "More work is needed."]
    assert citations("worth [E1, E3] and [E2]") == ["E1", "E3", "E2"]


def test_numbers_are_read_the_way_they_are_written():
    assert [n[1] for n in numbers("120 000 000 TND, 120.000.000, 120 millions, 120M, 1,5 et 2026")] == [
        120e6, 120e6, 120e6, 120e6, 1.5, 2026]


def test_a_correct_sentence_passes_the_checks_in_code():
    c = check("The contract for market 2026-017 was worth 120 million TND [E1].")
    assert (c.status, c.reasons) == (SentenceStatus.UNJUDGED, [])
    assert check("The benchmark put comparable works at 60 000 000 TND, half the award [E3].").status == "unjudged"
    assert check("It went to Société Zeta Travaux [E1].").status == "unjudged"
    assert check("The notice for market 2026-018 says 120 million TND [E1].").reasons == [
        "the reference 2026-018 is in none of the cited sources"]


def test_a_wrong_number_is_caught():
    c = check("The contract was worth 150 million TND [E1].")
    assert c.status == SentenceStatus.UNSUPPORTED
    assert c.reasons == ["the figure 150 (150,000,000) is in none of the cited evidence"]
    # The right figure, but cited to evidence that does not carry it.
    assert check("The contract was worth 120 million TND [E2].").status == SentenceStatus.UNSUPPORTED


def test_a_name_the_evidence_does_not_name_is_caught():
    c = check("The award was signed by Karim Ben Salah [E2].")
    assert c.status == SentenceStatus.UNSUPPORTED
    assert c.reasons == ["names Karim, Ben, Salah, which the cited sources do not name"]


def test_an_uncited_fact_is_caught_but_uncited_analysis_is_kept_as_such():
    assert check("The contract was worth 120 million TND.").status == SentenceStatus.UNCITED
    assert check("Société Zeta Travaux won the contract.").status == SentenceStatus.UNCITED
    c = check("The award is suspicious [jort_award_v1].", documents={"jort_award_v1"})
    assert (c.status, c.reasons) == (SentenceStatus.UNCITED, ["cites documents, not evidence items: jort_award_v1"])
    analysis = check("More work is needed before any conclusion.")
    assert analysis.status == SentenceStatus.ANALYSIS
    assert not is_factual("C5 remains open and H4 is refuted.")  # the case's own ids are not facts


def test_withdrawn_and_unknown_evidence_ids_are_caught():
    c = check("The award was made by direct agreement [E2, E9].", withdrawn={"E9"})
    assert c.reasons == ["E9 no longer counts (disputed after review)"]
    assert check("The award was made by direct agreement [E7].").reasons == ["E7 is not an evidence id of this case"]


def test_the_judge_must_point_to_the_words_that_carry_the_claim():
    passed = check("The contract was awarded without competition [E2].")
    good = apply_judgment(passed, JudgeRating(rating="supported", support_span="gré à gré", missing=""), EVIDENCE)
    assert (good.status, good.reasons) == (SentenceStatus.SUPPORTED, [])
    vague = apply_judgment(passed, JudgeRating(rating="supported", support_span="no tender", missing=""), EVIDENCE)
    assert vague.status == SentenceStatus.PARTIAL
    partial = apply_judgment(passed, JudgeRating(rating="partial", support_span="gré à gré",
                                                 missing="that no tender was published"), EVIDENCE)
    assert (partial.status, partial.reasons) == (SentenceStatus.PARTIAL, ["missing: that no tender was published"])


def test_the_published_summary_drops_failures_and_marks_partial_support():
    report = AttributionReport(sentences=[
        SentenceCheck(text="A [E1].", status="supported", cited=["E1"], reasons=[]),
        SentenceCheck(text="B [E2].", status="partial", cited=["E2"], reasons=["missing: x"]),
        SentenceCheck(text="C [E9].", status="unsupported", cited=["E9"], reasons=["unknown"]),
        SentenceCheck(text="D 5 M.", status="uncited", cited=[], reasons=["no citation"]),
        SentenceCheck(text="More work is needed.", status="analysis", cited=[], reasons=[]),
    ])
    assert report.published() == "A [E1]. B [E2]. [partly supported] More work is needed."
    assert [s.text for s in report.failures] == ["C [E9].", "D 5 M."]
