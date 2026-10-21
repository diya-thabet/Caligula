"""Cases in PostgreSQL: a snapshot per case, last write wins.

A snapshot is a convenience copy, not the record of authority -- the ledger and the
documents are (see schema.sql). Nothing here is immutable except that a snapshot is
never silently half-written: the row is written whole, and a verdict stored here is
always recomputed from the corpus on restore rather than trusted.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

from caligula.application.cases.snapshot import CaseSnapshot

_COLUMNS = (
    "id, claim, mode, poc, created_by, created_at, updated_at, status, note, origin, round, "
    "added_by_code, intake, decision, allegation, plan, params, review, summary, verdict, "
    "attribution, result, workspace, status_history, sign_off"
)
_JSON = ("added_by_code", "intake", "decision", "allegation", "plan", "params", "verdict", "attribution",
         "result", "workspace", "status_history", "sign_off")


class PostgresCaseRepository:
    def __init__(self, connect: Callable[[], Any]):
        self.connect = connect
        self._lock = threading.RLock()

    def save(self, snapshot: CaseSnapshot) -> None:
        row = snapshot.to_row()
        cols = ", ".join(_COLUMNS.split(", "))
        marks = ", ".join(f"%({c})s" for c in _COLUMNS.split(", "))
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNS.split(", ") if c != "id")
        with self._lock:
            conn = self.connect()
            with conn.transaction():
                conn.execute(
                    f"INSERT INTO cases ({cols}) VALUES ({marks}) ON CONFLICT (id) DO UPDATE SET {updates}",
                    {**{k: v for k, v in row.items() if k not in _JSON},
                     **{k: json.dumps(v, ensure_ascii=False, default=str) for k, v in row.items() if k in _JSON}},
                )

    def list(self) -> list[CaseSnapshot]:
        """Every stored case, newest first -- what startup restores."""
        rows = self.connect().execute(f"SELECT {_COLUMNS} FROM cases ORDER BY created_at DESC").fetchall()
        return [CaseSnapshot.from_row(r) for r in rows]

    def get(self, case_id: str) -> CaseSnapshot | None:
        rows = self.connect().execute(f"SELECT {_COLUMNS} FROM cases WHERE id = %s", (case_id,)).fetchall()
        return CaseSnapshot.from_row(rows[0]) if rows else None

    def delete(self, case_id: str) -> None:
        """Not used by the application: a case is never deleted, only superseded."""
        raise NotImplementedError("cases are kept; supersede them instead of deleting")