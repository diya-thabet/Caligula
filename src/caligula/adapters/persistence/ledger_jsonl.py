"""Ledger kept in memory and, when a path is given, appended to a JSON-lines file."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from caligula.domain.services.ledger_chain import GENESIS, Entry, next_entry, verify_chain


class JsonlLedger:
    def __init__(self, path: Path | None = None):
        self.path = path
        self._entries: list[Entry] = []
        self._lock = threading.Lock()
        if path and path.exists():
            self._entries = [Entry(**json.loads(line)) for line in path.read_text().splitlines() if line]

    @property
    def entries(self) -> list[Entry]:
        return self._entries

    @property
    def head(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS

    def append(self, action: str, actor: str, **data) -> Entry:
        with self._lock:
            entry = next_entry(self._entries, datetime.now(UTC).isoformat(), action, actor, data)
            self._entries.append(entry)
            if self.path:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(entry), ensure_ascii=False, default=str) + "\n")
            return entry

    def verify(self) -> int | None:
        return verify_chain(self._entries)
