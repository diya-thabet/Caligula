"""Composition root: the only place that picks concrete adapters."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from caligula.adapters.persistence.blob_fs import FileBlobStorage
from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.adapters.persistence.memory import MemoryDocumentRepository
from caligula.application.evidence_store import EvidenceStore
from caligula.application.investigation.workspace import Connectors
from caligula.application.ports.sources import WebSearch
from caligula.application.ports.storage import Ledger


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


def open_ledger_factory(dsn: str | None, ledgers_dir: Path | None, store: EvidenceStore | None,
                        kind: str = "auto") -> Callable[[str], Ledger]:
    """One ledger per case. PostgreSQL when there is a database and the kind is not
    "jsonl"; otherwise JSON-lines files, as before.

    The factory hands back the same object for the same case id: two ledgers over one
    chain would each number their entries from their own list and fork it.
    """
    repository = store.repository if store is not None else None
    use_postgres = bool(dsn) and kind != "jsonl" and hasattr(repository, "conn")
    if use_postgres:
        from caligula.adapters.persistence.ledger_postgres import PostgresLedger

        held: dict[str, Ledger] = {}

        def postgres_ledger(case_id: str) -> Ledger:
            if case_id not in held:
                held[case_id] = PostgresLedger(case_id, lambda: repository.conn)
            return held[case_id]

        return postgres_ledger

    directory = ledgers_dir or Path("ledgers")
    directory.mkdir(parents=True, exist_ok=True)

    def jsonl_ledger(case_id: str) -> Ledger:
        return JsonlLedger(directory / f"{case_id}.jsonl")

    return jsonl_ledger


def open_case_repository(store: EvidenceStore | None, kind: str = "auto"):
    """Durable case store, or None to run exactly as before (nothing written)."""
    repository = store.repository if store is not None else None
    if kind == "none" or not hasattr(repository, "conn"):
        return None
    from caligula.adapters.persistence.cases_pg import PostgresCaseRepository

    return PostgresCaseRepository(lambda: repository.conn)


def live_connectors(search: WebSearch | None = None) -> Connectors:
    from caligula.adapters.media.text_extraction import PopplerTesseractExtractor
    from caligula.adapters.sources.telegram import TelegramClient
    from caligula.adapters.sources.wayback import WaybackClient
    from caligula.adapters.sources.web import LiveFetcher
    from caligula.adapters.sources.worldbank import WorldBankClient

    return Connectors(wayback=WaybackClient(), live=LiveFetcher(), funders=WorldBankClient(),
                      telegram=TelegramClient(), extractor=PopplerTesseractExtractor(), search=search)
