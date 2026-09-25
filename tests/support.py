"""Helpers shared by application tests: a scripted AgentRunner and a workspace on the STEG fixture."""



from caligula.adapters.fixtures.case_directory import load_case
from caligula.adapters.persistence.ledger_jsonl import JsonlLedger
from caligula.application.investigation.workspace import Mode, Workspace
from caligula.application.ports.llm import ToolRefusal
from caligula.domain.model.claims import Allegation
from caligula.domain.services.innocent import ensure_innocent_explanations
from conftest import FIXTURE


def play(tools, script, record):
    """Plays scripted tool calls through the real tool functions, as a model would."""
    by_name = {t.__name__: t for t in tools}
    script = list(script)
    while script:
        name, args = script.pop(0)
        if name == "__expand__":  # decide the next calls from the live workspace state
            script[:0] = args()
            continue
        try:
            out, err = by_name[name](**args), False
        except ToolRefusal as exc:  # returned to the model as a tool error
            out, err = str(exc), True
        record.append((name, err, out))


class ScriptedAgentRunner:
    """Fake `AgentRunner`: `script_for(system, brief)` returns (script, record) for each agent run."""

    def __init__(self, script_for, calls=None):
        self.script_for = script_for
        self.calls = [] if calls is None else calls

    def run(self, system, tools, brief, max_iterations, done, web_search=False):
        self.calls.append({"system": system, "tools": tools, "brief": brief, "web_search": web_search})
        script, record = self.script_for(system, brief)
        play(tools, script, record)
        return "end_turn"


def workspace(store, mode=Mode.INVESTIGATE, **kw):
    """The synthetic case as `decompose_case` would hand it over: completed with the innocent explanations."""
    case = load_case(FIXTURE, store)
    allegation, _ = ensure_innocent_explanations(Allegation.model_validate(case["allegation"]))
    return Workspace(store=store, allegation=allegation, mode=mode, ledger=JsonlLedger(), **kw)
