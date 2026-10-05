from datetime import UTC, datetime, timedelta

import pytest

from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.application.usecases.publication import Publication, PublicationError


def test_publication_requires_approvals_and_reply_window():
    ledger = JsonlLedger()
    now = datetime(2026, 10, 1, tzinfo=UTC)
    pub = Publication("CASE-1", "Findings...", ["Company Z"], ledger)
    with pytest.raises(PublicationError, match="needs editor then legal approval"):
        pub.publish(now)
    with pytest.raises(PublicationError):
        pub.approve_legal("lawyer")  # editor first
    pub.approve_editorial("editor")
    pub.approve_legal("lawyer")
    with pytest.raises(PublicationError, match="not been asked for comment"):
        pub.publish(now)
    pub.request_reply("Company Z", now=now)
    with pytest.raises(PublicationError, match="may reply until 2026-10-08"):
        pub.publish(now + timedelta(days=3))
    text = pub.publish(now + timedelta(days=8))
    assert text.endswith("No response by the deadline from: Company Z.")
    assert [e.data["step"] for e in ledger.entries] == [
        "editor_approved", "legal_approved", "reply_requested", "published"]
    assert ledger.verify() is None
