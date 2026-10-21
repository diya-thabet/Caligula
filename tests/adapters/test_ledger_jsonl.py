

from caligula.adapters.persistence.ledger_jsonl import JsonlLedger


def test_ledger_detects_tampering(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = JsonlLedger(path)
    ledger.append("capture", "official", doc_id="a", raw_sha256="x" * 64)
    ledger.append("review", "reviewer", id="P1", status="accepted")
    ledger.append("publication", "editor", step="editor_approved")
    assert JsonlLedger(path).verify() is None
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[1].replace("accepted", "disputed"), lines[2]]) + "\n")
    assert JsonlLedger(path).verify() == 1
