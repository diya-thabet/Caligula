from datetime import UTC, datetime
from pathlib import Path

import pytest

from caligula.domain.model.documents import SourceKind
from caligula.store import BlobStore, MemoryEvidenceStore

FIXTURE = Path(__file__).parent.parent / "fixtures" / "steg_synthetic"


@pytest.fixture
def blobs(tmp_path):
    return BlobStore(tmp_path / "blobs")


@pytest.fixture
def store(blobs):
    return MemoryEvidenceStore(blobs)


def add_doc(store, doc_id, text, *, url=None, kind=SourceKind.NEWS, day=1, **kw):
    url = url or f"https://example.test/{doc_id}"
    return store.add(
        doc_id=doc_id,
        raw=text.encode(),
        text=text,
        canonical_url=kw.pop("canonical_url", url),
        url=url,
        source_kind=kind,
        publisher="test",
        observed_at=datetime(2026, 1, day, tzinfo=UTC),
        **kw,
    )
