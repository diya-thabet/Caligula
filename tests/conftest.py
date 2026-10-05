from datetime import UTC, datetime
from pathlib import Path

import pytest

from caligula.adapters.persistence.blob_fs import FileBlobStorage
from caligula.adapters.persistence.memory import MemoryDocumentRepository
from caligula.application.evidence_store import EvidenceStore
from caligula.domain.model.documents import SourceKind

FIXTURE = Path(__file__).parent.parent / "fixtures" / "steg_synthetic"


@pytest.fixture
def blobs(tmp_path):
    return FileBlobStorage(tmp_path / "blobs")


@pytest.fixture
def store(blobs):
    return EvidenceStore(MemoryDocumentRepository(), blobs)


def add_doc(store, doc_id, text, *, url=None, kind=SourceKind.NEWS, day=1, **kw):
    url = url or f"https://example.test/{doc_id}"
    return store.add(
        doc_id=doc_id,
        raw=text.encode(),
        text=text,
        canonical_url=kw.pop("canonical_url", url),
        url=url,
        source_kind=kind,
        publisher=kw.pop("publisher", "test"),
        observed_at=datetime(2026, 1, day, tzinfo=UTC),
        **kw,
    )
