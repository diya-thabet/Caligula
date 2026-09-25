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
from datetime import datetime
from enum import StrEnum

from caligula.application.evidence_store import EvidenceStore
from caligula.application.investigation.plan import EntityHint, Outcome, Task, TaskStatus
from caligula.application.ports.sources import ArchiveSource, FunderRecords, TelegramChannels, TextExtractor, WebFetcher
from caligula.application.ports.storage import Ledger
from caligula.domain.model.claims import Allegation, Party
from caligula.domain.model.evidence import AbsenceFinding, EvidenceEdge, FinancialFigure, RejectedEvidence
from caligula.domain.model.verdict import Verdict
from caligula.domain.services.absence import validate_absences
from caligula.domain.services.scoring import DEFAULT_PARAMS, SUPPORTED, Params
from caligula.domain.services.validation import validate_edges, validate_figures
from caligula.domain.services.verdict import build_verdict


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


Item = EvidenceEdge | FinancialFigure | AbsenceFinding


@dataclass
class Proposal:
    id: str
    by: str
    item: Item
    status: ProposalStatus = ProposalStatus.PENDING
    note: str = ""


@dataclass
class Lead:
    """A tip one agent leaves for another during a round (the shared board)."""

    by: str
    to: str
    note: str
    round: int


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
    wayback: ArchiveSource | None = None
    live: WebFetcher | None = None
    funders: FunderRecords | None = None
    telegram: TelegramChannels | None = None
    extractor: TextExtractor | None = None  # plain UTF-8 decoding when absent


@dataclass
class Workspace:
    store: EvidenceStore
    allegation: Allegation
    mode: Mode
    ledger: Ledger
    connectors: Connectors = field(default_factory=Connectors)
    params: Params = DEFAULT_PARAMS
    review_required: bool = False
    edges: list[EvidenceEdge] = field(default_factory=list)
    figures: list[FinancialFigure] = field(default_factory=list)
    absences: list[AbsenceFinding] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    leads: list[Lead] = field(default_factory=list)
    entities: list[EntityHint] = field(default_factory=list)
    window: tuple[datetime | None, datetime | None] = (None, None)  # period under investigation
    round: int = 1
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

    def add_party(self, party: Party, by: str) -> Party:
        """Declare a party with a stake in the case, or add aliases to a known one."""
        with self.lock:
            known = next((p for p in self.allegation.parties if p.name.casefold() == party.name.casefold()), None)
            if known is None:
                self.allegation.parties.append(party)
                known = party
            else:
                known.aliases += [a for a in party.aliases if a not in known.aliases]
            self.ledger.append("party", by, name=known.name, role=known.role.value, aliases=known.aliases)
            return known

    # --- tasks and leads ---------------------------------------------------

    def add_task(self, **fields) -> Task:
        with self.lock:
            task = Task(id=f"T{len(self.tasks) + 1}", **fields)
            self.tasks.append(task)
            self.ledger.append("task", task.created_by, id=task.id, specialist=task.specialist,
                               objective=task.objective, purpose=task.purpose, round=task.round)
            return task

    def open_tasks(self, specialist: str | None = None) -> list[Task]:
        with self.lock:
            return [t for t in self.tasks if t.status == TaskStatus.OPEN and t.round <= self.round
                    and (specialist is None or t.specialist == specialist)]

    def close_task(self, task_id: str, specialist: str, outcome: Outcome, note: str, doc_ids: list[str]) -> Task:
        with self.lock:
            task = next((t for t in self.tasks if t.id == task_id), None)
            if task is None or task.specialist != specialist:
                raise KeyError(f"no task {task_id} assigned to {specialist}")
            unknown = [d for d in doc_ids if self.store.get(d) is None]
            if unknown:
                raise ValueError(f"unknown documents {unknown}")
            task.status, task.outcome, task.note, task.doc_ids = TaskStatus.DONE, outcome, note, doc_ids
            self.ledger.append("task_closed", specialist, id=task.id, outcome=outcome.value, doc_ids=doc_ids)
            return task

    def post_lead(self, by: str, to: str, note: str) -> None:
        with self.lock:
            self.leads.append(Lead(by, to, note, self.round))

    def leads_for(self, specialist: str) -> list[Lead]:
        with self.lock:
            return [lead for lead in self.leads if lead.to in (specialist, "all") and lead.by != specialist]

    def coverage(self) -> dict[str, dict]:
        """Per sub-claim: which specialists were tasked, task outcomes, and whether it was challenged."""
        with self.lock:
            challenged = {sid for purpose, sid, _ in self.searches if purpose == Purpose.CHALLENGE}
            out = {}
            for c in self.allegation.subclaims:
                tasks = [t for t in self.tasks if c.id in t.subclaim_ids]
                out[c.id] = {
                    "specialists": sorted({t.specialist for t in tasks}),
                    "outcomes": {t.id: t.outcome.value if t.outcome else "open" for t in tasks},
                    "challenged": c.id in challenged
                    or any(t.purpose == "challenge" and t.status == TaskStatus.DONE for t in tasks),
                }
            return out

    def absence_for(self, task: Task, searched_at: datetime) -> AbsenceFinding | None:
        """The absence finding implied by a task that searched for an expected record and found nothing."""
        expected = self.allegation.expected().get(task.expectation_id or "")
        if task.outcome != Outcome.NOT_FOUND or expected is None:
            return None
        subclaim_id, record = expected
        return AbsenceFinding(subclaim_id=subclaim_id, relation=record.absence_means, register_id=record.register_id,
                              query="; ".join(task.queries) or record.description, searched_at=searched_at,
                              window_start=self.window[0], window_end=self.window[1],
                              doc_id=task.doc_ids[0] if task.doc_ids else None,
                              note=f"{task.id}: {task.note}")

    def add_search(self, purpose: Purpose, subclaim_id: str | None, query: str) -> None:
        with self.lock:
            self.searches.append((purpose, subclaim_id, query))

    def record(self, item: Item, by: str) -> tuple[str | None, str | None]:
        """Validate and record. Returns (rejection reason, proposal id)."""
        with self.lock:
            if isinstance(item, EvidenceEdge):
                kept, rejected = validate_edges(self.store.corpus(), self.allegation, [item])
            elif isinstance(item, AbsenceFinding):
                kept, rejected = validate_absences(self.store.corpus(), self.allegation, [item])
            else:
                kept, rejected = validate_figures(self.store.corpus(), [item])
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

    def _target(self, item: Item) -> list:
        if isinstance(item, EvidenceEdge):
            return self.edges
        return self.absences if isinstance(item, AbsenceFinding) else self.figures

    def _accept(self, item: Item) -> None:
        target = self._target(item)
        if item not in target:
            target.append(item)

    def review(self, proposal_id: str, accept: bool, note: str, reviewer: str) -> Proposal:
        with self.lock:
            p = next((p for p in self.proposals if p.id == proposal_id), None)
            if p is None:
                raise KeyError(proposal_id)
            if p.status == ProposalStatus.ACCEPTED and not accept:
                self._target(p.item).remove(p.item)
            p.status = ProposalStatus.ACCEPTED if accept else ProposalStatus.DISPUTED
            p.note = note
            if accept:
                self._accept(p.item)
            self.ledger.append("review", reviewer, id=p.id, status=p.status.value, note=note)
            return p

    def verdict(self, sensitivity: bool = True) -> Verdict:
        """The verdict from accepted evidence. `sensitivity=False` skips the
        recomputation per origin when only statuses are needed."""
        with self.lock:
            v = build_verdict(self.store.corpus(), self.allegation, list(self.edges), list(self.figures), self.params,
                              absences=list(self.absences), sensitivity=sensitivity)
            v.rejected_evidence = self.rejected + v.rejected_evidence
            return v

    def unchallenged(self, verdict: Verdict | None = None) -> list[str]:
        """Supported sub-claims nobody has yet tried to refute."""
        verdict = verdict or self.verdict(sensitivity=False)
        cov = self.coverage()
        return [c.id for c in verdict.by_subclaim if c.status == SUPPORTED and not cov[c.id]["challenged"]]
