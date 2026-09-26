import pytest

from caligula.adapters.cli.models import check_web_search, models_from, parse_spec, search_from
from caligula.adapters.llm.claude_analyst import ClaudeAnalyst
from caligula.adapters.llm.claude_runner import ClaudeAgentRunner
from caligula.adapters.llm.openai_compat import OpenAICompatAnalyst, OpenAICompatRunner
from caligula.adapters.sources.web_search import BraveSearch, SearxngSearch
from caligula.application.investigation.team import InvestigationTeam


def test_specs():
    assert parse_spec("claude") == parse_spec("claude:")
    assert parse_spec("claude:claude-sonnet-5").model == "claude-sonnet-5"
    local = parse_spec("openai:qwen3:32b@http://localhost:11434/v1")
    assert (local.provider, local.model, local.base_url) == ("openai", "qwen3:32b", "http://localhost:11434/v1")
    for bad in ("openai", "gemini:x"):
        with pytest.raises(ValueError):
            parse_spec(bad)


def test_roles_default_to_one_model_and_can_be_mixed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    env = {"CALIGULA_LLM": "openai:open-model", "CALIGULA_BASE_URL": "http://llm.local/v1", "CALIGULA_API_KEY": "k"}
    m = models_from(None, reviewer="claude", env=env)
    assert isinstance(m.analyst, OpenAICompatAnalyst) and isinstance(m.collectors, OpenAICompatRunner)
    assert m.collectors.client.url == "http://llm.local/v1/chat/completions"
    assert m.collectors.client.headers == {"Authorization": "Bearer k"}
    assert isinstance(m.reviewer, ClaudeAgentRunner)
    assert isinstance(models_from(None, env={}).analyst, ClaudeAnalyst)  # default provider


def test_openai_agents_need_a_search_engine_for_web_search():
    m = models_from("openai:open-model", env={})
    with pytest.raises(SystemExit, match="--search"):
        check_web_search(m, None, web=True)
    check_web_search(m, None, web=False)
    check_web_search(m, search_from("searxng", {}), web=True)
    assert isinstance(search_from("brave", {"BRAVE_API_KEY": "b"}), BraveSearch)
    assert isinstance(search_from("searxng", {"CALIGULA_SEARXNG_URL": "http://s"}), SearxngSearch)
    with pytest.raises(ValueError):
        search_from("brave", {})


def test_team_reviewer_can_run_on_its_own_model():
    collectors, reviewer = object(), object()
    team = InvestigationTeam(runner=collectors, reviewer_runner=reviewer)
    assert team.runner is collectors and team.reviewer_runner is reviewer
    assert InvestigationTeam(runner=collectors).reviewer_runner is collectors
