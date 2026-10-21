"""Interest of the source: who gains if a piece of evidence is believed.

Courts and analysts apply the same rule. A statement *against* the speaker's
own interest (an institution conceding an irregularity) is strong evidence:
nobody makes it lightly. A *self-serving* statement (the accused justifying
itself, a rival denouncing a competitor) is weak until something independent
confirms it.

A document's author is its publisher. Its interest in one piece of evidence
follows from three facts: the publisher's role in the case (accused,
complainant, or neither), whether the sub-claim incriminates or exculpates the
accused (`Bearing`), and whether the document supports or contradicts it.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum

from caligula.domain.model.claims import Bearing, Party, PartyRole
from caligula.domain.model.evidence import Relation
from caligula.domain.services.text import normalize_text


class Interest(StrEnum):
    AGAINST_INTEREST = "against_interest"  # the source concedes a point that hurts it
    SELF_SERVING = "self_serving"  # the source asserts a point that helps it
    NONE = "none"  # neutral source, or a point that does not touch its interest


_PUNCT = re.compile(r"[^\w]+")


def _words(text: str) -> str:
    text = unicodedata.normalize("NFKD", normalize_text(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return f" {_PUNCT.sub(' ', text).strip()} "


def role_of(publisher: str, parties: list[Party]) -> PartyRole | None:
    """The role of the party that published a document, matched on whole words
    of its name or aliases ("STEG" matches "STEG - Direction de la communication")."""
    haystack = _words(publisher)
    for party in parties:
        if any(_words(name) in haystack for name in [party.name, *party.aliases] if name.strip()):
            return party.role
    return None


def helps_accused(bearing: Bearing, relation: Relation) -> bool | None:
    """True if believing this evidence helps the accused, False if it hurts,
    None if the sub-claim does not bear on the accused either way."""
    if relation == Relation.QUALIFIES:  # a condition or innocent explanation
        return True if bearing == Bearing.AGAINST else None
    if bearing == Bearing.NEUTRAL:
        return None
    confirms = relation == Relation.SUPPORTS
    return confirms == (bearing == Bearing.FOR)


def interest(role: PartyRole | None, bearing: Bearing, relation: Relation) -> Interest:
    helps = helps_accused(bearing, relation)
    if role is None or helps is None:
        return Interest.NONE
    serves_itself = helps if role == PartyRole.ACCUSED else not helps
    return Interest.SELF_SERVING if serves_itself else Interest.AGAINST_INTEREST
