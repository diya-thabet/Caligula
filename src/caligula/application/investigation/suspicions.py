"""Suspicions the reviewer raises while the case is investigated.

A suspicion is a statement to test ("the 3M -> 1.8M change hides an
overpayment"). It is tied to a sub-claim, existing or created for it, so its
status is never the reviewer's opinion: it follows the sub-claim's status as
code scores it (supported: confirmed; contradicted: refuted; otherwise open).
Every suspicion comes with two tasks, one that would confirm it and one that
would refute it, so the loop cannot only look for what the reviewer already
believes.

A suspicion that brings in people or companies outside the original claim
widens the scope of the case, so it goes through the same legal policy as a
new request before any agent works on it.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

from caligula.domain.model.claims import Allegation
from caligula.domain.services.names import EntityKind, match
from caligula.domain.services.text import normalize_text


class SuspicionStatus(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    AWAITING_SCOPE = "awaiting_scope"  # new people or companies: a lawyer must approve the wider scope
    REJECTED = "rejected"  # refused by the legal policy (e.g. no documented act, sensitive traits)


@dataclass
class Suspicion:
    id: str
    statement: str
    subclaim_id: str | None
    raised_by: str
    round: int
    confirm_by: str
    refute_by: str
    new_entities: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    status: SuspicionStatus = SuspicionStatus.OPEN
    resolved_round: int | None = None
    note: str = ""


_FROM_STATUS = {"supported": SuspicionStatus.CONFIRMED, "contradicted": SuspicionStatus.REFUTED}


def resolve(suspicions: list[Suspicion], statuses: dict[str, str], round_: int) -> list[Suspicion]:
    """Update open suspicions from sub-claim statuses; returns the ones that changed."""
    changed = []
    for s in suspicions:
        if s.status not in (SuspicionStatus.OPEN, SuspicionStatus.CONFIRMED, SuspicionStatus.REFUTED):
            continue
        new = _FROM_STATUS.get(statuses.get(s.subclaim_id or ""), SuspicionStatus.OPEN)
        if new != s.status:
            s.status = new
            s.resolved_round = round_ if new != SuspicionStatus.OPEN else None
            changed.append(s)
    return changed


def _fold(text: str) -> str:
    """Lower case, normalized spaces and digits, no accents: "Société" and "Societe" compare equal."""
    return "".join(c for c in unicodedata.normalize("NFKD", normalize_text(text)) if not unicodedata.combining(c))


def unknown_entities(names: list[str], allegation: Allegation, known: list[str]) -> list[str]:
    """Names that are neither in the claim text nor close to a known entity or party."""
    text = _fold(allegation.text)
    known = known + [n for p in allegation.parties for n in [p.name, *p.aliases]]
    return [n for n in names if n.strip() and _fold(n) not in text
            and not any(match(n, k, EntityKind.COMPANY).same or match(n, k, EntityKind.PERSON).same
                        for k in known)]
