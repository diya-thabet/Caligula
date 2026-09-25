"""Turn a claim into a case: decomposition by the analyst, completed by code.

The analyst proposes sub-claims, hypotheses and parties; code then adds every
standard innocent explanation it neither covered nor ruled out, so no case
runs without testing the lawful explanation of its facts.
"""

from __future__ import annotations

from caligula.application.ports.llm import ClaimAnalyst
from caligula.domain.model.claims import Allegation
from caligula.domain.services.innocent import ensure_innocent_explanations


def decompose_case(analyst: ClaimAnalyst, case_id: str, text: str) -> tuple[Allegation, list[str]]:
    """The completed allegation, and what code added to the analyst's version."""
    return ensure_innocent_explanations(analyst.decompose(case_id, text))
