"""Code-side verification of everything the LLM proposed.

An evidence edge is kept only if its document exists, the stored bytes still
match the recorded hash, the sub-claim exists, and the quote appears in the
document text. A financial figure additionally needs its amount to be
extractable from that quote. Rejections are reported, never silently dropped.
"""

from __future__ import annotations

import math

from caligula.extract import extract_amounts
from caligula.hashing import normalize_text
from caligula.models import Allegation, EvidenceEdge, FinancialFigure, RejectedEvidence
from caligula.store import EvidenceStore


def _check_quote(store: EvidenceStore, doc_id: str, quote: str) -> str | None:
    doc = store.get(doc_id)
    if doc is None:
        return f"document {doc_id} not in store"
    if not store.blobs.verify(doc.raw_sha256):
        return f"stored bytes for {doc_id} no longer match {doc.raw_sha256[:12]}"
    if not quote.strip() or normalize_text(quote) not in normalize_text(doc.text):
        return f"quote not found verbatim in {doc_id}"
    return None


def validate_edges(
    store: EvidenceStore, allegation: Allegation, edges: list[EvidenceEdge]
) -> tuple[list[EvidenceEdge], list[RejectedEvidence]]:
    subclaim_ids = {c.id for c in allegation.subclaims}
    kept, rejected = [], []
    for edge in edges:
        label = f"edge {edge.doc_id} {edge.relation} {edge.subclaim_id}"
        reason = (
            f"unknown sub-claim {edge.subclaim_id}"
            if edge.subclaim_id not in subclaim_ids
            else _check_quote(store, edge.doc_id, edge.quote)
        )
        if reason:
            rejected.append(RejectedEvidence(item=label, reason=reason))
        else:
            kept.append(edge)
    return kept, rejected


def validate_figures(
    store: EvidenceStore, figures: list[FinancialFigure]
) -> tuple[list[FinancialFigure], list[RejectedEvidence]]:
    kept, rejected = [], []
    for fig in figures:
        label = f"figure {fig.doc_id} {fig.role}={fig.amount_tnd:,.0f} TND"
        reason = _check_quote(store, fig.doc_id, fig.quote)
        if reason is None and not any(
            math.isclose(a, fig.amount_tnd, rel_tol=1e-6) for a in extract_amounts(fig.quote)
        ):
            reason = "amount not present in quoted text"
        if reason:
            rejected.append(RejectedEvidence(item=label, reason=reason))
        else:
            kept.append(fig)
    return kept, rejected
