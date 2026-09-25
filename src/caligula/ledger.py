"""Tamper-evident evidence ledger.

Every capture, proposal, review decision and publication step is appended as
an entry whose hash covers the previous entry's hash. Editing or deleting any
past entry breaks every hash after it, so we can show an audience, a court or
a regulator that the record of *when we saw what* has not been rewritten.

The chain proves internal integrity. To prove the chain existed at a given
time to an outside party, periodically anchor the head hash with an RFC 3161
timestamping authority or publish it (see docs/legal.md).
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

GENESIS = "0" * 64


@dataclass(frozen=True)
class Entry:
    seq: int
    at: str
    action: str  # capture | proposal | review | publication | ...
    actor: str
    data: dict
    prev: str
    hash: str


def _digest(seq: int, at: str, action: str, actor: str, data: dict, prev: str) -> str:
    body = json.dumps([seq, at, action, actor, data, prev], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


class Ledger:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.entries: list[Entry] = []
        self._lock = threading.Lock()
        if path and path.exists():
            self.entries = [Entry(**json.loads(line)) for line in path.read_text().splitlines() if line]

    @property
    def head(self) -> str:
        return self.entries[-1].hash if self.entries else GENESIS

    def append(self, action: str, actor: str, **data) -> Entry:
        with self._lock:
            seq = len(self.entries)
            at = datetime.now(UTC).isoformat()
            entry = Entry(seq, at, action, actor, data, self.head, _digest(seq, at, action, actor, data, self.head))
            self.entries.append(entry)
            if self.path:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(entry), ensure_ascii=False, default=str) + "\n")
            return entry

    def verify(self) -> int | None:
        """Index of the first broken entry, or None if the chain is intact."""
        prev = GENESIS
        for i, e in enumerate(self.entries):
            if e.seq != i or e.prev != prev or e.hash != _digest(e.seq, e.at, e.action, e.actor, e.data, e.prev):
                return i
            prev = e.hash
        return None
