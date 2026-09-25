"""State of one investigation, owned by code, not by the model.

Agents change it only through tools, and every write is validated on the spot
so the model gets immediate feedback. Several agents (source specialists and
a reviewer) may run in parallel threads on the same workspace, so mutations
take a lock.

With `review_required`, evidence recorded by collectors is only *proposed*;
it counts once the reviewer accepts it.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum

from caligula.ingest.sources import LiveFetcher, WorldBankClient
from caligula.ingest.telegram import TelegramClient
from caligula.ingest.wayback import WaybackClient
from caligula.ledger import Ledger
from caligula.models import (
    Allegation,
    EvidenceEdge,
    FinancialFigure,
    RejectedEvidence,
    Verdict,
)
from caligula.scoring import DEFAULT_PARAMS, SUPPORTED, Params
from caligula.store import EvidenceStore
from caligula.validate import validate_edges, validate_figures
from caligula.verdict import build_verdict


class Mode(StrEnum):
    # Quick check of a public claim; short budget; answer suitable for a public reply.
    FACTCHECK = "factcheck"
    # Full case: multi-hop, financial checks, challenge phase; output goes to human review.
    INVESTIGATE = "investigate"


BUDGETS = {Mode.FACTCHECK: 25, Mode.INVESTIGATE: 80}


class Purpose(StrEnum):
    SUPPORT = "support"
    CHALLENGE = "challenge"  # looking for evidence that would clear the allegation
    EXPLORE = "explore"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISPUTED = "disputed"


@dataclass
class Proposal:
    id: str
    by: str
    item: EvidenceEdge | FinancialFigure
    status: ProposalStatus = ProposalStatus.PENDING
    note: str = ""


@dataclass
class CollectionRequest:
    specialist: str
    instructions: str
    subclaim_id: str | None
    purpose: Purpose


@dataclass
class TraceEntry:
    step: int
    agent: str
    tool: str
    args: dict
    outcome: str


@dataclass
class AgentContext:
    """One agent's identity and budget within a shared workspace."""

    name: str
    budget: int
    done: bool = False
    report: str | None = None


@dataclass
class Connectors:
    wayback: WaybackClient | None = None
    live: LiveFetcher | None = None
    funders: WorldBankClient | None = None
    telegram: TelegramClient | None = None


@dataclass
class Workspace:
    store: EvidenceStore
    allegation: Allegation
    mode: Mode
    connectors: Connectors = field(default_factory=Connectors)
    params: Params = DEFAULT_PARAMS
    ledger: Ledger = field(default_factory=Ledger)
    review_required: bool = False
    edges: list[EvidenceEdge] = field(default_factory=list)
    figures: list[FinancialFigure] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    requests: list[CollectionRequest] = field(default_factory=list)
    rejected: list[RejectedEvidence] = field(default_factory=list)
    trace: list[TraceEntry] = field(default_factory=list)
    searches: list[tuple[Purpose, str | None, str]] = field(default_factory=list)
    budget: int = 0  # default budget for a single-agent run
    summary: str | None = None

    def __post_init__(self):
        self.budget = self.budget or BUDGETS[self.mode]
        self.lock = threading.RLock()

    @property
    def finished(self) -> bool:
        return self.summary is not None

    def log(self, agent: str, tool: str, args: dict, outcome: str) -> None:
        with self.lock:
            self.trace.append(TraceEntry(len(self.trace) + 1, agent, tool, args, outcome))

    def add_search(self, purpose: Purpose, subclaim_id: str | None, query: str) -> None:
        with self.lock:
            self.searches.append((purpose, subclaim_id, query))

    def record(self, item: EvidenceEdge | FinancialFigure, by: str) -> tuple[str | None, str | None]:
        """Validate and record. Returns (rejection reason, proposal id)."""
        with self.lock:
            if isinstance(item, EvidenceEdge):
                kept, rejected = validate_edges(self.store, self.allegation, [item])
            else:
                kept, rejected = validate_figures(self.store, [item])
            self.rejected += rejected
            if rejected:
                self.ledger.append("rejection", by, item=item.model_dump(mode="json"), reason=rejected[0].reason)
                return rejected[0].reason, None
            if not self.review_required:
                self._accept(item)
                self.ledger.append("evidence", by, item=item.model_dump(mode="json"))
                return None, None
            if any(p.item == item for p in self.proposals):
                return None, next(p.id for p in self.proposals if p.item == item)
            proposal = Proposal(id=f"P{len(self.proposals) + 1}", by=by, item=item)
            self.proposals.append(proposal)
            self.ledger.append("proposal", by, id=proposal.id, item=item.model_dump(mode="json"))
            return None, proposal.id

    def _accept(self, item: EvidenceEdge | FinancialFigure) -> None:
        target = self.edges if isinstance(item, EvidenceEdge) else self.figures
        if item not in target:
            target.append(item)

    def review(self, proposal_id: str, accept: bool, note: str, reviewer: str) -> Proposal:
        with self.lock:
            p = next((p for p in self.proposals if p.id == proposal_id), None)
            if p is None:
                raise KeyError(proposal_id)
            if p.status == ProposalStatus.ACCEPTED and not accept:
                target = self.edges if isinstance(p.item, EvidenceEdge) else self.figures
                target.remove(p.item)
            p.status = ProposalStatus.ACCEPTED if accept else ProposalStatus.DISPUTED
            p.note = note
            if accept:
                self._accept(p.item)
            self.ledger.append("review", reviewer, id=p.id, status=p.status.value, note=note)
            return p

    def verdict(self) -> Verdict:
        with self.lock:
            v = build_verdict(self.store, self.allegation, list(self.edges), list(self.figures), self.params)
            v.rejected_evidence = self.rejected + v.rejected_evidence
            return v

    def unchallenged(self, verdict: Verdict | None = None) -> list[str]:
        """Supported sub-claims nobody has yet tried to refute."""
        verdict = verdict or self.verdict()
        challenged = {sid for purpose, sid, _ in self.searches if purpose == Purpose.CHALLENGE}
        return [c.id for c in verdict.by_subclaim if c.status == SUPPORTED and c.id not in challenged]
