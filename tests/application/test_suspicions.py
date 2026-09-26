"""Suspicions: status from the evidence, and detection of scope creep."""

from caligula.application.investigation.suspicions import Suspicion, SuspicionStatus, resolve, unknown_entities
from caligula.domain.model.evidence import EvidenceEdge, Relation
from support import workspace

S = SuspicionStatus


def suspicion(i, subclaim, status=S.OPEN):
    return Suspicion(id=f"S{i}", statement="s", subclaim_id=subclaim, raised_by="reviewer", round=1,
                     confirm_by="c", refute_by="r", status=status)


def test_status_follows_the_sub_claim_as_code_scores_it():
    items = [suspicion(1, "C1"), suspicion(2, "C2"), suspicion(3, "C3"), suspicion(4, "C4", S.AWAITING_SCOPE),
             suspicion(5, "C5", S.CONFIRMED)]
    statuses = {"C1": "supported", "C2": "contradicted", "C3": "contested", "C4": "supported",
                "C5": "partially_supported"}
    changed = resolve(items, statuses, round_=2)
    assert [(s.id, s.status, s.resolved_round) for s in items] == [
        ("S1", "confirmed", 2), ("S2", "refuted", 2), ("S3", "open", None),
        ("S4", "awaiting_scope", None),  # not investigated until the scope is approved
        ("S5", "open", None),  # new evidence reopened it
    ]
    assert [s.id for s in changed] == ["S1", "S2", "S5"]
    assert resolve(items, statuses, round_=3) == []


def test_new_people_or_companies_are_detected(store):
    ws = workspace(store)
    known = ["Centrale de Rades-Fictive"]  # entities the planner listed
    # In the claim text, a party, a spelling variant, a planned entity: known. The last two are new.
    names = ["Société Zeta Travaux", "Steg", "Societe Zeta Travaux", "centrale Rades-Fictive",
             "Société Omega Conseil", "Karim Ben Fictif", ""]
    assert unknown_entities(names, ws.allegation, known) == ["Société Omega Conseil", "Karim Ben Fictif"]


def test_workspace_resolves_and_logs_changes(store):
    ws = workspace(store)
    ws.suspicions.append(suspicion(1, "C2"))  # C2, the demand surge, has no evidence yet
    assert ws.resolve_suspicions() == []
    for doc, quote in (("ins_peak", "+0,8 % par rapport à 2025"), ("weather", "Aucun épisode de chaleur exceptionnel")):
        ws.record(EvidenceEdge(doc_id=doc, subclaim_id="C2", relation=Relation.CONTRADICTS, quote=quote), "test")
    [s] = ws.resolve_suspicions()
    assert s.status == "refuted"
    assert [e.data["status"] for e in ws.ledger.entries if e.action == "suspicion_status"] == ["refuted"]
