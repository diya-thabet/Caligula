"""Retcon detection: compare versions of the same logical document.

A raw-hash change alone is not a finding (re-rendering changes bytes). A
text-hash change is reported only when an extracted field (amount, date,
decree number) differs, so the flag says *what* was rewritten.
"""

from __future__ import annotations

from collections import Counter

from caligula.domain.model.documents import Document
from caligula.domain.model.verdict import FieldChange, RetconFlag
from caligula.extract import extract_fields
from caligula.store import EvidenceStore


def diff_fields(earlier: Document, later: Document) -> list[FieldChange]:
    before, after = extract_fields(earlier.text), extract_fields(later.text)
    changes = []
    for kind in before:
        b, a = Counter(before[kind]), Counter(after[kind])
        removed, added = sorted((b - a).elements()), sorted((a - b).elements())
        if removed or added:
            changes.append(FieldChange(kind=kind, removed=removed, added=added))
    return changes


def detect_retcons(store: EvidenceStore) -> list[RetconFlag]:
    flags = []
    for url in store.canonical_urls():
        versions = store.versions(url)
        for earlier, later in zip(versions, versions[1:]):
            if earlier.text_sha256 == later.text_sha256:
                continue
            changes = diff_fields(earlier, later)
            if changes:
                flags.append(
                    RetconFlag(
                        canonical_url=url,
                        earlier_doc_id=earlier.id,
                        later_doc_id=later.id,
                        earlier_observed_at=earlier.observed_at,
                        later_observed_at=later.observed_at,
                        changes=changes,
                        needs_review="ocr" in (earlier.extraction, later.extraction),
                    )
                )
    return flags
