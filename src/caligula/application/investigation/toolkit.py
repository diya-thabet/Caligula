"""Tools the agents can call, as plain functions.

Tool docstrings are the model's instructions for each tool, so they say when
to use it and what comes back. A tool refuses a call by raising `ToolRefusal`;
the LLM adapter turns that into a tool error for the model. `build_tools` hands each agent only the tools
of its role; every call is charged to that agent's budget except the ones
needed to wrap up (`assess`, `report`, `finish`, `complete_review`).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from functools import wraps
from itertools import pairwise
from typing import Literal

from caligula.application.investigation.plan import Outcome
from caligula.application.investigation.workspace import (
    AgentContext,
    ProposalStatus,
    Purpose,
    Workspace,
)
from caligula.application.ports.llm import Tool, ToolRefusal
from caligula.application.ports.sources import ExtractedText, PrivateSourceError
from caligula.domain.model.claims import Party, PartyRole
from caligula.domain.model.documents import SourceKind
from caligula.domain.model.evidence import AmountRole, EvidenceEdge, FinancialFigure, Relation
from caligula.domain.services.interest import interest, role_of
from caligula.domain.services.names import EntityKind, match
from caligula.domain.services.privacy import MINIMISED_KINDS, minimise
from caligula.domain.services.retcon import diff_fields
from caligula.domain.services.text import sha256_bytes

MAX_READ = 8000
KindName = Literal[
    "official_live", "archive", "foreign_mirror", "audit", "statistics", "contributor", "osint", "news", "social"
]
SpecialistName = Literal["official", "funders_audit", "web_news", "social", "telegram"]


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    d = datetime.fromisoformat(value)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def build_tools(ws: Workspace, ctx: AgentContext | None = None, names: Iterable[str] | None = None) -> list[Tool]:
    """Tools bound to one agent. `ctx` defaults to a single agent using the workspace budget."""
    single = ctx is None
    ctx = ctx or AgentContext(name="investigator", budget=ws.budget)

    def spend() -> None:
        if single:
            ws.budget -= 1
            ctx.budget = ws.budget
        else:
            ctx.budget -= 1

    def metered(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(**kwargs):
            if ws.finished or ctx.done:
                raise ToolRefusal("Your part of the investigation is finished; no further tool calls.")
            if ctx.budget <= 0:
                raise ToolRefusal("Tool budget exhausted. Wrap up now (report, finish or complete_review).")
            spend()
            try:
                out = fn(**kwargs)
            except ToolRefusal as exc:
                ws.log(ctx.name, fn.__name__, kwargs, f"error: {exc}")
                raise
            except Exception as exc:  # connector failures are information, not crashes
                ws.log(ctx.name, fn.__name__, kwargs, f"error: {exc}")
                raise ToolRefusal(f"{type(exc).__name__}: {exc}") from exc
            ws.log(ctx.name, fn.__name__, kwargs, out[:300])
            return out

        return wrapper

    def store_document(raw: bytes, *, kind: SourceKind, url: str, canonical_url: str, publisher: str,
                       observed_at: datetime, filename: str = "", text: str | None = None,
                       published_at: datetime | None = None) -> str:
        doc_id = f"{kind.value}-{sha256_bytes(raw)[:12]}"
        with ws.lock:
            if ws.store.get(doc_id) is not None:
                return doc_id
            extraction = "plain"
            if text is None:
                extractor = ws.connectors.extractor
                extracted = (extractor.extract(raw, filename or url) if extractor
                             else ExtractedText(raw.decode("utf-8", "replace"), "plain"))
                text, extraction = extracted.text, extracted.method
            masked: dict[str, int] = {}
            if kind in MINIMISED_KINDS:
                text, masked = minimise(text)
            doc = ws.store.add(doc_id=doc_id, raw=raw, text=text, extraction=extraction, canonical_url=canonical_url,
                               url=url, source_kind=kind, publisher=publisher, observed_at=observed_at,
                               published_at=published_at)
            ws.ledger.append("capture", ctx.name, doc_id=doc_id, url=url, raw_sha256=doc.raw_sha256,
                             observed_at=observed_at.isoformat(), masked=masked)
        return doc_id

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
            query: Search text in French or English.
            purpose: "support" to find evidence for a sub-claim, "challenge" to look for
                evidence that would refute it or give an innocent explanation, "explore" otherwise.
            subclaim_id: The sub-claim this search is about, if any.
            source_kinds: Restrict to these source kinds.
            observed_after: ISO date; only documents we or an archive observed on/after it.
            observed_before: ISO date; only documents observed on/before it.
            k: Number of results.
        """
        ws.add_search(Purpose(purpose), subclaim_id, query)
        with ws.lock:  # other agents may be adding documents concurrently
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

    @metered
    def read_document(doc_id: str, offset: int = 0) -> str:
        """Read a stored document's text and metadata. Long documents are returned in
        windows; call again with the returned next_offset to continue. Personal
        identifiers in social, news and contributor texts are masked.

        Args:
            doc_id: Document id from a search or ingest result.
            offset: Character offset to start from.
        """
        d = ws.store.get(doc_id)
        if d is None:
            raise ToolRefusal(f"No document {doc_id}.")
        chunk = d.text[offset : offset + MAX_READ]
        end = offset + len(chunk)
        meta = {"doc_id": d.id, "kind": d.source_kind, "publisher": d.publisher, "url": d.url,
                "canonical_url": d.canonical_url, "extraction": d.extraction,
                "published_at": d.published_at.isoformat() if d.published_at else None,
                "observed_at": d.observed_at.isoformat(), "cites": d.cites,
                "next_offset": end if end < len(d.text) else None}
        return json.dumps(meta, ensure_ascii=False) + "\n---\n" + chunk

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
            raise ToolRefusal(f"No stored versions for {canonical_url}.")
        out = [{"doc_id": v.id, "kind": v.source_kind, "observed_at": v.observed_at.isoformat()} for v in versions]
        for a, b in pairwise(versions):
            changes = [c.model_dump() for c in diff_fields(a, b)] if a.text_sha256 != b.text_sha256 else []
            out.append({"from": a.id, "to": b.id, "changes": changes})
        return json.dumps(out, ensure_ascii=False)

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
            raise ToolRefusal("Archive connector not configured.")
        caps = ws.connectors.wayback.captures(url, since=since, until=until)
        return json.dumps([{"timestamp": c.timestamp, "original": c.original, "mimetype": c.mimetype} for c in caps]) \
            if caps else "No captures."

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
            raise ToolRefusal("Archive connector not configured.")
        copy = ws.connectors.wayback.fetch(url, timestamp)
        doc_id = store_document(copy.content, kind=SourceKind.ARCHIVE, url=copy.url, canonical_url=url,
                                publisher=publisher, observed_at=copy.captured_at, filename=url)
        return f"Stored as {doc_id}."

    @metered
    def ingest_url(url: str, source_kind: KindName, publisher: str, canonical_url: str | None = None) -> str:
        """Fetch a publicly accessible URL now, hash it, and store it exactly as served:
        an official claim stored this way is proof of what was said, even if the page
        changes later. Never use for pages behind a login or paywall. For official
        pages, also check the archive. Returns the doc_id.

        Args:
            url: URL to fetch.
            source_kind: What kind of source this is.
            publisher: Organisation, outlet or account that published it.
            canonical_url: Stable identity of the document if different from url.
        """
        if ws.connectors.live is None:
            raise ToolRefusal("Live fetching not configured.")
        fetched = ws.connectors.live.fetch(url)
        doc_id = store_document(fetched.content, kind=SourceKind(source_kind), url=fetched.url,
                                canonical_url=canonical_url or url, publisher=publisher,
                                observed_at=datetime.now(UTC), filename=url)
        return f"Stored as {doc_id}."

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
            raise ToolRefusal("Funder connector not configured.")
        request_url, raw, projects = ws.connectors.funders.search(query, country_code)
        doc_id = store_document(raw, kind=SourceKind.FOREIGN_MIRROR, url=request_url, canonical_url=request_url,
                                publisher="World Bank", observed_at=datetime.now(UTC), filename="projects.json")
        brief = [{k: p.get(k) for k in ("id", "project_name", "totalcommamt", "boardapprovaldate", "status")}
                 for p in projects]
        return json.dumps({"doc_id": doc_id, "projects": brief}, ensure_ascii=False)

    @metered
    def fetch_telegram_channel(channel: str, keywords: list[str] | None = None, before: int | None = None) -> str:
        """Read recent posts of a PUBLIC Telegram channel (e.g. "@channel" or
        "https://t.me/channel"), store the matching posts, and return their doc_ids.
        Private groups and invite links are refused. Forwarded posts show their origin:
        many channels forwarding one post are one source.

        Args:
            channel: Public channel name or link.
            keywords: Keep only posts containing one of these words (case-insensitive).
            before: Post id to page back from.
        """
        if ws.connectors.telegram is None:
            raise ToolRefusal("Telegram connector not configured.")
        try:
            page_url, raw_page, posts = ws.connectors.telegram.fetch(channel, before=before)
        except PrivateSourceError as exc:
            raise ToolRefusal(str(exc)) from exc
        ws.ledger.append("capture", ctx.name, url=page_url, raw_sha256=sha256_bytes(raw_page), posts=len(posts))
        terms = [k.lower() for k in keywords or []]
        stored = []
        for p in posts:
            if terms and not any(t in p.text.lower() for t in terms):
                continue
            header = f"Telegram @{p.channel}, post {p.post_id}" + (f", forwarded from {p.forwarded_from}" if p.forwarded_from else "")
            text = f"{header}\n{p.text}"
            raw = json.dumps({"url": p.url, "posted_at": p.posted_at.isoformat() if p.posted_at else None,
                              "forwarded_from": p.forwarded_from, "text": p.text}, ensure_ascii=False).encode()
            doc_id = store_document(raw, kind=SourceKind.SOCIAL, url=p.url, canonical_url=p.url,
                                    publisher=f"Telegram @{p.channel}", observed_at=datetime.now(UTC),
                                    text=text, published_at=p.posted_at)
            stored.append({"doc_id": doc_id, "posted_at": p.posted_at.isoformat() if p.posted_at else None,
                           "forwarded_from": p.forwarded_from, "snippet": ws.store.get(doc_id).text[:200]})
        oldest = min((p.post_id for p in posts), default=None)
        return json.dumps({"stored": stored, "posts_on_page": len(posts), "page_back_with_before": oldest},
                          ensure_ascii=False)

    def _record(item: EvidenceEdge | FinancialFigure) -> str:
        reason, proposal_id = ws.record(item, ctx.name)
        if reason:
            raise ToolRefusal(f"Rejected: {reason}")
        if proposal_id and ctx.name == "reviewer":
            ws.review(proposal_id, True, "recorded by reviewer", ctx.name)
            return "Accepted."
        return f"Proposed as {proposal_id}; the reviewer decides whether it counts." if proposal_id else "Accepted."

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
        return _record(EvidenceEdge(doc_id=doc_id, subclaim_id=subclaim_id, relation=Relation(relation),
                                    quote=quote, rationale=rationale))

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
        return _record(FinancialFigure(doc_id=doc_id, role=AmountRole(role), amount_tnd=amount_tnd, quote=quote))

    @metered
    def compare_names(names: list[str], kind: Literal["person", "company"]) -> str:
        """Check whether names in different spellings may refer to the same company or
        person (word order, accents, Ben/Bin, Arabic transliterations). Person matches
        are leads for human review, never proof of identity.

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

    def assess() -> str:
        """Score the evidence that currently counts. Returns each sub-claim's status,
        hypotheses, retcon flags, the financial check, missing evidence, supported
        sub-claims not yet challenged, pending proposals and your remaining budget."""
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
            "coverage": ws.coverage(),
            "open_tasks": [f"{t.id} {t.specialist}: {t.objective[:80]}" for t in ws.open_tasks()],
            "pending_proposals": sum(p.status == ProposalStatus.PENDING for p in ws.proposals),
            "budget_left": ctx.budget,
        }
        ws.log(ctx.name, "assess", {}, f"{v.verdict} {v.confidence}")
        return json.dumps(out, ensure_ascii=False, default=str)

    # --- collector tasks and wrap-up -------------------------------------------

    def list_tasks() -> str:
        """Your open tasks for this round, and leads other agents left for you. Work the
        tasks in order of importance; close each one with complete_task."""
        tasks = [t.model_dump(include={"id", "objective", "subclaim_ids", "purpose", "queries", "urls", "created_by"})
                 for t in ws.open_tasks(ctx.name)]
        leads = [{"from": lead.by, "note": lead.note} for lead in ws.leads_for(ctx.name)]
        return json.dumps({"tasks": tasks, "leads": leads}, ensure_ascii=False)

    @metered
    def complete_task(
        task_id: str,
        outcome: Literal["found", "partial", "not_found", "blocked"],
        note: str,
        doc_ids: list[str] | None = None,
    ) -> str:
        """Close one of your tasks. "not_found" means you searched properly and the
        thing does not exist in reach (absence is information: say where you looked).
        "blocked" means the source was unreachable or needs access we do not have.

        Args:
            task_id: Task id (T1, T2, ...).
            outcome: found / partial / not_found / blocked.
            note: What you did and what it showed, in one to three sentences.
            doc_ids: Stored documents that answer the task.
        """
        try:
            t = ws.close_task(task_id, ctx.name, Outcome(outcome), note, doc_ids or [])
        except (KeyError, ValueError) as exc:
            raise ToolRefusal(str(exc)) from exc
        left = len(ws.open_tasks(ctx.name))
        return f"{t.id} closed ({t.outcome}). {left} open task(s) left."

    @metered
    def post_lead(
        to: Literal["official", "funders_audit", "web_news", "social", "telegram", "reviewer", "all"],
        note: str,
    ) -> str:
        """Leave a lead for another agent working in parallel: a URL, a name spelling,
        a decree number, a date. They see it the next time they list their tasks.

        Args:
            to: Recipient agent, or "all".
            note: The lead, specific enough to act on.
        """
        ws.post_lead(ctx.name, to, note)
        return "Lead posted."

    def report(summary: str) -> str:
        """Finish your collection round. Refused while you have open tasks, unless your
        budget is spent. Summarise what you stored and proposed, what you looked for
        and did not find, and leads other specialists should follow. Cite [doc_id].

        Args:
            summary: Your report to the reviewer.
        """
        still_open = [t.id for t in ws.open_tasks(ctx.name)]
        if still_open and ctx.budget > 0:
            raise ToolRefusal(f"Close your open tasks first: {still_open} (use complete_task, outcome "
                            "'not_found' or 'blocked' if you could not answer them).")
        ctx.done, ctx.report = True, summary
        ws.log(ctx.name, "report", {}, summary[:300])
        return "Report filed. Reply with a one-line acknowledgement only."

    # --- reviewer ------------------------------------------------------------

    @metered
    def list_proposals(status: Literal["pending", "accepted", "disputed"] = "pending") -> str:
        """List evidence proposed by the collectors, with the quoted text and the
        document's source kind and dates, so you can judge each one.

        Args:
            status: Which proposals to list.
        """
        rows = []
        for p in ws.proposals:
            if p.status != status:
                continue
            d = ws.store.get(p.item.doc_id)
            row = {"id": p.id, "by": p.by, **p.item.model_dump(mode="json"), "doc_kind": d.source_kind,
                   "doc_publisher": d.publisher, "doc_observed_at": d.observed_at.date().isoformat(), "note": p.note}
            if isinstance(p.item, EvidenceEdge):
                row["publisher_interest"] = interest(role_of(d.publisher, ws.allegation.parties),
                                                     ws.allegation.bearing_of(p.item.subclaim_id), p.item.relation)
            rows.append(row)
        return json.dumps(rows, ensure_ascii=False) if rows else f"No {status} proposals."

    @metered
    def review_proposal(proposal_id: str, decision: Literal["accept", "dispute"], note: str) -> str:
        """Accept a proposal (it then counts in the scoring) or dispute it (it does not).
        Dispute when the quote does not actually bear on the sub-claim, the relation is
        wrong, the document concerns a different entity or date, or it merely repeats a
        source already counted. You may change an earlier decision.

        Args:
            proposal_id: Proposal id (P1, P2, ...).
            decision: accept or dispute.
            note: The reason, one or two sentences.
        """
        try:
            p = ws.review(proposal_id, decision == "accept", note, ctx.name)
        except KeyError as exc:
            raise ToolRefusal(f"No proposal {proposal_id}.") from exc
        return f"{p.id} {p.status}."

    @metered
    def register_party(name: str, role: Literal["accused", "complainant"], aliases: list[str] | None = None) -> str:
        """Declare a publisher as a party with a stake in the case: the body, company
        or office whose conduct is at issue (accused), or whoever makes the allegation
        (complainant). Evidence it publishes is then weighed as self-serving or as
        against its own interest. Use it for other names of a known party (a ministry's
        directorate, a company's trade name) and for complainants' outlets; never for
        a neutral source you merely distrust.

        Args:
            name: The party's name as it publishes.
            role: accused or complainant.
            aliases: Other names, acronyms and spellings it publishes under.
        """
        party = ws.add_party(Party(name=name, role=PartyRole(role), aliases=aliases or []), ctx.name)
        return f"{party.name} registered as {party.role.value} (aliases: {', '.join(party.aliases) or 'none'})."

    @metered
    def request_collection(
        specialist: SpecialistName,
        instructions: str,
        purpose: Literal["support", "challenge", "explore"],
        subclaim_ids: list[str] | None = None,
        queries: list[str] | None = None,
        urls: list[str] | None = None,
    ) -> str:
        """Create a task for a source specialist in the next round: a gap to fill, a
        lead to follow, or an innocent explanation to look for (purpose "challenge").

        Args:
            specialist: official (JORT, TUNEPS, ministries, archives of their pages),
                funders_audit (World Bank, audit and statistics), web_news (articles),
                social (public posts of officials and institutions), telegram (public channels).
            instructions: What to look for and where, precise enough to act on.
            purpose: support, challenge or explore.
            subclaim_ids: The sub-claims concerned.
            queries: Suggested search queries.
            urls: Specific URLs to fetch or check in the archive.
        """
        known = {c.id for c in ws.allegation.subclaims}
        t = ws.add_task(specialist=specialist, objective=instructions, purpose=purpose,
                        subclaim_ids=[i for i in subclaim_ids or [] if i in known], queries=queries or [],
                        urls=urls or [], round=ws.round + 1, created_by=ctx.name)
        return f"Task {t.id} queued for {specialist} in the next round."

    def complete_review(summary: str) -> str:
        """Close this round's review. Refused while proposals are pending (unless your
        budget is spent). Challenge tasks for supported sub-claims are queued
        automatically; add your own with request_collection when you see a specific
        innocent explanation worth checking. The summary is for a human editor: the
        anomalies, the evidence for each, contradictions, and what is still needed.
        Cite documents as [doc_id]; do not name or accuse individuals.

        Args:
            summary: Review summary.
        """
        pending = [p.id for p in ws.proposals if p.status == ProposalStatus.PENDING]
        if pending and ctx.budget > 0:
            raise ToolRefusal(f"Not finished: proposals {pending} are still pending.")
        ctx.done, ctx.report = True, summary
        ws.log(ctx.name, "complete_review", {}, summary[:300])
        return "Review closed. Reply with a one-line acknowledgement only."

    # --- single-agent wrap-up ------------------------------------------------

    def finish(summary: str) -> str:
        """End the investigation. Refused while any supported sub-claim has not been
        challenged by at least one search with purpose "challenge" (unless the budget
        is spent). The summary must cite documents as [doc_id] and must not name or
        accuse individuals.

        Args:
            summary: Plain-language account of what the evidence shows and what is missing.
        """
        pending = ws.unchallenged()
        if pending and ctx.budget > 0:
            raise ToolRefusal(
                f"Not finished: sub-claims {pending} are supported but no challenge search has "
                "looked for evidence against them (emergency decrees, force majeure, price shocks, corrections)."
            )
        ws.summary = summary
        ws.log(ctx.name, "finish", {}, "done")
        return "Investigation closed. Reply with a one-line acknowledgement only."

    everything = {t.__name__: t for t in [
        search_evidence, read_document, compare_versions, find_archived_captures, ingest_archived_capture,
        ingest_url, search_funder_records, fetch_telegram_channel, record_evidence, record_amount, compare_names,
        assess, list_tasks, complete_task, post_lead, report, list_proposals, review_proposal, register_party,
        request_collection, complete_review, finish,
    ]}
    if names is None:
        names = SINGLE_AGENT_TOOLS
    return [everything[n] for n in names]


SINGLE_AGENT_TOOLS = [
    "search_evidence", "read_document", "compare_versions", "find_archived_captures", "ingest_archived_capture",
    "ingest_url", "search_funder_records", "fetch_telegram_channel", "record_evidence", "record_amount",
    "compare_names", "register_party", "assess", "finish",
]
