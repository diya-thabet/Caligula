"""`AgentRunner` adapter: one agent's tool loop on the Claude tool runner."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

import anthropic
from anthropic import beta_tool
from anthropic.lib.tools import ToolError

from caligula.adapters.llm.claude_analyst import FALLBACK_BETA, MODEL
from caligula.application.ports.llm import Tool, ToolRefusal

CONTEXT_BETA = "context-management-2025-06-27"
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 10}
MAX_PAUSE_RESTARTS = 3
# Claude Opus 5 thinks adaptively by default at effort "high"; deep roles run at "xhigh".
DEEP_EFFORT = "xhigh"


def as_claude_tool(fn: Tool):
    """Bind a plain tool function; its signature and docstring become the tool schema."""

    @wraps(fn)
    def call(**kwargs):
        try:
            return fn(**kwargs)
        except ToolRefusal as exc:
            raise ToolError(str(exc)) from exc

    return beta_tool(call)


class ClaudeAgentRunner:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL):
        self.client = client or anthropic.Anthropic()
        self.model = model

    def run(
        self,
        system: str,
        tools: list[Tool],
        brief: str,
        max_iterations: int,
        done: Callable[[], bool],
        web_search: bool = False,
        deep: bool = False,
    ) -> str:
        bound: list = [as_claude_tool(t) for t in tools] + ([WEB_SEARCH] if web_search else [])
        effort = {"output_config": {"effort": DEEP_EFFORT}} if deep else {}
        messages: list = [{"role": "user", "content": brief}]
        stop_reason = "no_response"
        for _ in range(MAX_PAUSE_RESTARTS + 1):
            runner = self.client.beta.messages.tool_runner(
                model=self.model,
                max_tokens=16000,
                system=system,
                tools=bound,
                messages=messages,
                # Budgets and the wrap-up tools end the loop; this only guards against a runaway.
                max_iterations=max_iterations,
                betas=[FALLBACK_BETA, CONTEXT_BETA],
                fallbacks="default",
                # Old tool results can be cleared: everything that matters is in the workspace.
                context_management={"edits": [{"type": "clear_tool_uses_20250919"}]},
                **effort,
            )
            last = None
            for message in runner:
                last = message
                messages.append({"role": "assistant", "content": message.content})
                tool_response = runner.generate_tool_call_response()
                if tool_response is not None:
                    messages.append(tool_response)
            stop_reason = last.stop_reason if last else "no_response"
            # A long server-side web search can pause the turn; resume it.
            if stop_reason != "pause_turn" or done():
                break
        return stop_reason
