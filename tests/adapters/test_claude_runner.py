"""The Claude AgentRunner adapter, against a fake SDK client."""

from types import SimpleNamespace

import pytest
from anthropic.lib.tools import ToolError

from caligula.adapters.llm.claude_runner import WEB_SEARCH, ClaudeAgentRunner, as_claude_tool
from caligula.application.ports.llm import ToolRefusal


def lookup(doc_id: str, offset: int = 0) -> str:
    """Read a document.

    Args:
        doc_id: Document id.
        offset: Character offset.
    """
    if doc_id == "missing":
        raise ToolRefusal("No document missing.")
    return f"{doc_id}@{offset}"


def test_plain_tool_is_bound_with_schema_and_refusals_become_tool_errors():
    tool = as_claude_tool(lookup)
    schema = tool.to_dict()
    assert schema["name"] == "lookup" and schema["input_schema"]["required"] == ["doc_id"]
    assert tool.call({"doc_id": "a", "offset": 3}) == "a@3"
    with pytest.raises(ToolError, match="No document missing"):
        tool.call({"doc_id": "missing"})


def test_runner_request_shape_and_pause_turn_resume():
    calls = []
    stops = iter(["pause_turn", "end_turn"])

    class FakeLoop:
        def __iter__(self):
            yield SimpleNamespace(content=[], stop_reason=next(stops))

        def generate_tool_call_response(self):
            return None

    def tool_runner(**kwargs):
        calls.append(kwargs)
        return FakeLoop()

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner)))
    stop = ClaudeAgentRunner(client).run("sys", [lookup], "brief", 10, lambda: False, web_search=True)

    assert stop == "end_turn" and len(calls) == 2  # paused turn resumed once
    first = calls[0]
    assert first["model"] == "claude-opus-5" and first["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in first["betas"]
    assert first["tools"][-1] == WEB_SEARCH and first["tools"][0].name == "lookup"
    assert first["system"] == "sys" and first["max_iterations"] == 10
    assert "output_config" not in first  # default effort ("high"), adaptive thinking on by default


def test_deep_roles_run_at_higher_effort():
    calls = []

    class FakeLoop:
        def __iter__(self):
            yield SimpleNamespace(content=[], stop_reason="end_turn")

        def generate_tool_call_response(self):
            return None

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(
        tool_runner=lambda **kw: calls.append(kw) or FakeLoop())))
    ClaudeAgentRunner(client).run("sys", [lookup], "brief", 10, lambda: False, deep=True)
    assert calls[0]["output_config"] == {"effort": "xhigh"}
