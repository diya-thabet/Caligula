"""`caligula serve`: the case service it builds, without starting a server."""

import argparse

from fastapi.testclient import TestClient

from caligula.adapters.api.app import create_app
from caligula.adapters.cli import commands, main
from conftest import FIXTURE


def args(tmp_path, **kw):
    base = dict(db=None, blobs=tmp_path / "blobs", llm=None, analyst_llm=None, collector_llm=None, reviewer_llm=None,
                search=None, no_web=True, rounds=8, max_tool_calls=600, replay=[FIXTURE], ledgers=tmp_path / "ledgers",
                cors=[], web=None)
    return argparse.Namespace(**(base | kw))


def test_replayed_cases_are_served_without_a_model(tmp_path):
    service = commands.case_service(args(tmp_path))
    assert service.engine is None
    [case] = service.list()
    assert case.id == "STEG-2026-07-21-SYNTHETIC" and case.status == "in_review"
    body = TestClient(create_app(service)).get(f"/api/cases/{case.id}").json()
    assert body["assessment"]["verdict"] == "high_suspicion"


def test_with_a_model_the_service_can_open_cases(tmp_path):
    env_free = args(tmp_path, replay=[], llm="openai:local-model@http://localhost:1/v1")
    service = commands.case_service(env_free)
    assert service.engine is not None and service.list() == []
    ledger = service.new_ledger("C-1")
    ledger.append("case_opened", "a")
    assert (tmp_path / "ledgers" / "C-1.jsonl").exists()


def test_the_serve_command_is_wired(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(commands, "serve", lambda a: seen.setdefault("args", a) and 0)
    main.main(["serve", "--replay", str(FIXTURE), "--cors", "http://localhost:5173", "--port", "8123"])
    a = seen["args"]
    assert (a.port, a.cors, a.replay) == (8123, ["http://localhost:5173"], [FIXTURE])
