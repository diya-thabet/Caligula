"""Our own web search replaces the provider's built-in one when configured."""

from caligula.application.investigation.single_agent import InvestigatorAgent
from caligula.application.investigation.workspace import Connectors
from caligula.application.ports.sources import SearchResult
from support import ScriptedAgentRunner, workspace


class FakeSearch:
    def __init__(self):
        self.queries = []

    def search(self, query, k=8, language=None):
        self.queries.append((query, language))
        return [SearchResult("https://news.example/steg", "STEG", "coupure du 21/07")]


def run(ws, web_search=True, search=True):
    record, calls = [], []
    script = [("search_web", {"query": "coupure STEG décret urgence", "purpose": "challenge",
                              "subclaim_id": "C5", "language": "fr"})] if search else []
    InvestigatorAgent(ScriptedAgentRunner(lambda s, b: (script, record), calls), web_search=web_search).run(ws)
    return record, calls[0]


def test_search_connector_gives_agents_a_search_tool_instead_of_native_search(store):
    search = FakeSearch()
    ws = workspace(store, connectors=Connectors(search=search))
    record, call = run(ws)
    assert call["web_search"] is False  # the provider's built-in search is not requested
    assert "search_web" in [t.__name__ for t in call["tools"]]
    assert '"url": "https://news.example/steg"' in record[0][2]
    assert search.queries == [("coupure STEG décret urgence", "fr")]
    assert ws.coverage()["C5"]["challenged"]  # a challenge search counts as one


def test_without_connector_the_provider_search_is_requested(store):
    record, call = run(workspace(store), search=False)
    assert call["web_search"] is True and "search_web" not in [t.__name__ for t in call["tools"]]


def test_no_web_disables_both(store):
    record, call = run(workspace(store, connectors=Connectors(search=FakeSearch())), web_search=False, search=False)
    assert call["web_search"] is False and "search_web" not in [t.__name__ for t in call["tools"]]
