"""Absence as evidence: checking and weighing searches that found nothing.

"We looked and it is not there" counts only if the search can be checked:
a known register, a stated query, a window the search could actually cover,
and ideally a stored capture of the empty result. Its weight is the
register's completeness (`domain.model.registers`), reduced when there is
no capture. Several searches of one register for one sub-claim are one
origin, like several articles repeating one source.
"""

from __future__ import annotations

from caligula.domain.model.claims import Allegation
from caligula.domain.model.documents import Corpus
from caligula.domain.model.evidence import AbsenceFinding, RejectedEvidence, Relation
from caligula.domain.model.registers import REGISTERS
from caligula.domain.model.verdict import WeighedEvidence
from caligula.domain.services.scoring import DEFAULT_PARAMS, Params
from caligula.domain.services.validation import CLOCK_SLACK


def _problem(corpus: Corpus, claims: set[str], f: AbsenceFinding) -> str | None:
    if f.subclaim_id not in claims:
        return f"unknown sub-claim {f.subclaim_id}"
    if f.register_id not in REGISTERS:
        return f"unknown register {f.register_id}"
    if f.relation == Relation.QUALIFIES:
        return "an absence supports or contradicts a sub-claim; it cannot qualify it"
    if not f.query.strip():
        return "no query: say what was searched"
    if f.window_start and f.window_end and f.window_start > f.window_end:
        return "search window ends before it starts"
    if f.doc_id is None:
        if f.window_end and f.searched_at + CLOCK_SLACK < f.window_end:
            return "search made before the end of the window it claims to cover"
        return None
    doc = corpus.get(f.doc_id)
    if doc is None:
        return f"document {f.doc_id} not in store"
    if not corpus.intact(doc):
        return f"stored bytes for {f.doc_id} no longer match {doc.raw_sha256[:12]}"
    if f.window_end and doc.observed_at + CLOCK_SLACK < f.window_end:
        return f"capture {f.doc_id} predates the end of the window it claims to cover"
    return None


def validate_absences(
    corpus: Corpus, allegation: Allegation, findings: list[AbsenceFinding]
) -> tuple[list[AbsenceFinding], list[RejectedEvidence]]:
    claims = {c.id for c in allegation.subclaims}
    kept, rejected = [], []
    for f in findings:
        reason = _problem(corpus, claims, f)
        if reason:
            rejected.append(RejectedEvidence(item=f"absence {f.subclaim_id} in {f.register_id}", reason=reason))
        else:
            kept.append(f)
    return kept, rejected


def weigh_absences(
    findings: list[AbsenceFinding], clusters: dict[str, str], params: Params = DEFAULT_PARAMS
) -> list[WeighedEvidence]:
    out = []
    for f in findings:
        weight = params.completeness.get(f.register_id, 0.0)
        if f.doc_id is None:
            weight *= params.absence_uncaptured_factor
        label = f.doc_id or f"absence:{f.register_id}"
        out.append(WeighedEvidence(doc_id=label, subclaim_id=f.subclaim_id, relation=f.relation, kind="absence",
                                   cluster=clusters[f.doc_id] if f.doc_id else label, weight=round(weight, 4)))
    return out
