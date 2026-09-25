"""Name matching across Arabic script, French transliterations and word order.

"Mohamed Ben Salah", "SALAH Mohamed Ben", "M'hamed Bensalah" and "محمد بن صالح"
should all land near each other. Names are reduced to a consonant skeleton
(Arabic has no written short vowels, and French spellings disagree on them),
compared token by token, independent of order.

A match between *people* is a lead for a reviewer, never an automatic merge:
`match()` reports a score and whether a human must confirm it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum

_AR_TO_LATIN = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ء": "", "ؤ": "ou", "ئ": "i", "ب": "b", "ت": "t",
    "ة": "a", "ث": "th", "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z",
    "س": "s", "ش": "ch", "ص": "s", "ض": "d", "ط": "t", "ظ": "dh", "ع": "", "غ": "gh", "ف": "f",
    "ق": "k", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "ou", "ي": "i", "ى": "a",
}
_DIGRAPHS = [("sch", "x"), ("ch", "x"), ("sh", "x"), ("kh", "k"), ("gh", "g"), ("th", "t"),
             ("dh", "d"), ("ou", "w"), ("q", "k"), ("c", "k"), ("dj", "j")]
_LEGAL_FORMS = {
    "societe", "ste", "sa", "sarl", "suarl", "sas", "cie", "compagnie", "groupe", "group", "ets",
    "etablissements", "entreprise", "company", "co", "ltd", "sharika", "shrk", "mouassasa",
}
_STOPWORDS = {"de", "du", "des", "la", "le", "les", "et", "d", "l", "al", "el"}
_AR_LEGAL = {"شركة", "مؤسسة", "مجمع"}


class EntityKind(StrEnum):
    PERSON = "person"
    COMPANY = "company"


def _latin(text: str) -> str:
    text = "".join(_AR_TO_LATIN.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def _skeleton(token: str) -> str:
    token = re.sub(r"(?<=[aeiou])x$", "", token)  # silent French plural: travaux
    for a, b in _DIGRAPHS:
        token = token.replace(a, b)
    token = token.replace("v", "f").replace("p", "b")  # sounds Arabic script lacks
    token = token[:1] + token[1:].replace("w", "")  # medial و is usually a long vowel
    token = re.sub(r"[aeiouy'’]", "", token)
    return re.sub(r"(.)\1+", r"\1", token)


def name_key(name: str) -> list[str]:
    """Order-free consonant skeletons of the meaningful tokens of a name."""
    words = [w for w in re.split(r"[\s\-_.,/()]+", name) if w and w not in _AR_LEGAL]
    tokens = []
    for w in words:
        # Arabic definite article and Latin "al-/el-" prefixes carry no identity.
        w = re.sub(r"^ال", "", w)
        latin = re.sub(r"[^a-z']", "", _latin(w))
        latin = re.sub(r"^(al|el)(?=[a-z]{3})", "", latin)
        if not latin or latin in _LEGAL_FORMS or latin in _STOPWORDS:
            continue
        # "Bensalah" -> "ben" + "salah" so it matches "Ben Salah".
        m = re.fullmatch(r"(ben|bin|ibn|bou|abou|abu)([a-z]{3,})", latin)
        parts = [m[1], m[2]] if m else [latin]
        tokens += [s for s in (_skeleton(p) for p in parts) if s]
    return sorted(tokens)


def _token_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def similarity(a: str, b: str) -> float:
    """Soft token-set overlap in [0, 1], symmetric and order-independent."""
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return 0.0
    if len(ka) > len(kb):
        ka, kb = kb, ka
    used: set[int] = set()
    total = 0.0
    for t in ka:
        best, best_j = 0.0, None
        for j, u in enumerate(kb):
            if j not in used and (s := _token_sim(t, u)) > best:
                best, best_j = s, j
        if best_j is not None:
            used.add(best_j)
        total += best
    # Penalize unmatched extra tokens in the longer name, but only half:
    # official documents often add a father's name ("ben X").
    return total / (len(ka) + 0.5 * (len(kb) - len(ka)))


AUTO_MERGE = 0.92  # companies only
REVIEW = 0.75


@dataclass(frozen=True)
class Match:
    score: float
    same: bool
    needs_review: bool


def match(a: str, b: str, kind: EntityKind) -> Match:
    s = round(similarity(a, b), 3)
    if kind == EntityKind.COMPANY and s >= AUTO_MERGE:
        return Match(s, True, False)
    return Match(s, False, s >= REVIEW)


@dataclass
class Entity:
    id: str
    kind: EntityKind
    names: list[str] = field(default_factory=list)


class EntityResolver:
    """Groups company names; proposes (never merges) person matches."""

    def __init__(self):
        self.entities: list[Entity] = []

    def add(self, name: str, kind: EntityKind) -> tuple[Entity, list[tuple[Entity, Match]]]:
        """Returns the entity the name was attached to and person matches to review."""
        candidates = [
            (e, max((match(name, n, kind) for n in e.names), key=lambda m: m.score))
            for e in self.entities
            if e.kind == kind
        ]
        merged = [c for c in candidates if c[1].same]
        if merged:
            entity = max(merged, key=lambda c: c[1].score)[0]
            entity.names.append(name)
            return entity, []
        entity = Entity(id=f"{kind.value[0]}{len(self.entities) + 1}", kind=kind, names=[name])
        self.entities.append(entity)
        return entity, sorted((c for c in candidates if c[1].needs_review), key=lambda c: -c[1].score)
