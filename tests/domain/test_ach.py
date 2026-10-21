from caligula.domain.model.claims import Allegation, Hypothesis, HypothesisKind, SubClaim
from caligula.domain.model.evidence import Relation
from caligula.domain.model.verdict import WeighedEvidence
from caligula.domain.services.ach import build_matrices, competing_groups, rate

H = HypothesisKind


def _case():
    claims = [SubClaim(id=c, statement=c) for c in ("C1", "C2", "C5", "C9", "C10")]
    hyps = [
        Hypothesis(id="H1", statement="production deficit", predicts={"C1": True, "C2": False}),
        Hypothesis(id="H2", statement="demand surge", predicts={"C1": True, "C2": True}),
        Hypothesis(id="H3", statement="rigged award", predicts={"C5": True, "C9": False, "C10": False},
                   kind=H.ALLEGATION),
        Hypothesis(id="H4", statement="lawful emergency", predicts={"C5": True, "C9": True}, kind=H.INNOCENT),
        Hypothesis(id="H5", statement="price shock", predicts={"C10": True}, kind=H.INNOCENT),
    ]
    return Allegation(id="A", text="t", subject="s", claim_type="procurement", subclaims=claims,
                      hypotheses=hyps, core_subclaims=["C5"])


def item(doc, claim, relation=Relation.SUPPORTS, weight=0.8):
    return WeighedEvidence(doc_id=doc, subclaim_id=claim, relation=relation, cluster=doc, weight=weight)


def test_hypotheses_compete_when_they_predict_the_same_sub_claims():
    groups = competing_groups(_case().hypotheses)
    assert [[h.id for h in g] for g in groups] == [["H1", "H2"], ["H3", "H4", "H5"]]


def test_rating_follows_the_prediction():
    h3 = _case().hypotheses[2]
    assert rate(h3, "C5", Relation.SUPPORTS) == "C"
    assert rate(h3, "C9", Relation.SUPPORTS) == "I"
    assert rate(h3, "C9", Relation.CONTRADICTS) == "C"
    assert rate(h3, "C1", Relation.SUPPORTS) == "N"


def test_least_evidence_against_ranks_first_and_shared_evidence_is_not_diagnostic():
    items = [
        item("outage", "C1"),
        item("stats", "C2", Relation.CONTRADICTS, 0.7),
        item("award", "C5", weight=0.75),  # fits a rigged award and a lawful emergency alike
        item("operator", "C9", weight=0.25),  # the operator invokes urgency (self-serving)
        item("audit", "C9", Relation.CONTRADICTS, 0.85),
        item("audit", "C1", Relation.QUALIFIES),  # conditions are not rated
    ]
    outage, award = build_matrices(_case(), items)

    assert outage.ranking == ["H1", "H2"] and outage.inconsistency == {"H1": 0.0, "H2": 0.7}
    assert [(r.subclaim_id, r.diagnostic) for r in outage.rows] == [("C1", False), ("C2", True)]

    assert award.inconsistency == {"H3": 0.25, "H4": 0.85, "H5": 0.0}
    assert award.ranking == ["H3", "H4"]
    assert award.untested == ["H5"]  # no evidence on a price shock: not "least contradicted"
    diagnostic = {(r.subclaim_id, tuple(r.doc_ids)): r.diagnostic for r in award.rows}
    assert diagnostic == {("C5", ("award",)): False, ("C9", ("operator",)): True, ("C9", ("audit",)): True}


def test_one_origin_is_one_row():
    rows = build_matrices(_case(), [item("jort", "C5"), item("news", "C5").model_copy(update={"cluster": "jort"})])[1].rows
    assert len(rows) == 1 and rows[0].doc_ids == ["jort", "news"]
