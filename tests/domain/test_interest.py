from caligula.domain.model.claims import Allegation, Bearing, Party, PartyRole, SubClaim
from caligula.domain.model.documents import SourceKind
from caligula.domain.model.evidence import EvidenceEdge, Relation
from caligula.domain.services.interest import Interest, interest, role_of
from caligula.domain.services.verdict import build_verdict
from conftest import add_doc

PARTIES = [
    Party(name="STEG", role=PartyRole.ACCUSED, aliases=["Société tunisienne de l'électricité et du gaz"]),
    Party(name="Parti Fictif", role=PartyRole.COMPLAINANT),
]


def test_publisher_matches_party_on_whole_words_and_ignores_accents():
    assert role_of("STEG - Direction de la communication", PARTIES) == PartyRole.ACCUSED
    assert role_of("Societe Tunisienne de l'Electricite et du Gaz", PARTIES) == PartyRole.ACCUSED
    assert role_of("parti fictif (communiqué)", PARTIES) == PartyRole.COMPLAINANT
    assert role_of("STEGMA Industries", PARTIES) is None
    assert role_of("Cour des comptes", PARTIES) is None


def test_interest_follows_who_gains():
    accused, complainant = PartyRole.ACCUSED, PartyRole.COMPLAINANT
    # The accused conceding an incriminating fact, or denying an exculpating one.
    assert interest(accused, Bearing.AGAINST, Relation.SUPPORTS) == Interest.AGAINST_INTEREST
    assert interest(accused, Bearing.FOR, Relation.CONTRADICTS) == Interest.AGAINST_INTEREST
    # The accused denying, justifying or qualifying.
    assert interest(accused, Bearing.AGAINST, Relation.CONTRADICTS) == Interest.SELF_SERVING
    assert interest(accused, Bearing.FOR, Relation.SUPPORTS) == Interest.SELF_SERVING
    assert interest(accused, Bearing.AGAINST, Relation.QUALIFIES) == Interest.SELF_SERVING
    # The complainant is the mirror image.
    assert interest(complainant, Bearing.AGAINST, Relation.SUPPORTS) == Interest.SELF_SERVING
    assert interest(complainant, Bearing.AGAINST, Relation.CONTRADICTS) == Interest.AGAINST_INTEREST
    # Neutral sources and context sub-claims carry no interest.
    assert interest(None, Bearing.AGAINST, Relation.SUPPORTS) == Interest.NONE
    assert interest(accused, Bearing.NEUTRAL, Relation.SUPPORTS) == Interest.NONE


def _case():
    return Allegation(
        id="A", text="t", subject="s", claim_type="procurement",
        subclaims=[SubClaim(id="C1", statement="no tender was published"),
                   SubClaim(id="C2", statement="an emergency justified the direct award", bearing=Bearing.FOR)],
        hypotheses=[], core_subclaims=["C1"], parties=PARTIES,
    )


def _edge(doc, claim, quote, rel):
    return EvidenceEdge(doc_id=doc, subclaim_id=claim, relation=rel, quote=quote)


def test_self_serving_statement_weighs_less_and_admission_more(store):
    add_doc(store, "denial", "un appel d'offres a bien été publié", kind=SourceKind.OFFICIAL_LIVE, publisher="STEG")
    add_doc(store, "admission", "aucun appel d'offres n'a été publié", kind=SourceKind.SOCIAL, publisher="STEG")
    add_doc(store, "excuse", "la procédure d'urgence s'imposait", kind=SourceKind.OFFICIAL_LIVE, publisher="STEG")
    add_doc(store, "rival", "aucun appel d'offres, dénonce le parti", kind=SourceKind.NEWS, publisher="Parti Fictif")
    edges = [
        _edge("denial", "C1", "un appel d'offres a bien été publié", Relation.CONTRADICTS),
        _edge("admission", "C1", "aucun appel d'offres n'a été publié", Relation.SUPPORTS),
        _edge("excuse", "C2", "la procédure d'urgence s'imposait", Relation.SUPPORTS),
        _edge("rival", "C1", "aucun appel d'offres", Relation.SUPPORTS),
    ]
    v = build_verdict(store.corpus(), _case(), edges, [])
    by_doc = {w.doc_id: w for w in v.weighed}
    assert (by_doc["denial"].interest, by_doc["denial"].weight) == ("self_serving", 0.25)
    assert (by_doc["admission"].interest, by_doc["admission"].weight) == ("against_interest", 0.8)
    assert (by_doc["excuse"].interest, by_doc["excuse"].weight) == ("self_serving", 0.25)
    assert (by_doc["rival"].interest, by_doc["rival"].weight) == ("self_serving", 0.175)
    c2 = v.by_subclaim[1]
    assert c2.support == 0.25 and c2.status == "partially_supported"
