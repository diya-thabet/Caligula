"""The evidence ledger in PostgreSQL: the same chain as the JSON-lines ledger.

`at` is stored as text rather than timestamptz on purpose. It is one of the inputs
to the entry hash (see `domain/services/ledger_chain.py`), so a normalised
timestamp -- "T" folded to a space, an offset folded to UTC -- would recompute a
different hash on the way back and the chain would read as tampered.

Appends are serialised per case with an advisory lock and read the chain's tail
inside the transaction, so a second process writing the same case cannot fork it.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from caligula.domain.services.ledger_chain import GENESIS, Entry, entry_hash, verify_chain

_COLUMNS = "seq, at, action, actor, data, prev, hash"


class PostgresLedger:
    """`Ledger` port over `case_ledger`. One chain per case id."""

    def __init__(self, case_id: str, connect: Callable[[], Any],
                 clock: Callable[[], str] = lambda: datetime.now(UTC).isoformat()):
        self.case_id = case_id
        self.connect = connect
        self.clock = clock
        self._entries: list[Entry] = []
        self._lock = threading.RLock()
        self.reload()

    def reload(self) -> None:
        """Read the stored chain. Cheap: one indexed query."""
        rows = self.connect().execute(
            f"SELECT {_COLUMNS} FROM case_ledger WHERE case_id = %s ORDER BY seq", (self.case_id,)
        ).fetchall()
        with self._lock:
            self._entries = [Entry(r["seq"], r["at"], r["action"], r["actor"], r["data"], r["prev"], r["hash"])
                             for r in rows]

    @property
    def entries(self) -> list[Entry]:
        return self._entries

    @property
    def head(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS

    def append(self, action: str, actor: str, **data) -> Entry:
        with self._lock:
            conn = self.connect()
            with conn.transaction():
                # Serialise appends to this chain, in this process and any other.
                conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (self.case_id,))
                tail = conn.execute(
                    "SELECT seq, hash FROM case_ledger WHERE case_id = %s ORDER BY seq DESC LIMIT 1",
                    (self.case_id,),
                ).fetchone()
                seq, prev = (tail["seq"] + 1, tail["hash"]) if tail else (0, GENESIS)
                at = self.clock()
                entry = Entry(seq, at, action, actor, data, prev,
                              entry_hash(seq, at, action, actor, data, prev))
                conn.execute(
                    f"INSERT INTO case_ledger (case_id, {_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)",
                    (self.case_id, entry.seq, entry.at, entry.action, entry.actor,
                     json.dumps(data, ensure_ascii=False, default=str), entry.prev, entry.hash),
                )
            self._entries.append(entry)
            return entry

    def verify(self) -> int | None:
        return verify_chain(self._entries)