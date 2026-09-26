"""JSON views of a case for the web interface, one per surface: the case header,
the plan card, claim cards, evidence, documents with their chain of custody,
the timeline, suspicions, the audit log and the checked summary.

Everything is computed from the case and its workspace; nothing here decides
anything. Evidence is referred to by its id (E1, E2...), the same id the
summary cites, so a citation chip can open the exact quote.
"""

from __future__ import annotations

from typing import Any

from caligula.application.cases.service import Case, CaseStatus
from caligula.application.investigation.attribution import check_summary
from caligula.application.investigation.plan import TaskStatus
from caligula.application.investigation.workspace import Workspace
from caligula.domain.model.documents import Document, SourceKind
from caligula.domain.model.evidence import AbsenceFinding, EvidenceEdge, FinancialFigure, Relation
from caligula.domain.model.registers import REGISTERS
from caligula.domain.model.verdict import Verdict
from caligula.domain.services.interest import interest, role_of
from caligula.domain.services.judgment import subclaim_judgment
from caligula.domain.services.provenance import origin_clusters

# How far a source can be trusted, for the reliability badge shown wherever it is cited. The
# order follows the scoring weights: how easily the publisher can silently change the record.
RELIABILITY = {
    SourceKind.AUDIT: "independent audit",
    SourceKind.FOREIGN_MIRROR: "independent record (lender, foreign register)",
    SourceKind.ARCHIVE: "archived copy",
    SourceKind.STATISTICS: "official statistics",
    SourceKind.OSINT: "measurement (satellite, sensors)",
    SourceKind.CONTRIBUTOR: "field contributor",
    SourceKind.OFFICIAL_LIVE: "live official page (editable by its publisher)",
    SourceKind.NEWS: "press",
    SourceKind.SOCIAL: "social media (unverified)",
}

Json = dict[str, Any]


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def current_verdict(case: Case) -> Verdict | None:
    """The case's verdict, or while it runs, the assessment of the evidence counted so far."""
    if case.verdict is not None:
        return case.verdict
    return case.workspace.verdict(sensitivity=False) if case.workspace else None


def pending_approvals(case: Case) -> list[Json]:
    """What waits for a person, and who: the needs-attention queue."""
    out = []
    if case.status == CaseStatus.AWAITING_LEGAL_REVIEW:
        out.append({"kind": "legal_review", "role": "lawyer", "about": case.note})
    if case.status == CaseStatus.AWAITING_PLAN_APPROVAL:
        out.append({"kind": "plan_approval", "role": "investigator", "about": f"{len(case.plan.tasks)} tasks"})
    out += [{"kind": "scope", "role": "lawyer", "suspicion": s.id, "about": s.statement,
             "entities": s.new_entities} for s in case.awaiting_scope()]
    if case.status == CaseStatus.IN_REVIEW:
        out.append({"kind": "sign_off", "role": "editor", "about": "case file ready for review"})
    return out


def overview(case: Case) -> Json:
    v = current_verdict(case)
    ws = case.workspace
    result = case.result
    return {
        "id": case.id, "claim": case.claim, "title": case.claim[:120], "status": case.status.value,
        "note": case.note, "mode": case.mode.value, "poc": case.poc, "created_by": case.created_by,
        "created_at": _iso(case.created_at), "last_activity": _iso(case.last_activity),
        "claim_type": case.intake.claim_type.value if case.intake else (ws.allegation.claim_type if ws else None),
        "parties": [p.model_dump(mode="json") for p in (case.allegation or (ws and ws.allegation)).parties]
        if (case.allegation or ws) else [],
        "assessment": None if v is None else {
            "verdict": v.verdict, "likelihood": v.likelihood, "likelihood_term": v.likelihood_term,
            "confidence": v.confidence, "confidence_reasons": v.confidence_reasons, "final": case.verdict is not None},
        "stop_reason": result.stop_reason if result else None,
        "rounds": len(result.rounds) if result else (ws.round if ws else 0),
        "counts": None if ws is None else {
            "documents": len(ws.store.documents), "evidence": len(ws.counted()),
            "pending_proposals": sum(p.status == "pending" for p in ws.proposals),
            "open_tasks": sum(t.status == TaskStatus.OPEN for t in ws.tasks), "tool_calls": len(ws.trace),
            "open_suspicions": sum(s.status == "open" for s in ws.suspicions)},
        "pending_approvals": pending_approvals(case),
        "sign_off": None if case.sign_off is None else {
            "by": case.sign_off.by, "at": _iso(case.sign_off.at), "note": case.sign_off.note},
    }


def plan(case: Case) -> Json:
    if case.plan is None:
        return {"status": case.status.value, "plan": None}
    p = case.plan
    return {"status": case.status.value, "editable": case.status == CaseStatus.AWAITING_PLAN_APPROVAL,
            "entities": [e.model_dump() for e in p.entities], "window": [_iso(d) for d in p.window],
            "budgets": p.budgets, "fixes": p.fixes,
            "tasks": [t.model_dump(mode="json") for t in (case.workspace.tasks if case.workspace and
                                                           case.workspace.tasks else p.tasks)]}


def _sides(ws: Workspace, v: Verdict, subclaim_id: str) -> dict[str, list[str]]:
    sides: dict[str, list[str]] = {r.value: [] for r in Relation}
    for eid, item in ws.counted().items():
        if isinstance(item, FinancialFigure):
            if subclaim_id == ws.allegation.financial_subclaim and v.financial and item in v.financial.figures:
                sides[Relation.SUPPORTS.value].append(eid)
        elif item.subclaim_id == subclaim_id:
            sides[item.relation.value].append(eid)
    return sides


def claims(case: Case) -> Json:
    ws = case.workspace
    if ws is None:
        return {"subclaims": [], "hypotheses": [], "ruled_out": []}
    a, v = ws.allegation, current_verdict(case)
    unchallenged = ws.unchallenged(v)
    results = {c.id: c for c in v.by_subclaim}
    subclaims = []
    for c in a.subclaims:
        r = results[c.id]
        p, term, level, reasons = subclaim_judgment(r, v, a, ws.params, unchallenged)
        subclaims.append({
            "id": c.id, "statement": c.statement, "core": c.id in a.core_subclaims, "bearing": a.bearing_of(c.id),
            "status": r.status, "likelihood": p, "likelihood_term": term, "confidence": level.value,
            "confidence_reasons": reasons, "support": r.support, "contradiction": r.contradiction,
            "independent_origins": {"for": len(r.supporting_clusters), "against": len(r.contradicting_clusters)},
            "evidence": _sides(ws, v, c.id), "challenged": c.id not in unchallenged,
            "verification_questions": c.verification_questions,
            "expected_records": [r.model_dump(mode="json") for r in c.expected_records],
        })
    ach = {h: m for m in v.ach for h in m.hypotheses}
    kinds = {h.id: h for h in a.hypotheses}
    hypotheses = [{
        "id": h.id, "kind": kinds[h.id].kind.value, "statement": h.statement, "status": h.status,
        "reasons": h.reasons, "predicts": kinds[h.id].predicts,
        "evidence_against": ach[h.id].inconsistency.get(h.id) if h.id in ach else None,
        "untested": h.id in ach and h.id in ach[h.id].untested,
    } for h in v.hypotheses]
    return {"subclaims": subclaims, "hypotheses": hypotheses,
            "ruled_out": [r.model_dump() for r in a.ruled_out],
            "depends_on": [d.model_dump() for d in v.depends_on]}


def _source(doc: Document) -> Json:
    return {"doc_id": doc.id, "publisher": doc.publisher, "kind": doc.source_kind.value,
            "reliability": RELIABILITY[doc.source_kind], "published_at": _iso(doc.published_at),
            "observed_at": _iso(doc.observed_at), "url": doc.url}


def evidence(case: Case) -> Json:
    """Every item that counts, and every proposal with its review, by evidence and proposal id."""
    ws = case.workspace
    if ws is None:
        return {"items": []}
    v = current_verdict(case)
    weights = {(w.doc_id, w.subclaim_id, w.relation): w for w in v.weighed}
    clusters = origin_clusters(ws.store.documents)
    counted = ws.counted()
    by_item = [(p.item, p) for p in ws.proposals] + [(item, None) for item in counted.values()
                                                     if not any(p.item == item for p in ws.proposals)]
    items = []
    for item, p in by_item:
        eid = ws.evidence_id(item)
        row: Json = {"evidence_id": eid if eid in counted else None, "proposal_id": p.id if p else None,
                     "status": p.status.value if p else "accepted", "proposed_by": p.by if p else None,
                     "review_note": p.note if p else "", "counts": eid in counted}
        if isinstance(item, AbsenceFinding):
            row |= {"type": "absence", "subclaim_id": item.subclaim_id, "relation": item.relation.value,
                    "register": item.register_id, "register_name": REGISTERS[item.register_id].name,
                    "query": item.query, "searched_at": _iso(item.searched_at), "capture": item.doc_id,
                    "weight": getattr(weights.get((item.doc_id or f"absence:{item.register_id}", item.subclaim_id,
                                                   item.relation)), "weight", None)}
        else:
            doc = ws.store.get(item.doc_id)
            row |= {"source": _source(doc), "quote": item.quote, "origin": clusters[doc.id]}
            if isinstance(item, EvidenceEdge):
                w = weights.get((item.doc_id, item.subclaim_id, item.relation))
                row |= {"type": "quote", "subclaim_id": item.subclaim_id, "relation": item.relation.value,
                        "weight": w.weight if w else None,
                        "publisher_interest": interest(role_of(doc.publisher, ws.allegation.parties),
                                                       ws.allegation.bearing_of(item.subclaim_id), item.relation)}
            else:
                row |= {"type": "amount", "role": item.role.value, "amount_tnd": item.amount_tnd,
                        "used_by_financial_check": bool(v.financial and item in v.financial.figures)}
        items.append(row)
    return {"items": items}


def documents(case: Case) -> Json:
    ws = case.workspace
    if ws is None:
        return {"documents": []}
    used: dict[str, list[str]] = {}
    for eid, item in ws.counted().items():
        doc_id = item.doc_id
        if doc_id:
            used.setdefault(doc_id, []).append(eid)
    return {"documents": [_document(ws, d, used.get(d.id, [])) for d in
                          sorted(ws.store.documents.values(), key=lambda d: (d.observed_at, d.id))]}


def _document(ws: Workspace, d: Document, used_by: list[str]) -> Json:
    captures = [{"seq": e.seq, "at": e.at, "actor": e.actor, "data": e.data} for e in ws.ledger.entries
                if e.action == "capture" and e.data.get("doc_id") == d.id]
    return {**_source(d), "title": d.title, "canonical_url": d.canonical_url, "used_by": used_by,
            "custody": {"raw_sha256": d.raw_sha256, "text_sha256": d.text_sha256, "extraction": d.extraction,
                        "cites": d.cites, "derived_from": d.derived_from, "captured": captures,
                        "bytes_intact": ws.store.corpus().intact(d)}}


def document(case: Case, doc_id: str) -> Json | None:
    ws = case.workspace
    d = ws.store.get(doc_id) if ws else None
    if d is None:
        return None
    used = [eid for eid, item in ws.counted().items() if getattr(item, "doc_id", None) == doc_id]
    quotes = [{"evidence_id": eid, "quote": item.quote} for eid, item in ws.counted().items()
              if getattr(item, "doc_id", None) == doc_id and hasattr(item, "quote")]
    return {**_document(ws, d, used), "text": d.text, "highlights": quotes}


def timeline(case: Case) -> Json:
    """Dated events: documents used, events the claim dates, and rewritten records."""
    ws = case.workspace
    if ws is None:
        return {"events": []}
    v = current_verdict(case)
    events = []
    for doc_id in sorted({i.doc_id for i in ws.counted().values() if i.doc_id}):
        d = ws.store.get(doc_id)
        when = d.published_at or d.observed_at
        events.append({"date": _iso(when), "type": "document", "doc_id": doc_id, "text": d.title or d.publisher,
                       "source": _source(d), "first_seen": _iso(d.observed_at),
                       "seen_late": abs((d.observed_at - when).days) > 1})
    for c in ws.allegation.subclaims:
        if c.event_date:
            events.append({"date": _iso(c.event_date), "type": "claimed_event", "subclaim_id": c.id,
                           "text": c.statement})
    for f in v.retcon_flags:
        events.append({"date": _iso(f.later_observed_at), "type": "rewrite", "doc_id": f.later_doc_id,
                       "earlier_doc_id": f.earlier_doc_id,
                       "text": "; ".join(f"{c.kind} {c.removed} → {c.added}" for c in f.changes),
                       "needs_review": f.needs_review})
    return {"events": sorted(events, key=lambda e: (e["date"], e["type"], e["text"]))}


def suspicions(case: Case) -> Json:
    ws = case.workspace
    rows = [] if ws is None else [{
        "id": s.id, "statement": s.statement, "status": s.status.value, "raised_by": s.raised_by, "round": s.round,
        "tested_by": s.subclaim_id, "confirm_by": s.confirm_by, "refute_by": s.refute_by, "tasks": s.task_ids,
        "new_entities": s.new_entities, "note": s.note, "resolved_round": s.resolved_round,
    } for s in ws.suspicions]
    return {"suspicions": rows}


def audit(case: Case, action: str | None = None, actor: str | None = None) -> Json:
    entries = [e for e in case.ledger.entries if (action is None or e.action == action)
               and (actor is None or e.actor == actor)]
    broken = case.ledger.verify()
    return {"integrity": {"entries": len(case.ledger.entries), "head": case.ledger.head,
                          "intact": broken is None, "broken_at": broken},
            "entries": [{"seq": e.seq, "at": e.at, "action": e.action, "actor": e.actor, "data": e.data,
                         "hash": e.hash} for e in entries]}


def summary(case: Case) -> Json:
    """The reviewer's summary as written, as published after the citation check, and each sentence."""
    ws = case.workspace
    report = ws.attribution if ws else None
    if report is None and ws is not None and case.review:
        report = check_summary(ws, case.review)
    if report is None:
        return {"written": case.review, "published": None, "sentences": []}
    return {"written": case.review, "published": report.published(),
            "sentences": [s.model_dump(mode="json") for s in report.sentences]}
