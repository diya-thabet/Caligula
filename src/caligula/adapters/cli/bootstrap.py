"""Composition root: the only place that picks concrete adapters."""

from __future__ import annotations

from pathlib import Path

from caligula.adapters.persistence.blob_fs import FileBlobStorage
from caligula.adapters.persistence.memory import MemoryDocumentRepository
from caligula.application.evidence_store import EvidenceStore
from caligula.application.investigation.workspace import Connectors


def open_store(dsn: str | None, blobs_dir: Path) -> EvidenceStore:
    blobs = FileBlobStorage(blobs_dir)
    if not dsn:
        return EvidenceStore(MemoryDocumentRepository(), blobs)
    from caligula.adapters.persistence.postgres import PostgresDocumentRepository

    repository = PostgresDocumentRepository(dsn)
    repository.init_schema()
    return EvidenceStore(repository, blobs)


def memory_store(blobs_dir: Path) -> EvidenceStore:
    return EvidenceStore(MemoryDocumentRepository(), FileBlobStorage(blobs_dir))


def live_connectors() -> Connectors:
    from caligula.adapters.media.text_extraction import PopplerTesseractExtractor
    from caligula.adapters.sources.telegram import TelegramClient
    from caligula.adapters.sources.wayback import WaybackClient
    from caligula.adapters.sources.web import LiveFetcher
    from caligula.adapters.sources.worldbank import WorldBankClient

    return Connectors(wayback=WaybackClient(), live=LiveFetcher(), funders=WorldBankClient(),
                      telegram=TelegramClient(), extractor=PopplerTesseractExtractor())


def claude():
    """(analyst, agent runner) on the Claude API."""
    from caligula.adapters.llm.claude_analyst import ClaudeAnalyst
    from caligula.adapters.llm.claude_runner import ClaudeAgentRunner

    return ClaudeAnalyst(), ClaudeAgentRunner()
