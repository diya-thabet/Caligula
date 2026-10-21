"""A case's live event log, and the ledger that echoes its entries into it."""

import threading

from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.application.cases.events import EventLog, ObservedLedger


def test_events_are_numbered_and_read_after_the_last_one_seen():
    log = EventLog()
    log.append("status", {"status": "running"})
    log.append("tool", {"tool": "search_evidence"})
    assert [(e.seq, e.kind) for e in log.since(0)] == [(1, "status"), (2, "tool")]
    assert [e.seq for e in log.since(1)] == [2] and log.last.seq == 2


def test_a_reader_waits_for_the_next_event():
    log = EventLog()
    threading.Timer(0.05, lambda: log.append("phase", {"phase": "review"})).start()
    assert [e.kind for e in log.wait(0, timeout=2)] == ["phase"]
    assert log.wait(1, timeout=0.01) == []  # nothing new: returns empty after the timeout


def test_every_ledger_entry_is_also_an_audit_event():
    log, inner = EventLog(), JsonlLedger()
    ledger = ObservedLedger(inner, log)
    entry = ledger.append("sign_off", "Sonia", note="ok")
    assert ledger.entries == inner.entries == [entry] and ledger.head == entry.hash and ledger.verify() is None
    [event] = log.since(0)
    assert (event.kind, event.data) == ("audit", {"action": "sign_off", "actor": "Sonia", "data": {"note": "ok"}})
