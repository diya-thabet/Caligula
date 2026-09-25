"""State of one investigation, owned by code, not by the model.

The agent can only change it through tools, and every write is validated on
the spot, so the model gets immediate feedback ("quote not found", "document
observed after the event") and can correct course within the loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from caligula.ingest.sources import LiveFetcher, WorldBankClient
from caligula.ingest.wayback import WaybackClient
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


@dataclass
class TraceEntry:
    step: int
    tool: str
    args: dict
    outcome: str


@dataclass
class Connectors:
    wayback: WaybackClient | None = None
    live: LiveFetcher | None = None
    funders: WorldBankClient | None = None


@dataclass
class Workspace:
    store: EvidenceStore
    allegation: Allegation
    mode: Mode
    connectors: Connectors = field(default_factory=Connectors)
    params: Params = DEFAULT_PARAMS
    edges: list[EvidenceEdge] = field(default_factory=list)
    figures: list[FinancialFigure] = field(default_factory=list)
    rejected: list[RejectedEvidence] = field(default_factory=list)
    trace: list[TraceEntry] = field(default_factory=list)
    searches: list[tuple[Purpose, str | None, str]] = field(default_factory=list)
    budget: int = 0
    summary: str | None = None

    def __post_init__(self):
        self.budget = self.budget or BUDGETS[self.mode]

    @property
    def finished(self) -> bool:
        return self.summary is not None

    def log(self, tool: str, args: dict, outcome: str) -> None:
        self.trace.append(TraceEntry(len(self.trace) + 1, tool, args, outcome))

    def record_edge(self, edge: EvidenceEdge) -> str | None:
        """Returns the rejection reason, or None if accepted."""
        kept, rejected = validate_edges(self.store, self.allegation, [edge])
        if kept and edge not in self.edges:
            self.edges.append(edge)
        self.rejected += rejected
        return rejected[0].reason if rejected else None

    def record_figure(self, figure: FinancialFigure) -> str | None:
        kept, rejected = validate_figures(self.store, [figure])
        if kept and figure not in self.figures:
            self.figures.append(figure)
        self.rejected += rejected
        return rejected[0].reason if rejected else None

    def verdict(self) -> Verdict:
        v = build_verdict(self.store, self.allegation, self.edges, self.figures, self.params)
        v.rejected_evidence = self.rejected + v.rejected_evidence
        return v

    def unchallenged(self, verdict: Verdict | None = None) -> list[str]:
        """Supported sub-claims nobody has yet tried to refute."""
        verdict = verdict or self.verdict()
        challenged = {sid for purpose, sid, _ in self.searches if purpose == Purpose.CHALLENGE}
        return [c.id for c in verdict.by_subclaim if c.status == SUPPORTED and c.id not in challenged]
