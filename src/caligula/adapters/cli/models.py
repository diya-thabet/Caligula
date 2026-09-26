"""Which model runs each role, from CLI flags or environment variables.

A model is given as a spec:

    claude                         Claude API, default model (ANTHROPIC_API_KEY)
    claude:MODEL                   a given Claude model
    openai:MODEL                   any OpenAI-compatible API at CALIGULA_BASE_URL
                                   (default https://api.openai.com/v1), key in CALIGULA_API_KEY
    openai:MODEL@BASE_URL          the same at another address, e.g. a local server:
                                   openai:qwen3:32b@http://localhost:11434/v1 (Ollama)

Roles: the analyst (intake, decomposition, plan), the collectors (source
specialists or the single investigator) and the reviewer. Each defaults to
`--llm` (or CALIGULA_LLM, else "claude"): a strong model can review while a
cheaper or local one collects.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from caligula.application.ports.llm import AgentRunner, ClaimAnalyst
from caligula.application.ports.sources import WebSearch

DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class ModelSpec:
    provider: Literal["claude", "openai"]
    model: str | None = None
    base_url: str | None = None


def parse_spec(text: str) -> ModelSpec:
    provider, _, rest = text.strip().partition(":")
    if provider == "claude":
        return ModelSpec("claude", rest or None)
    if provider == "openai":
        model, _, base_url = rest.partition("@")
        if not model:
            raise ValueError("openai specs need a model: openai:MODEL or openai:MODEL@BASE_URL")
        return ModelSpec("openai", model, base_url or None)
    raise ValueError(f"unknown model provider {provider!r}: use claude[:MODEL] or openai:MODEL[@BASE_URL]")


def _chat_client(spec: ModelSpec, env: Mapping[str, str]):
    from caligula.adapters.llm.openai_compat import ChatClient

    return ChatClient(spec.base_url or env.get("CALIGULA_BASE_URL", DEFAULT_BASE_URL), spec.model,
                      api_key=env.get("CALIGULA_API_KEY"),
                      max_tokens_field=env.get("CALIGULA_MAX_TOKENS_FIELD", "max_tokens"))


def analyst_for(spec: ModelSpec, env: Mapping[str, str] = os.environ) -> ClaimAnalyst:
    if spec.provider == "claude":
        from caligula.adapters.llm.claude_analyst import MODEL, ClaudeAnalyst

        return ClaudeAnalyst(model=spec.model or MODEL)
    from caligula.adapters.llm.openai_compat import OpenAICompatAnalyst

    return OpenAICompatAnalyst(_chat_client(spec, env), output_mode=env.get("CALIGULA_OUTPUT_MODE", "json_schema"))


def runner_for(spec: ModelSpec, env: Mapping[str, str] = os.environ) -> AgentRunner:
    if spec.provider == "claude":
        from caligula.adapters.llm.claude_analyst import MODEL
        from caligula.adapters.llm.claude_runner import ClaudeAgentRunner

        return ClaudeAgentRunner(model=spec.model or MODEL)
    from caligula.adapters.llm.openai_compat import OpenAICompatRunner

    effort = env.get("CALIGULA_REASONING_EFFORT")  # for servers that accept reasoning_effort
    return OpenAICompatRunner(_chat_client(spec, env), deep_params={"reasoning_effort": effort} if effort else None)


def search_from(name: str | None, env: Mapping[str, str] = os.environ) -> WebSearch | None:
    """`searxng` (CALIGULA_SEARXNG_URL), `brave` (BRAVE_API_KEY), or None."""
    from caligula.adapters.sources.web_search import BraveSearch, SearxngSearch

    if not name:
        return None
    if name == "searxng":
        return SearxngSearch(env.get("CALIGULA_SEARXNG_URL", "http://localhost:8888"))
    if name == "brave":
        if not env.get("BRAVE_API_KEY"):
            raise ValueError("--search brave needs BRAVE_API_KEY")
        return BraveSearch(env["BRAVE_API_KEY"])
    raise ValueError(f"unknown search engine {name!r}: use searxng or brave")


@dataclass(frozen=True)
class Models:
    analyst: ClaimAnalyst
    collectors: AgentRunner
    reviewer: AgentRunner
    specs: dict[str, ModelSpec]


def models_from(default: str | None, analyst: str | None = None, collectors: str | None = None,
                reviewer: str | None = None, env: Mapping[str, str] = os.environ) -> Models:
    base = default or env.get("CALIGULA_LLM", "claude")
    specs = {role: parse_spec(given or base)
             for role, given in (("analyst", analyst), ("collectors", collectors), ("reviewer", reviewer))}
    return Models(analyst_for(specs["analyst"], env), runner_for(specs["collectors"], env),
                  runner_for(specs["reviewer"], env), specs)


def check_web_search(models: Models, search: WebSearch | None, web: bool) -> None:
    """OpenAI-compatible agents have no built-in search: they need a search connector (or --no-web)."""
    agents = [models.specs["collectors"], models.specs["reviewer"]]
    if web and search is None and any(s.provider == "openai" for s in agents):
        raise SystemExit("OpenAI-compatible agents need a search engine for web search: "
                         "pass --search searxng|brave, or --no-web")
