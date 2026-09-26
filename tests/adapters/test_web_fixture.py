"""The data the interface's tests run on, taken from the real API on the synthetic case.

web/src/test/steg.json holds each view the interface reads. The interface's
tests use it as their fake server, so if a view changes shape this test fails
first: regenerate with `UPDATE_GOLDEN=1 pytest tests/adapters/test_web_fixture.py`,
then run the interface's tests (`cd web && npm test`).
"""

import json
import os
import re
from pathlib import Path

from fastapi.testclient import TestClient

from caligula.adapters.api.app import create_app
from caligula.adapters.fixtures.case_directory import case_workspace
from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.application.cases.service import CaseService
from conftest import FIXTURE

OUT = Path(__file__).parents[2] / "web" / "src" / "test" / "steg.json"
REVIEW = ("The award was made by direct agreement [E13]. It was worth 120 million TND [E19]. "
          "The contract was signed by Karim Ben Salah [E13]. More collection is needed on the price.")
PATHS = ["/health", "/cases", "/approvals", "/cases/{id}", "/cases/{id}/analysis", "/cases/{id}/claims",
         "/cases/{id}/evidence", "/cases/{id}/documents", "/cases/{id}/documents/jort_award_v1",
         "/cases/{id}/documents/jort_award_v1/versions", "/cases/{id}/documents/jort_award_v2/versions",
         "/cases/{id}/timeline", "/cases/{id}/suspicions",
         "/cases/{id}/audit", "/cases/{id}/summary", "/cases/{id}/history", "/cases/{id}/plan",
         "/cases/{id}/events"]


def _stable(text: str) -> str:
    """Mask what changes between runs: timestamps and hashes of the ledger."""
    text = re.sub(r'"(at|created_at|last_activity)": "[^"]+"', r'"\1": "2026-09-26T10:00:00+00:00"', text)
    return re.sub(r'"(hash|head)": "[0-9a-f]{64}"', r'"\1": "' + "0" * 64 + '"', text)


def build(store) -> str:
    service = CaseService(None, new_ledger=lambda case_id: JsonlLedger())
    ws = case_workspace(FIXTURE, store)
    case = service.add_reviewed(ws, ws.allegation.text, by="replay", review=REVIEW)
    client = TestClient(create_app(service))
    views = {p: client.get("/api" + p.replace("{id}", case.id)).json() for p in PATHS}
    return _stable(json.dumps({"case_id": case.id, "views": views}, ensure_ascii=False, indent=1, sort_keys=True))


def test_the_interface_fixture_matches_the_api(store):
    data = build(store) + "\n"
    if os.environ.get("UPDATE_GOLDEN"):
        OUT.write_text(data, encoding="utf-8")
    assert OUT.read_text(encoding="utf-8") == data, "the API changed: regenerate web/src/test/steg.json"
