"""Tools the investigator agent can call.

Tool docstrings are the model's instructions for each tool, so they say when
to use it and what comes back. Every tool counts against the budget except
`assess` and `finish`, which the agent always needs to wrap up.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Literal

from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from caligula.agent.workspace import Purpose, Workspace
from caligula.entities import EntityKind, match
from caligula.hashing import sha256_bytes
from caligula.ingest.text import extract_text
from caligula.ingest.wayback import Capture
from caligula.models import AmountRole, EvidenceEdge, FinancialFigure, Relation, SourceKind
from caligula.retcon import diff_fields

MAX_READ = 8000
KindName = Literal[
    "official_live", "archive", "foreign_mirror", "audit", "statistics", "contributor", "osint", "news", "social"
]


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    d = datetime.fromisoformat(value)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def build_tools(ws: Workspace) -> list:
    def metered(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(**kwargs):
            if ws.finished:
                raise ToolError("The investigation is finished; no further tool calls.")
            if ws.budget <= 0:
                raise ToolError("Tool budget exhausted. Call assess, then finish with what you have.")
            ws.budget -= 1
            try:
                out = fn(**kwargs)
            except ToolError as exc:
                ws.log(fn.__name__, kwargs, f"error: {exc}")
                raise
            except Exception as exc:  # connector failures are information, not crashes
                ws.log(fn.__name__, kwargs, f"error: {exc}")
                raise ToolError(f"{type(exc).__name__}: {exc}") from exc
            ws.log(fn.__name__, kwargs, out[:300])
            return out

        return wrapper

    def store_document(raw: bytes, *, kind: SourceKind, url: str, canonical_url: str, publisher: str,
                       observed_at: datetime, filename: str = "") -> str:
        doc_id = f"{kind.value}-{sha256_bytes(raw)[:12]}"
        if ws.store.get(doc_id) is None:
            extracted = extract_text(raw, filename or url)
            ws.store.add(doc_id=doc_id, raw=raw, text=extracted.text, extraction=extracted.method,
                         canonical_url=canonical_url, url=url, source_kind=kind, publisher=publisher,
                         observed_at=observed_at)
        return doc_id

    @beta_tool
    @metered
    def search_evidence(
        query: str,
        purpose: Literal["support", "challenge", "explore"],
        subclaim_id: str | None = None,
        source_kinds: list[KindName] | None = None,
        observed_after: str | None = None,
        observed_before: str | None = None,
        k: int = 8,
    ) -> str:
        """Search stored documents (hybrid keyword + semantic). Use exact identifiers
        (market numbers, decree numbers, company names) as well as paraphrases.

        Args:
            query: Search text, French or Arabic.
            purpose: "support" to find evidence for a sub-claim, "challenge" to look for
                evidence that would refute it or give an innocent explanation, "explore" otherwise.
            subclaim_id: The sub-claim this search is about, if any.
            source_kinds: Restrict to these source kinds.
            observed_after: ISO date; only documents we or an archive observed on/after it.
            observed_before: ISO date; only documents observed on/before it.
            k: Number of results.
        """
        ws.searches.append((Purpose(purpose), subclaim_id, query))
        hits = ws.store.search(
            query, k=k, kinds=[SourceKind(s) for s in source_kinds] if source_kinds else None,
            observed_after=_date(observed_after), observed_before=_date(observed_before),
        )
        rows = []
        for h in hits:
            d = ws.store.get(h.doc_id)
            rows.append({"doc_id": d.id, "kind": d.source_kind, "publisher": d.publisher,
                         "observed_at": d.observed_at.date().isoformat(), "url": d.canonical_url, "snippet": h.snippet})
        return json.dumps(rows, ensure_ascii=False) if rows else "No matching documents in the store."

    @beta_tool
    @metered
    def read_document(doc_id: str, offset: int = 0) -> str:
        """Read a stored document's text and metadata. Long documents are returned in
        windows; call again with the returned next_offset to continue.

        Args:
            doc_id: Document id from a search or ingest result.
            offset: Character offset to start from.
        """
        d = ws.store.get(doc_id)
        if d is None:
            raise ToolError(f"No document {doc_id}.")
        chunk = d.text[offset : offset + MAX_READ]
        end = offset + len(chunk)
        meta = {"doc_id": d.id, "kind": d.source_kind, "publisher": d.publisher, "url": d.url,
                "canonical_url": d.canonical_url, "extraction": d.extraction,
                "published_at": d.published_at.isoformat() if d.published_at else None,
                "observed_at": d.observed_at.isoformat(), "cites": d.cites,
                "next_offset": end if end < len(d.text) else None}
        return json.dumps(meta, ensure_ascii=False) + "\n---\n" + chunk

    @beta_tool
    @metered
    def compare_versions(canonical_url: str) -> str:
        """List every stored version of one logical document (live page, archive
        snapshots) and the fields that changed between consecutive versions.
        Changed amounts, dates or decree numbers mean the record was rewritten.

        Args:
            canonical_url: The document's canonical URL (from read_document).
        """
        versions = ws.store.versions(canonical_url)
        if not versions:
            raise ToolError(f"No stored versions for {canonical_url}.")
        out = [{"doc_id": v.id, "kind": v.source_kind, "observed_at": v.observed_at.isoformat()} for v in versions]
        for a, b in zip(versions, versions[1:]):
            changes = [c.model_dump() for c in diff_fields(a, b)] if a.text_sha256 != b.text_sha256 else []
            out.append({"from": a.id, "to": b.id, "changes": changes})
        return json.dumps(out, ensure_ascii=False)

    @beta_tool
    @metered
    def find_archived_captures(url: str, since: str | None = None, until: str | None = None) -> str:
        """List Wayback Machine captures of a URL (one per distinct content). Use this
        before trusting any official page: the archive shows what it said earlier.

        Args:
            url: Page or document URL.
            since: Optional year or yyyymmdd lower bound.
            until: Optional year or yyyymmdd upper bound.
        """
        if ws.connectors.wayback is None:
            raise ToolError("Archive connector not configured.")
        caps = ws.connectors.wayback.captures(url, since=since, until=until)
        return json.dumps([{"timestamp": c.timestamp, "original": c.original, "mimetype": c.mimetype} for c in caps]) \
            if caps else "No captures."

    @beta_tool
    @metered
    def ingest_archived_capture(url: str, timestamp: str, publisher: str) -> str:
        """Fetch one Wayback capture in raw form, hash it, and store it as an archive
        document dated at capture time. Returns the doc_id.

        Args:
            url: The original URL of the capture.
            timestamp: The 14-digit capture timestamp from find_archived_captures.
            publisher: Who originally published the page (e.g. "JORT", "TUNEPS").
        """
        if ws.connectors.wayback is None:
            raise ToolError("Archive connector not configured.")
        cap = Capture(timestamp=timestamp, original=url, digest="", mimetype="")
        raw = ws.connectors.wayback.fetch(cap)
        doc_id = store_document(raw, kind=SourceKind.ARCHIVE, url=cap.raw_url, canonical_url=url,
                                publisher=publisher, observed_at=cap.captured_at, filename=url)
        return f"Stored as {doc_id}."

    @beta_tool
    @metered
    def ingest_url(url: str, source_kind: KindName, publisher: str, canonical_url: str | None = None) -> str:
        """Fetch a live URL now, hash it, and store it. For official pages, also check the
        archive: a live page can be edited after the fact. Returns the doc_id.

        Args:
            url: URL to fetch.
            source_kind: What kind of source this is.
            publisher: Organisation or outlet that published it.
            canonical_url: Stable identity of the document if different from url.
        """
        if ws.connectors.live is None:
            raise ToolError("Live fetching not configured.")
        fetched = ws.connectors.live.fetch(url)
        doc_id = store_document(fetched.content, kind=SourceKind(source_kind), url=fetched.url,
                                canonical_url=canonical_url or url, publisher=publisher,
                                observed_at=datetime.now(UTC), filename=url)
        return f"Stored as {doc_id}."

    @beta_tool
    @metered
    def search_funder_records(query: str, country_code: str = "TN") -> str:
        """Search World Bank project records (commitments, dates, implementing agency).
        Results are stored as foreign-mirror documents: an independent record of money
        that the borrowing ministry cannot edit.

        Args:
            query: Project keywords, e.g. "electricity generation capacity".
            country_code: ISO-2 country code.
        """
        if ws.connectors.funders is None:
            raise ToolError("Funder connector not configured.")
        request_url, raw, projects = ws.connectors.funders.search(query, country_code)
        doc_id = store_document(raw, kind=SourceKind.FOREIGN_MIRROR, url=request_url, canonical_url=request_url,
                                publisher="World Bank", observed_at=datetime.now(UTC), filename="projects.json")
        brief = [{k: p.get(k) for k in ("id", "project_name", "totalcommamt", "boardapprovaldate", "status")}
                 for p in projects]
        return json.dumps({"doc_id": doc_id, "projects": brief}, ensure_ascii=False)

    @beta_tool
    @metered
    def record_evidence(
        doc_id: str,
        subclaim_id: str,
        relation: Literal["supports", "contradicts", "qualifies"],
        quote: str,
        rationale: str,
    ) -> str:
        """Record that a document supports, contradicts or qualifies a sub-claim.
        Checked immediately: the quote must appear verbatim in the document, and the
        document's dates must be compatible with the sub-claim.

        Args:
            doc_id: Document id.
            subclaim_id: Sub-claim id (C1, C2, ...).
            relation: supports / contradicts / qualifies (adds a condition or innocent explanation).
            quote: Exact text copied from the document.
            rationale: One sentence on why this quote bears on the sub-claim.
        """
        edge = EvidenceEdge(doc_id=doc_id, subclaim_id=subclaim_id, relation=Relation(relation),
                            quote=quote, rationale=rationale)
        reason = ws.record_edge(edge)
        if reason:
            raise ToolError(f"Rejected: {reason}")
        return "Accepted."

    @beta_tool
    @metered
    def record_amount(
        doc_id: str,
        role: Literal["allocated", "disbursed", "benchmark", "proven_spend"],
        amount_tnd: float,
        quote: str,
    ) -> str:
        """Record a monetary amount in Tunisian dinars for the financial check. The
        amount must be readable from the quote, which must appear in the document.

        Args:
            doc_id: Document id.
            role: allocated (awarded/budgeted), disbursed (paid), benchmark (comparable
                works), proven_spend (documented actual cost).
            amount_tnd: Amount in dinars (units, not millions).
            quote: Exact text containing the amount.
        """
        reason = ws.record_figure(FinancialFigure(doc_id=doc_id, role=AmountRole(role), amount_tnd=amount_tnd, quote=quote))
        if reason:
            raise ToolError(f"Rejected: {reason}")
        return "Accepted."

    @beta_tool
    @metered
    def compare_names(names: list[str], kind: Literal["person", "company"]) -> str:
        """Check whether names in different scripts or spellings may refer to the same
        company or person (Arabic/French, word order, Ben/Bin). Person matches are
        leads for human review, never proof of identity.

        Args:
            names: Two or more names.
            kind: person or company.
        """
        pairs = []
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                m = match(a, b, EntityKind(kind))
                if m.score >= 0.5:
                    pairs.append({"a": a, "b": b, "score": m.score, "same": m.same, "needs_review": m.needs_review})
        return json.dumps(pairs, ensure_ascii=False) if pairs else "No likely matches."

    @beta_tool
    def assess() -> str:
        """Score the evidence recorded so far. Returns each sub-claim's status,
        hypotheses, retcon flags, the financial check, what evidence is still missing,
        supported sub-claims not yet challenged, and the remaining tool budget. Use it
        to decide the next search."""
        v = ws.verdict()
        out = {
            "verdict": v.verdict,
            "confidence": v.confidence,
            "subclaims": {c.id: {"status": c.status, "support": c.support, "contradiction": c.contradiction,
                                 "independent_supporting_sources": len(c.supporting_clusters)} for c in v.by_subclaim},
            "hypotheses": {h.id: h.status for h in v.hypotheses},
            "retcon_flags": [f"{f.canonical_url}: {[c.model_dump() for c in f.changes]}" for f in v.retcon_flags],
            "financial": v.financial.model_dump(exclude={"figures"}) if v.financial else None,
            "missing_evidence": v.missing_evidence,
            "not_yet_challenged": ws.unchallenged(v),
            "budget_left": ws.budget,
        }
        ws.log("assess", {}, f"{v.verdict} {v.confidence}")
        return json.dumps(out, ensure_ascii=False, default=str)

    @beta_tool
    def finish(summary: str) -> str:
        """End the investigation. Refused while any supported sub-claim has not been
        challenged by at least one search with purpose "challenge" (unless the budget
        is spent). The summary must cite documents as [doc_id] and must not name or
        accuse individuals.

        Args:
            summary: Plain-language account of what the evidence shows and what is missing.
        """
        pending = ws.unchallenged()
        if pending and ws.budget > 0:
            raise ToolError(
                f"Not finished: sub-claims {pending} are supported but no challenge search has "
                "looked for evidence against them (emergency decrees, force majeure, price shocks, corrections)."
            )
        ws.summary = summary
        ws.log("finish", {}, "done")
        return "Investigation closed. Reply with a one-line acknowledgement only."

    return [search_evidence, read_document, compare_versions, find_archived_captures, ingest_archived_capture,
            ingest_url, search_funder_records, record_evidence, record_amount, compare_names, assess, finish]
