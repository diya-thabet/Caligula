"""`ClaimAnalyst` adapter on the Claude API (structured outputs).

Prompts and schemas are shared with the other providers (`analyst_base`).
"""

from __future__ import annotations

import anthropic

from caligula.adapters.llm.analyst_base import RefusalError, StructuredAnalyst, T

MODEL = "claude-opus-5"
# Route policy declines to Anthropic's recommended fallback model instead of failing the call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

__all__ = ["FALLBACK_BETA", "MODEL", "ClaudeAnalyst", "RefusalError"]


class ClaudeAnalyst(StructuredAnalyst):
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL):
        self.client = client or anthropic.Anthropic()
        self.model = model

    def _parse(self, system: str, prompt: str, schema: type[T]) -> T:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RefusalError(f"request declined: {response.stop_details}")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise RuntimeError(f"no parsable output (stop_reason={response.stop_reason})")
        return response.parsed_output
