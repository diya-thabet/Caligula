"""Hash-chain rules of the evidence ledger.

Every entry's hash covers the previous entry's hash. Editing or deleting any
past entry breaks every hash after it, so the record of *when we saw what*
cannot be rewritten without detection.

The chain proves internal integrity. To prove the chain existed at a given
time to an outside party, periodically anchor the head hash with an RFC 3161
timestamping authority or publish it (see docs/legal.md).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

GENESIS = "0" * 64


@dataclass(frozen=True)
class Entry:
    seq: int
    at: str  # ISO-8601 timestamp
    action: str  # capture | proposal | review | publication | ...
    actor: str
    data: dict
    prev: str
    hash: str


def entry_hash(seq: int, at: str, action: str, actor: str, data: dict, prev: str) -> str:
    body = json.dumps([seq, at, action, actor, data, prev], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def next_entry(chain: Sequence[Entry], at: str, action: str, actor: str, data: dict) -> Entry:
    seq = len(chain)
    prev = chain[-1].hash if chain else GENESIS
    return Entry(seq, at, action, actor, data, prev, entry_hash(seq, at, action, actor, data, prev))


def verify_chain(chain: Sequence[Entry]) -> int | None:
    """Index of the first broken entry, or None if the chain is intact."""
    prev = GENESIS
    for i, e in enumerate(chain):
        if e.seq != i or e.prev != prev or e.hash != entry_hash(e.seq, e.at, e.action, e.actor, e.data, e.prev):
            return i
        prev = e.hash
    return None
