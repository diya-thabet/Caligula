"""Evaluate a case from evidence readings: recorded ones, or fresh ones from an analyst.

Both paths go through the same validation and scoring.
"""

from __future__ import annotations

from caligula.application.evidence_store import EvidenceStore
from caligula.application.ports.llm import ClaimAnalyst
from caligula.application.usecases.decompose import decompose_case
from caligula.domain.model.claims import Allegation
from caligula.domain.model.evidence import EvidenceEdge, FinancialFigure
from caligula.domain.model.verdict import Verdict
from caligula.domain.services.scoring import DEFAULT_PARAMS, Params
from caligula.domain.services.verdict import build_verdict


def evaluate_readings(
    store: EvidenceStore,
    allegation: Allegation,
    edges: list[EvidenceEdge],
    figures: list[FinancialFigure],
    params: Params = DEFAULT_PARAMS,
) -> Verdict:
    return build_verdict(store.corpus(), allegation, edges, figures, params)


def evaluate_with_analyst(
    store: EvidenceStore,
    analyst: ClaimAnalyst,
    allegation_id: str,
    text: str,
    params: Params = DEFAULT_PARAMS,
) -> Verdict:
    """Decompose the claim and have the analyst read every stored document."""
    allegation, _ = decompose_case(analyst, allegation_id, text)
    edges: list[EvidenceEdge] = []
    figures: list[FinancialFigure] = []
    for doc in store.documents.values():
        doc_edges, doc_figures = analyst.read(allegation, doc)
        edges += doc_edges
        figures += doc_figures
    return evaluate_readings(store, allegation, edges, figures, params)
