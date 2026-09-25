"""Model ports: structured analysis calls, and agent tool loops.

The investigation workflow depends on these two interfaces only; which model
and SDK run behind them is an adapter's business.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from caligula.domain.model.claims import Allegation
from caligula.domain.model.documents import Document
from caligula.domain.model.evidence import EvidenceEdge, FinancialFigure
from caligula.domain.model.intake import Intake

if TYPE_CHECKING:
    from caligula.agent.plan import PlanDraft

Tool = Callable[..., str]


class ToolRefusal(Exception):
    """Raised by a tool to refuse a call; the message goes back to the agent as a tool error."""


class ClaimAnalyst(Protocol):
    """Single structured calls. Outputs are proposals that code validates."""

    def classify(self, text: str) -> Intake: ...

    def decompose(self, allegation_id: str, text: str) -> Allegation: ...

    def plan(self, allegation: Allegation) -> PlanDraft: ...

    def read(self, allegation: Allegation, doc: Document) -> tuple[list[EvidenceEdge], list[FinancialFigure]]: ...


class AgentRunner(Protocol):
    """Runs one agent: a model-driven loop over `tools` until it stops calling them.

    Tools are plain functions whose signature and docstring describe them; a
    tool refuses a call by raising `ToolRefusal`.
    """

    def run(
        self,
        system: str,
        tools: list[Tool],
        brief: str,
        max_iterations: int,
        done: Callable[[], bool],
        web_search: bool = False,
    ) -> str:
        """Returns the final stop reason."""
        ...
