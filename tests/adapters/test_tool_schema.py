from caligula.adapters.llm.tool_schema import call_tool, function_schema
from caligula.application.investigation.toolkit import build_tools
from caligula.application.investigation.workspace import AgentContext
from support import workspace


def tools(store):
    ws = workspace(store)
    return ws, {t.__name__: t for t in build_tools(ws, AgentContext(name="investigator", budget=10),
                                                   ["record_evidence", "search_evidence", "assess"])}


def test_schema_from_signature_and_docstring(store):
    _, t = tools(store)
    s = function_schema(t["record_evidence"])
    assert s["name"] == "record_evidence"
    assert s["description"].startswith("Record that a document supports, contradicts or qualifies a sub-claim.")
    props = s["parameters"]["properties"]
    assert props["relation"]["enum"] == ["supports", "contradicts", "qualifies"]
    assert props["quote"]["description"] == "Exact text copied from the document."
    assert set(s["parameters"]["required"]) == {"doc_id", "subclaim_id", "relation", "quote", "rationale"}
    search = function_schema(t["search_evidence"])["parameters"]
    assert "k" not in search["required"] and search["properties"]["k"]["default"] == 8
    assert function_schema(t["assess"])["parameters"]["properties"] == {}


def test_calls_are_validated_and_refusals_returned_as_errors(store):
    ws, t = tools(store)
    out, err = call_tool(t["record_evidence"], '{"doc_id": "audit", "subclaim_id": "C5", "relation": "supports", '
                                               '"quote": "invented", "rationale": "r"}')
    assert err and out.startswith("Rejected: quote not found")
    out, err = call_tool(t["record_evidence"], '{"doc_id": "audit", "relation": "maybe"}')
    assert err and out.startswith("Invalid arguments")
    out, err = call_tool(t["search_evidence"], {"query": "gré à gré", "purpose": "support", "k": "2"})
    assert not err and out.count('"doc_id"') == 2  # "2" coerced to an int
    assert call_tool(t["record_evidence"], "not json")[1]
