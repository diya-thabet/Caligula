"""One agent's tool loop on the Claude tool runner."""

from __future__ import annotations

from collections.abc import Callable

import anthropic

from caligula.llm.claude import FALLBACK_BETA

CONTEXT_BETA = "context-management-2025-06-27"
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 10}
MAX_PAUSE_RESTARTS = 3


def run_loop(
    client: anthropic.Anthropic,
    model: str,
    system: str,
    tools: list,
    brief: str,
    max_iterations: int,
    done: Callable[[], bool],
) -> str:
    """Runs until the agent stops calling tools. Returns the final stop reason."""
    messages: list = [{"role": "user", "content": brief}]
    stop_reason = "no_response"
    for _ in range(MAX_PAUSE_RESTARTS + 1):
        runner = client.beta.messages.tool_runner(
            model=model,
            max_tokens=16000,
            system=system,
            tools=tools,
            messages=messages,
            # Budgets and the wrap-up tools end the loop; this only guards against a runaway.
            max_iterations=max_iterations,
            betas=[FALLBACK_BETA, CONTEXT_BETA],
            fallbacks="default",
            # Old tool results can be cleared: everything that matters is in the workspace.
            context_management={"edits": [{"type": "clear_tool_uses_20250919"}]},
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
