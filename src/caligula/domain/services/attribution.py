"""Sentence-level attribution check, the part done in code.

Research on model citations (ALCE) finds that about half of the citations the
best models give do not fully support their sentence. A summary about a
public body is only as safe as its weakest sentence, so each one is checked
before anything reaches an editor:

1. Split the summary into sentences and read the evidence ids each cites
   ([E3], [E3, E7]). Document ids are not enough: a document says many
   things, an evidence item is one verified quote or search.
2. A sentence with a factual marker (a number, a quotation, a proper name)
   must cite evidence. One without markers or citations is the writer's
   analysis: kept, but shown as such.
3. Cited ids must exist and still count.
4. Every number in the sentence must appear in a cited quote or be a value
   the cited item vouches for (its date, the financial check). Small counts
   (up to 12) are left to the judge: "two sources" is not a figure to verify.
   References (market and decree numbers, numeric dates) may come from
   anywhere in the cited documents.
5. Every proper name must appear in the cited sources: a sentence may not
   name anyone its evidence does not.

What passes goes to a judge model (see `apply_judgment`), whose "supported"
counts only if it can point to the words that carry the claim.
"""

from __future__ import annotations

import re
import unicodedata

from caligula.domain.model.attribution import (
    Citable,
    JudgeRating,
    SentenceCheck,
    SentenceStatus,
)
from caligula.domain.services.extraction import _NUM, _parse_number
from caligula.domain.services.text import normalize_text

_CITATION = re.compile(r"\[([^\[\]]+)\]")
_EVIDENCE_ID = re.compile(r"^E\d+$")
# Ids of the case's own objects: sub-claims, hypotheses, suspicions, tasks, proposals, evidence.
_CASE_ID = re.compile(r"\b(?:[CHSTPE]\d+(?:\.E\d+)?)\b")
_SCALE = {"k": 1e3, "mille": 1e3, "m": 1e6, "million": 1e6, "millions": 1e6, "md": 1e6, "mdt": 1e6,
          "milliard": 1e9, "milliards": 1e9, "bn": 1e9, "billion": 1e9, "billions": 1e9}
_NUMBER = re.compile(rf"(?<![\w.,])(?P<num>{_NUM})\s*(?P<scale>{'|'.join(sorted(_SCALE, key=len, reverse=True))})?"
                     r"(?![\w])")
_SMALL = 12
# Capitalised words that are not names: calendar words (dates are checked as numbers).
_CALENDAR = {
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "janvier", "février", "fevrier", "mars", "avril", "mai", "juin", "juillet", "août", "aout", "septembre",
    "octobre", "novembre", "décembre", "decembre",
}
_NAME = re.compile(r"\b[A-ZÀ-ÖØ-Þ][\w'’-]*")
_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[\"«(]?[A-ZÀ-ÖØ-Þ0-9])")
_ABBREVIATION = re.compile(r"(?:^|\s)(?:dr|mr|mrs|ms|m|mme|mlle|st|no|n°|art|cf|vs|etc|e\.g|i\.e|p|pp)\.$", re.I)
# References: market, decree and file numbers, and numeric dates (2026-017, 21/07/2026).
_REFERENCE = re.compile(r"(?<![\w.,])\d+(?:[-/]\d+)+(?![\w])")
_ONLY_CITATIONS = re.compile(r"^(?:\s*\[[^\[\]]+\]\s*)+[.;,]?$")


def fold(text: str) -> str:
    """Lower case, normalised spaces and digits, no accents."""
    return "".join(c for c in unicodedata.normalize("NFKD", normalize_text(text)) if not unicodedata.combining(c))


def split_sentences(summary: str) -> list[str]:
    """Sentences of a summary, one per bullet or line at least; headings are dropped.
    A citation left after a full stop ("... 2026. [E3]") stays with its sentence."""
    out: list[str] = []
    for line in summary.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line).strip()
        if not line or line.startswith("#"):
            continue
        parts: list[str] = []
        for part in _BOUNDARY.split(line):
            if parts and _ABBREVIATION.search(parts[-1]):
                parts[-1] = f"{parts[-1]} {part}"
            else:
                parts.append(part)
        for part in parts:
            part = part.strip()
            if out and _ONLY_CITATIONS.match(part):
                out[-1] = f"{out[-1]} {part}"
            elif part:
                out.append(part)
    return out


def citations(sentence: str) -> list[str]:
    return [ref.strip() for group in _CITATION.findall(sentence) for ref in group.split(",") if ref.strip()]


def _bare(sentence: str) -> str:
    """The sentence without its citations and the case's own ids."""
    return _CASE_ID.sub(" ", _CITATION.sub(" ", sentence))


def numbers(text: str) -> list[tuple[float, float, bool]]:
    """(value as written, value scaled, has a scale or percent) for each number in `text`."""
    out = []
    for m in _NUMBER.finditer(normalize_text(text)):
        raw = _parse_number(m.group("num"))
        scale = m.group("scale")
        out.append((raw, raw * _SCALE.get(scale or "", 1), bool(scale)))
    return out


def names(sentence: str) -> list[str]:
    """Capitalised words other than the first word, calendar words and the case's ids."""
    words = _NAME.findall(_bare(sentence))
    first = _NAME.match(_bare(sentence).lstrip("«\"( "))
    if first and words and words[0] == first.group(0):
        words = words[1:]
    return [w for w in words if len(w) > 1 and w.lower() not in _CALENDAR]


def is_factual(sentence: str) -> bool:
    bare = _bare(sentence)
    return bool(numbers(bare) or re.search(r"[«»\"“”]", bare) or names(sentence))


def _matches(value: float, known: set[float]) -> bool:
    return any(abs(value - k) <= 0.005 * max(abs(k), 1) for k in known)


def check_sentence(sentence: str, evidence: dict[str, Citable], withdrawn: set[str] = frozenset(),
                   documents: set[str] = frozenset()) -> SentenceCheck:
    """The checks done in code. `evidence`: counted items by id; `withdrawn`: ids that no longer
    count; `documents`: stored document ids (cited alone, they are not evidence)."""
    refs = citations(sentence)
    ids = [r for r in refs if _EVIDENCE_ID.match(r)]
    reasons: list[str] = []
    if not ids:
        if not refs and not is_factual(sentence):
            return SentenceCheck(text=sentence, status=SentenceStatus.ANALYSIS, cited=[], reasons=[])
        docs = [r for r in refs if r in documents]
        reasons.append(f"cites documents, not evidence items: {', '.join(docs)}" if docs
                       else "states a fact (a number, a quotation or a name) without citing evidence")
        return SentenceCheck(text=sentence, status=SentenceStatus.UNCITED, cited=[], reasons=reasons)
    reasons += [f"{i} no longer counts (disputed after review)" for i in ids if i in withdrawn]
    reasons += [f"{i} is not an evidence id of this case" for i in ids if i not in evidence and i not in withdrawn]
    cited = [evidence[i] for i in ids if i in evidence]
    text = " ".join(c.text for c in cited)
    known_raw = {raw for raw, _, _ in numbers(text)}
    known = {scaled for _, scaled, _ in numbers(text)} | {n for c in cited for n in c.numbers} | known_raw
    sources = fold(" ".join(f"{c.text} {c.context}" for c in cited))
    bare = _bare(sentence)
    for ref in _REFERENCE.findall(bare):
        if ref not in sources:
            reasons.append(f"the reference {ref} is in none of the cited sources")
    for raw, scaled, scaled_up in numbers(_REFERENCE.sub(" ", bare)):
        if not scaled_up and raw.is_integer() and raw <= _SMALL:
            continue
        if not (_matches(scaled, known) or _matches(raw, known_raw)):
            reasons.append(f"the figure {raw:g}{'' if scaled == raw else f' ({scaled:,.0f})'} is in none of the "
                           "cited evidence")
    missing = [n for n in names(sentence) if fold(n) not in sources]
    if missing:
        reasons.append(f"names {', '.join(missing)}, which the cited sources do not name")
    status = SentenceStatus.UNSUPPORTED if reasons else SentenceStatus.UNJUDGED
    return SentenceCheck(text=sentence, status=status, cited=ids, reasons=reasons)


def apply_judgment(check: SentenceCheck, rating: JudgeRating, evidence: dict[str, Citable]) -> SentenceCheck:
    """A judge's rating of a sentence that passed the checks in code. "Supported" stands only
    if the judge quotes the words that carry the claim, verbatim from a cited item."""
    quotes = fold(" ".join(evidence[i].text for i in check.cited if i in evidence))
    reasons = [f"missing: {rating.missing}"] if rating.missing.strip() else []
    status = SentenceStatus(rating.rating)
    if status == SentenceStatus.SUPPORTED and (not rating.support_span.strip()
                                               or fold(rating.support_span) not in quotes):
        status = SentenceStatus.PARTIAL
        reasons.append("the judge could not point to words of a cited quote that carry the claim")
    if status != SentenceStatus.SUPPORTED and not reasons:
        reasons.append(f"judge: {status.value}")
    return check.model_copy(update={"status": status, "reasons": reasons})
