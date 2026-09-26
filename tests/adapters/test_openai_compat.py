"""The OpenAI-compatible adapter against a scripted chat server (httpx mock)."""

import json

import httpx
import pytest

from caligula.adapters.llm.analyst_base import RefusalError
from caligula.adapters.llm.openai_compat import CLEARED, ChatClient, OpenAICompatAnalyst, OpenAICompatRunner
from caligula.application.investigation.single_agent import InvestigatorAgent
from caligula.domain.model.intake import Intake
from support import workspace

INTAKE = {"claim_type": "procurement", "subject_types": ["public_body", "company"], "public_nexus": True,
          "documented_act": True, "relies_on_sensitive_traits": False,
          "involves_leaked_or_classified_material": False, "rationale": "a public contract"}


def server(replies, statuses=()):
    """A chat server that answers each request with the next reply, recording what it received."""
    requests, statuses = [], list(statuses)

    def handler(request):
        requests.append(json.loads(request.content))
        if statuses:
            return httpx.Response(statuses.pop(0), json={"error": "busy"})
        message, finish = replies.pop(0)
        return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": finish}]})

    client = ChatClient("http://llm.local/v1/", "open-model", api_key="k", sleep=lambda s: None,
                        http=httpx.Client(transport=httpx.MockTransport(handler)))
    return client, requests


def call(i, name, **args):
    return {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def test_analyst_uses_json_schema_and_retries_once_on_invalid_output():
    client, requests = server([({"content": '{"claim_type": "procurement"}'}, "stop"),
                               ({"content": json.dumps(INTAKE)}, "stop")], statuses=[429])
    intake = OpenAICompatAnalyst(client).classify("Le marché 2026-017 a été attribué sans appel d'offres.")
    assert isinstance(intake, Intake) and intake.public_nexus
    first = requests[1]  # requests[0] was rate-limited and retried
    assert first["model"] == "open-model" and first["response_format"]["type"] == "json_schema"
    assert first["response_format"]["json_schema"]["name"] == "Intake"
    assert "That output is invalid" in requests[2]["messages"][-1]["content"]


def test_json_object_mode_puts_the_schema_in_the_prompt_and_refusals_raise():
    client, requests = server([({"content": json.dumps(INTAKE)}, "stop"), ({"refusal": "no"}, "stop")])
    analyst = OpenAICompatAnalyst(client, output_mode="json_object")
    analyst.classify("x")
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert '"public_nexus"' in requests[0]["messages"][0]["content"]
    with pytest.raises(RefusalError):
        analyst.classify("y")


def test_runner_drives_the_real_tools_until_the_agent_finishes(store):
    ws = workspace(store)
    replies = [
        ({"content": None, "tool_calls": [
            call(1, "record_evidence", doc_id="audit", subclaim_id="C5", relation="supports", rationale="audit",
                 quote="n'est pas justifié par une situation d'urgence documentée"),
            call(2, "record_evidence", doc_id="audit", subclaim_id="C5", relation="supports", rationale="x",
                 quote="invented sentence"),
            call(3, "no_such_tool")]}, "tool_calls"),
        ({"content": None, "tool_calls": [call(4, "finish", summary="too early")]}, "tool_calls"),
        ({"content": None, "tool_calls": [
            call(5, "search_evidence", query="procédure d'urgence", purpose="challenge", subclaim_id="C5"),
            call(6, "finish", summary="Audit [audit].")]}, "tool_calls"),
    ]
    client, requests = server(replies)
    result = InvestigatorAgent(OpenAICompatRunner(client), web_search=False).run(ws)

    assert result.stop_reason == "done" and ws.summary == "Audit [audit]."
    assert [e.doc_id for e in ws.edges] == ["audit"]
    tools = {t["function"]["name"] for t in requests[0]["tools"]}
    assert {"record_evidence", "finish", "assess"} <= tools
    results = [m["content"] for m in requests[1]["messages"] if m["role"] == "tool"]
    assert results[0] == "Accepted as evidence E1." and results[1].startswith("Error: Rejected: quote not found")
    assert results[2] == "Error: Unknown tool no_such_tool"
    # The code-enforced challenge phase works the same with any provider.
    assert "Error: Not finished" in [m["content"] for m in requests[2]["messages"] if m["role"] == "tool"][-1]


def test_runner_clears_old_tool_results_and_refuses_native_web_search(store):
    ws = workspace(store)
    replies = [({"content": None, "tool_calls": [call(i, "assess")]}, "tool_calls") for i in range(3)]
    replies.append(({"content": "done"}, "stop"))
    client, requests = server(replies)
    runner = OpenAICompatRunner(client, keep_tool_results=1)
    stop = InvestigatorAgent(runner, web_search=False).run(ws).stop_reason
    assert stop == "stop"
    last = [m["content"] for m in requests[-1]["messages"] if m["role"] == "tool"]
    assert last[:2] == [CLEARED, CLEARED] and last[2] != CLEARED
    with pytest.raises(ValueError, match="configure a WebSearch connector"):
        runner.run("s", [], "b", 5, lambda: False, web_search=True)


def test_deep_parameters_are_sent_only_for_deep_roles(store):
    replies = [({"content": "ok"}, "stop"), ({"content": "ok"}, "stop")]
    client, requests = server(replies)
    runner = OpenAICompatRunner(client, deep_params={"reasoning_effort": "high"})
    runner.run("s", [], "b", 3, lambda: False)
    runner.run("s", [], "b", 3, lambda: False, deep=True)
    assert "reasoning_effort" not in requests[0] and requests[1]["reasoning_effort"] == "high"
