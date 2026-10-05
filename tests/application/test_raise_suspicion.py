"""The reviewer's raise_suspicion tool: tested both ways, and within the legal scope."""

import pytest

from caligula.application.investigation.toolkit import MAX_SUSPICIONS_PER_ROUND, build_tools
from caligula.application.investigation.workspace import AgentContext
from caligula.application.ports.llm import ToolRefusal
from caligula.domain.model.intake import Decision, IntakeDecision
from support import assert_invariants, workspace

RETCON = "The 80M TND figure was entered after the audit to hide the original 120M TND award"


def raise_(ws, statement=RETCON, **kw):
    tool = {t.__name__: t for t in build_tools(ws, AgentContext(name="reviewer", budget=30), ["raise_suspicion"])}
    args = {"statement": statement, "confirm_by": "archived versions of the JORT page and the audit's date",
            "refute_by": "a published erratum explaining the change", "confirm_specialist": "official",
            "refute_specialist": "web_news"} | kw
    return tool["raise_suspicion"](**args)


def test_a_suspicion_becomes_a_sub_claim_tested_both_ways(store):
    ws = workspace(store)
    out = raise_(ws, entities=["STEG"])
    [s] = ws.suspicions
    assert out.startswith(f"S1 recorded, tested by {s.subclaim_id}")
    claim = next(c for c in ws.allegation.subclaims if c.id == s.subclaim_id)
    assert claim.statement == RETCON and claim.bearing == "against"
    h3 = next(h for h in ws.allegation.hypotheses if h.id == "H3")  # the allegation predicts it true
    assert h3.predicts[s.subclaim_id] is True
    confirm, refute = (next(t for t in ws.tasks if t.id == tid) for tid in s.task_ids)
    assert (confirm.specialist, confirm.purpose, confirm.round) == ("official", "support", 2)
    assert (refute.specialist, refute.purpose, refute.suspicion_id) == ("web_news", "challenge", "S1")
    assert [e.action for e in ws.ledger.entries][-4:] == ["suspicion", "subclaim", "task", "task"]
    assert_invariants(ws)


def test_an_existing_sub_claim_can_carry_the_suspicion(store):
    ws = workspace(store)
    raise_(ws, statement="No tender was ever published", subclaim_id="C5")
    assert ws.suspicions[0].subclaim_id == "C5" and len(ws.allegation.subclaims) == 12


def test_both_directions_and_limits_are_enforced(store):
    ws = workspace(store)
    with pytest.raises(ToolRefusal, match="confirm and what would refute"):
        raise_(ws, refute_by=" ")
    with pytest.raises(ToolRefusal, match="No sub-claim C77"):
        raise_(ws, subclaim_id="C77")
    raise_(ws)
    with pytest.raises(ToolRefusal, match="already recorded"):
        raise_(ws, statement=RETCON.upper())
    for i in range(MAX_SUSPICIONS_PER_ROUND - 1):
        raise_(ws, statement=f"suspicion {i}")
    with pytest.raises(ToolRefusal, match="At most"):
        raise_(ws, statement="one too many")


def _policy(decision):
    return lambda statement: IntakeDecision(decision, [f"policy says {decision}"])


def test_new_people_or_companies_go_through_the_legal_policy(store):
    ws = workspace(store, poc=False)
    ws.scope_policy = _policy(Decision.REFUSE)
    out = raise_(ws, statement="The director's cousin is a spy", entities=["Karim Ben Fictif"])
    assert "rejected by the legal policy" in out
    ws.scope_policy = _policy(Decision.LEGAL_REVIEW)
    out = raise_(ws, statement="Omega Conseil received subcontracts", entities=["Société Omega Conseil"])
    assert "waits for a lawyer" in out
    assert [s.status for s in ws.suspicions] == ["rejected", "awaiting_scope"]
    assert all(not s.task_ids and s.subclaim_id is None for s in ws.suspicions)  # nobody works on them
    ws.scope_policy = _policy(Decision.ACCEPT)
    raise_(ws, statement="Omega Conseil was paid by the contractor", entities=["Société Omega Conseil"])
    assert ws.suspicions[-1].status == "open" and len(ws.suspicions[-1].task_ids) == 2


def test_in_poc_mode_legal_review_proceeds_but_is_logged(store):
    ws = workspace(store)  # PoC by default, no policy available: treated as needing legal review
    raise_(ws, statement="Omega Conseil received subcontracts", entities=["Société Omega Conseil"])
    [s] = ws.suspicions
    assert s.status == "open" and s.note.startswith("PoC: wider scope not reviewed by a lawyer")
    assert any(e.action == "poc_unreviewed" and e.data["suspicion"] == "S1" for e in ws.ledger.entries)


def test_a_lawyer_approves_or_refuses_a_wider_scope(store):
    ws = workspace(store, poc=False)
    ws.scope_policy = _policy(Decision.LEGAL_REVIEW)
    raise_(ws, statement="Omega Conseil received subcontracts", entities=["Société Omega Conseil"],
           confirm_specialist="funders_audit", bearing="against")
    raise_(ws, statement="Delta SARL received subcontracts", entities=["Delta SARL"])
    approved = ws.decide_scope("S1", True, "Maître Fictive", note="public contract, documented payments")
    assert approved.status == "open" and approved.note.startswith("scope approved by Maître Fictive")
    confirm, refute = (next(t for t in ws.tasks if t.id == tid) for tid in approved.task_ids)
    assert (confirm.specialist, refute.specialist, confirm.created_by) == ("funders_audit", "web_news",
                                                                          "Maître Fictive")
    refused = ws.decide_scope("S2", False, "Maître Fictive")
    assert refused.status == "rejected" and not refused.task_ids
    assert [(e.action, e.actor) for e in ws.ledger.entries if e.action.startswith("legal_")] == [
        ("legal_approval", "Maître Fictive"), ("legal_refusal", "Maître Fictive")]
    with pytest.raises(ValueError):
        ws.decide_scope("S1", True, "Maître Fictive")  # already decided
    assert_invariants(ws)
