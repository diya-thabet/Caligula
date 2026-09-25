"""Publication gate for findings that concern identifiable parties.

Nothing that points at wrongdoing goes out unless, in this order:
1. an editor approved the evidence review,
2. a lawyer approved the text (defamation, data protection, secrecy),
3. every named party was asked for comment and the reply window has passed
   (or they replied, and the reply is published alongside).
Corrections are appended, never overwritten. Each step is written to the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from caligula.ledger import Ledger

DEFAULT_REPLY_WINDOW = timedelta(days=7)


class Stage(StrEnum):
    DRAFT = "draft"
    EDITOR_APPROVED = "editor_approved"
    LEGAL_APPROVED = "legal_approved"
    PUBLISHED = "published"


class PublicationError(RuntimeError):
    pass


@dataclass
class ReplyRequest:
    party: str
    sent_at: datetime
    deadline: datetime
    reply: str | None = None


@dataclass
class Publication:
    case_id: str
    text: str
    named_parties: list[str]
    ledger: Ledger
    stage: Stage = Stage.DRAFT
    replies: dict[str, ReplyRequest] = field(default_factory=dict)
    corrections: list[tuple[datetime, str]] = field(default_factory=list)

    def _log(self, step: str, actor: str, **data) -> None:
        self.ledger.append("publication", actor, case_id=self.case_id, step=step, **data)

    def approve_editorial(self, editor: str) -> None:
        self._require(Stage.DRAFT)
        self.stage = Stage.EDITOR_APPROVED
        self._log("editor_approved", editor)

    def approve_legal(self, lawyer: str) -> None:
        self._require(Stage.EDITOR_APPROVED)
        self.stage = Stage.LEGAL_APPROVED
        self._log("legal_approved", lawyer)

    def request_reply(self, party: str, now: datetime | None = None, window: timedelta = DEFAULT_REPLY_WINDOW) -> None:
        now = now or datetime.now(UTC)
        self.replies[party] = ReplyRequest(party, now, now + window)
        self._log("reply_requested", "caligula", party=party, deadline=(now + window).isoformat())

    def record_reply(self, party: str, reply: str) -> None:
        self.replies[party].reply = reply
        self._log("reply_received", party, chars=len(reply))

    def blockers(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(UTC)
        out = []
        if self.stage not in (Stage.LEGAL_APPROVED, Stage.PUBLISHED):
            out.append(f"stage is {self.stage}; needs editor then legal approval")
        for party in self.named_parties:
            r = self.replies.get(party)
            if r is None:
                out.append(f"{party} has not been asked for comment")
            elif r.reply is None and now < r.deadline:
                out.append(f"{party} may reply until {r.deadline:%Y-%m-%d}")
        return out

    def publish(self, now: datetime | None = None) -> str:
        if blockers := self.blockers(now):
            raise PublicationError("; ".join(blockers))
        self.stage = Stage.PUBLISHED
        self._log("published", "caligula", chars=len(self.text))
        replies = [f"Response from {r.party}: {r.reply}" for r in self.replies.values() if r.reply]
        silent = [r.party for r in self.replies.values() if not r.reply]
        tail = replies + ([f"No response by the deadline from: {', '.join(silent)}."] if silent else [])
        return "\n\n".join([self.text, *tail])

    def correct(self, note: str, actor: str) -> None:
        self.corrections.append((datetime.now(UTC), note))
        self._log("correction", actor, note=note)

    def _require(self, stage: Stage) -> None:
        if self.stage != stage:
            raise PublicationError(f"expected stage {stage}, found {self.stage}")
