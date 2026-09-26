"""What happens in a case, in order, for live views: status changes, phases,
tool calls and ledger entries. Readers ask for what came after the last event
they saw, and may wait for more.

The ledger stays the record of authority; this is its live echo, kept in memory.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from caligula.application.ports.storage import Ledger
from caligula.domain.services.ledger_chain import Entry


@dataclass(frozen=True)
class Event:
    seq: int
    at: datetime
    kind: str  # status | phase | tool | audit | error
    data: dict


class EventLog:
    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self._events: list[Event] = []
        self._changed = threading.Condition()
        self._clock = clock

    def append(self, kind: str, data: dict) -> Event:
        with self._changed:
            event = Event(len(self._events) + 1, self._clock(), kind, data)
            self._events.append(event)
            self._changed.notify_all()
            return event

    def since(self, after: int = 0) -> list[Event]:
        with self._changed:
            return self._events[after:]

    def wait(self, after: int, timeout: float) -> list[Event]:
        """Events after `after`, waiting up to `timeout` seconds for the first one."""
        with self._changed:
            self._changed.wait_for(lambda: len(self._events) > after, timeout)
            return self._events[after:]

    @property
    def last(self) -> Event | None:
        with self._changed:
            return self._events[-1] if self._events else None


class ObservedLedger:
    """A ledger whose every entry is also published as an "audit" event."""

    def __init__(self, inner: Ledger, events: EventLog):
        self.inner = inner
        self.events = events

    @property
    def entries(self) -> list[Entry]:
        return self.inner.entries

    @property
    def head(self) -> str:
        return self.inner.head

    def append(self, action: str, actor: str, **data) -> Entry:
        entry = self.inner.append(action, actor, **data)
        self.events.append("audit", {"action": action, "actor": actor, "data": data})
        return entry

    def verify(self) -> int | None:
        return self.inner.verify()
