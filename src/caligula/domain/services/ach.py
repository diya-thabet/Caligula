"""Analysis of competing hypotheses (Heuer), computed from validated evidence.

Every piece of evidence is rated against every hypothesis: consistent,
inconsistent, or no prediction. The ratings are not asked of a model: they
follow from what each hypothesis predicts about each sub-claim and whether the
evidence supports or contradicts that sub-claim. To change a rating, dispute
the evidence or change the prediction, both of which leave a trace.

Two rules from ACH matter most:
- Evidence consistent with every hypothesis is not diagnostic. "The outage
  happened" fits a production deficit and a demand surge alike.
- The most likely hypothesis is the one with the least evidence *against*
  it, not the most evidence for it: support is easy to find for anything.
  A hypothesis with no evidence at all on what it predicts is *untested*, and
  is listed as such rather than ranked first.

Hypotheses compete when they make predictions about the same sub-claims;
each group gets its own matrix.
"""

from __future__ import annotations

from caligula.domain.model.claims import Allegation, Hypothesis
from caligula.domain.model.evidence import Relation
from caligula.domain.model.verdict import AchMatrix, AchRow, WeighedEvidence

CONSISTENT, INCONSISTENT, NO_PREDICTION = "C", "I", "N"


def competing_groups(hypotheses: list[Hypothesis]) -> list[list[Hypothesis]]:
    """Hypotheses linked by predictions about a shared sub-claim, in order of appearance."""
    groups: list[list[Hypothesis]] = []
    for h in hypotheses:
        linked = [g for g in groups if any(set(h.predicts) & set(o.predicts) for o in g)]
        merged = [x for g in linked for x in g] + [h]
        groups = [g for g in groups if g not in linked] + [merged]
    order = {h.id: i for i, h in enumerate(hypotheses)}
    return sorted((sorted(g, key=lambda h: order[h.id]) for g in groups), key=lambda g: order[g[0].id])


def rate(h: Hypothesis, subclaim_id: str, relation: Relation) -> str:
    if subclaim_id not in h.predicts:
        return NO_PREDICTION
    return CONSISTENT if (relation == Relation.SUPPORTS) == h.predicts[subclaim_id] else INCONSISTENT


def _rows(group: list[Hypothesis], items: list[WeighedEvidence]) -> list[AchRow]:
    predicted = {cid for h in group for cid in h.predicts}
    merged: dict[tuple[str, Relation, str], list[WeighedEvidence]] = {}
    for item in items:
        if item.subclaim_id in predicted and item.relation != Relation.QUALIFIES:
            merged.setdefault((item.subclaim_id, item.relation, item.cluster), []).append(item)
    rows = []
    for (cid, relation, _), same in merged.items():
        ratings = {h.id: rate(h, cid, relation) for h in group}
        predicted_by = [r for r in ratings.values() if r != NO_PREDICTION]
        rows.append(AchRow(subclaim_id=cid, relation=relation, kind=same[0].kind,
                           doc_ids=sorted({i.doc_id for i in same}), weight=max(i.weight for i in same),
                           ratings=ratings, diagnostic=len(predicted_by) > 1 and len(set(predicted_by)) > 1))
    return rows


def build_matrices(allegation: Allegation, items: list[WeighedEvidence]) -> list[AchMatrix]:
    matrices = []
    for group in competing_groups(allegation.hypotheses):
        rows = _rows(group, items)
        against = {h.id: round(sum(r.weight for r in rows if r.ratings[h.id] == INCONSISTENT), 3) for h in group}
        # Tie-break on diagnostic evidence for the hypothesis, then on order of appearance.
        support = {h.id: sum(r.weight for r in rows if r.diagnostic and r.ratings[h.id] == CONSISTENT) for h in group}
        tested = [h.id for h in group if any(r.ratings[h.id] != NO_PREDICTION for r in rows)]
        ranking = sorted(tested, key=lambda hid: (against[hid], -support[hid]))
        matrices.append(AchMatrix(hypotheses=[h.id for h in group], rows=rows, inconsistency=against,
                                  ranking=ranking, untested=[h.id for h in group if h.id not in tested]))
    return matrices
