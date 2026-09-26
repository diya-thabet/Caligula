"""`ClaimAnalyst` and `AgentRunner` on any OpenAI-compatible chat API.

One adapter covers hosted providers (OpenAI, Mistral, Groq, DeepSeek,
OpenRouter, Together...) and self-hosted open models (vLLM, Ollama,
llama.cpp server): they all accept `POST {base_url}/chat/completions` with
tools and JSON-schema outputs. Self-hosting keeps case data on your own
servers, which matters for personal data (see docs/legal.md).

Plain httpx, no provider SDK. Web search is not the provider's business here:
configure a `WebSearch` connector and agents get the `search_web` tool.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Literal

import httpx
from pydantic import ValidationError

from caligula.adapters.llm.analyst_base import RefusalError, StructuredAnalyst, T
from caligula.adapters.llm.tool_schema import call_tool, function_schema
from caligula.application.ports.llm import Tool

RETRY_STATUS = {429, 500, 502, 503, 504}
CLEARED = "[older tool result cleared; everything that counts is recorded in the workspace]"


class ChatClient:
    """Minimal client for `/chat/completions`, with retries on rate limits and server errors."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None, http: httpx.Client | None = None,
                 max_tokens: int = 8000, max_tokens_field: str = "max_tokens", retries: int = 2,
                 sleep: Callable[[float], None] = time.sleep):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = http or httpx.Client(timeout=300.0)
        self.max_tokens = {max_tokens_field: max_tokens}
        self.retries = retries
        self.sleep = sleep

    def complete(self, messages: list[dict], **params) -> dict:
        """The first choice of one completion: {"message": ..., "finish_reason": ...}."""
        body = {"model": self.model, "messages": messages, **self.max_tokens, **params}
        for attempt in range(self.retries + 1):
            resp = self.http.post(self.url, json=body, headers=self.headers)
            if resp.status_code in RETRY_STATUS and attempt < self.retries:
                self.sleep(2.0 * 2**attempt)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]
        raise RuntimeError("unreachable")


class OpenAICompatAnalyst(StructuredAnalyst):
    """Structured calls through `response_format`.

    `json_schema` (default) asks the server to follow the schema; `json_object`
    is for servers that only guarantee valid JSON: the schema then goes into
    the prompt. Either way the output is validated here, with one retry that
    shows the model its error.
    """

    def __init__(self, client: ChatClient, output_mode: Literal["json_schema", "json_object"] = "json_schema"):
        self.client = client
        self.output_mode = output_mode

    def _parse(self, system: str, prompt: str, schema: type[T]) -> T:
        json_schema = schema.model_json_schema()
        if self.output_mode == "json_schema":
            fmt = {"type": "json_schema",
                   "json_schema": {"name": schema.__name__, "schema": json_schema, "strict": False}}
        else:
            fmt = {"type": "json_object"}
            system += f"\n\nAnswer with one JSON object that follows this JSON schema:\n{json.dumps(json_schema)}"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        for attempt in range(2):
            choice = self.client.complete(messages, response_format=fmt)
            message = choice["message"]
            if message.get("refusal"):
                raise RefusalError(f"request declined: {message['refusal']}")
            if choice.get("finish_reason") == "length":
                raise RuntimeError("no parsable output (output truncated)")
            content = message.get("content") or ""
            try:
                return schema.model_validate_json(content)
            except ValidationError as exc:
                if attempt:
                    raise RuntimeError(f"no parsable output: {exc}") from exc
                messages += [{"role": "assistant", "content": content},
                             {"role": "user", "content": f"That output is invalid: {exc}. Answer again with "
                                                         "corrected JSON only."}]
        raise RuntimeError("unreachable")


class OpenAICompatRunner:
    """`AgentRunner`: the tool loop, run here rather than by a provider SDK.

    Old tool results are cleared from the context once there are more than
    `keep_tool_results` of them: every result that matters (documents,
    proposals, task outcomes) is already recorded in the workspace.
    """

    def __init__(self, client: ChatClient, keep_tool_results: int = 12, parallel_tool_calls: bool | None = None,
                 deep_params: dict | None = None):
        self.client = client
        # Extra request fields for deep roles, e.g. {"reasoning_effort": "high"}; servers differ, so opt-in.
        self.deep_params = deep_params or {}
        self.keep_tool_results = keep_tool_results
        self.parallel_tool_calls = parallel_tool_calls

    def run(self, system: str, tools: list[Tool], brief: str, max_iterations: int, done: Callable[[], bool],
            web_search: bool = False, deep: bool = False) -> str:
        if web_search:
            raise ValueError("OpenAI-compatible providers have no built-in web search here; "
                             "configure a WebSearch connector (agents then get search_web)")
        by_name = {t.__name__: t for t in tools}
        specs = [{"type": "function", "function": function_schema(t)} for t in tools]
        extra = {} if self.parallel_tool_calls is None else {"parallel_tool_calls": self.parallel_tool_calls}
        if deep:
            extra |= self.deep_params
        messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": brief}]
        for _ in range(max_iterations):
            self._clear_old_results(messages)
            choice = self.client.complete(messages, tools=specs, tool_choice="auto", **extra)
            message = choice["message"]
            calls = message.get("tool_calls") or []
            messages.append({"role": "assistant", "content": message.get("content"),
                             **({"tool_calls": calls} if calls else {})})
            if message.get("refusal"):
                return "refusal"
            if not calls:
                return choice.get("finish_reason") or "stop"
            for call in calls:
                fn = by_name.get(call["function"]["name"])
                output, is_error = (call_tool(fn, call["function"].get("arguments") or "{}") if fn
                                    else (f"Unknown tool {call['function']['name']}", True))
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": f"Error: {output}" if is_error else output})
            if done():
                return "done"
        return "max_iterations"

    def _clear_old_results(self, messages: list[dict]) -> None:
        results = [m for m in messages if m["role"] == "tool"]
        for m in results[: max(0, len(results) - self.keep_tool_results)]:
            m["content"] = CLEARED
