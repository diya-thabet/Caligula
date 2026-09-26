"""Sentence-level attribution: does each factual sentence of a summary rest on
the evidence it cites?"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class Citable:
    """A counted evidence item as a summary may cite it.

    `text` is what the item itself establishes (a verified quote, or for an
    absence the register and what was searched); `context` is the wider source
    (the whole document, its publisher and title), used only to check that a
    sentence names no one its sources do not name. `numbers` are values the
    item vouches for beyond its text: the document's date, the financial
    check's results."""

    id: str
    text: str
    context: str = ""
    numbers: tuple[float, ...] = field(default=())


class SentenceStatus(StrEnum):
    SUPPORTED = "supported"  # the judge found the claim in the cited quotes
    PARTIAL = "partial"  # part of the claim is in the quotes, part is not
    UNSUPPORTED = "unsupported"  # the cited evidence does not say it, or cannot be cited
    UNCITED = "uncited"  # states a fact (names, numbers, quotes) without citing evidence
    UNJUDGED = "unjudged"  # passed the checks in code; no judge model was available
    ANALYSIS = "analysis"  # no citation and no factual marker: the writer's reasoning, shown as such


# Kept in the published summary, and how it is marked there.
KEPT = {SentenceStatus.SUPPORTED: "", SentenceStatus.UNJUDGED: "", SentenceStatus.ANALYSIS: "",
        SentenceStatus.PARTIAL: " [partly supported]"}


class JudgeRating(BaseModel):
    """A judge model's reading of one sentence against the quotes it cites."""

    rating: Literal["supported", "partial", "unsupported"]
    support_span: str  # the exact words of a quote that carry the claim; empty if none
    missing: str  # what the sentence asserts that no quote establishes; empty if nothing


class SentenceCheck(BaseModel):
    text: str
    status: SentenceStatus
    cited: list[str]
    reasons: list[str]


class AttributionReport(BaseModel):
    sentences: list[SentenceCheck]

    @property
    def failures(self) -> list[SentenceCheck]:
        return [s for s in self.sentences if s.status in (SentenceStatus.UNSUPPORTED, SentenceStatus.UNCITED)]

    def published(self) -> str:
        """The summary as it may reach an editor: failing sentences removed, partial ones marked."""
        return " ".join(s.text + KEPT[s.status] for s in self.sentences if s.status in KEPT)
