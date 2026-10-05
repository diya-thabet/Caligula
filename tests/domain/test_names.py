import pytest

from caligula.domain.services.names import EntityKind, EntityResolver, match, similarity


@pytest.mark.parametrize("a, b", [
    ("Mohamed Ben Salah", "محمد بن صالح"),
    ("Mohamed Ben Salah", "SALAH Mohamed Ben"),
    ("Mohamed Ben Salah", "M'hamed Bensalah"),
    ("Société Zeta Travaux SARL", "Ste ZETA TRAVAUX"),
    ("Société Zeta Travaux", "شركة زيتا ترافو"),
])
def test_spelling_variants_match(a, b):
    assert similarity(a, b) >= 0.9


def test_different_people_do_not_match():
    assert similarity("Mohamed Ben Salah", "Ahmed Trabelsi") < 0.5


def test_people_are_never_auto_merged():
    m = match("Mohamed Ben Salah", "محمد بن صالح", EntityKind.PERSON)
    assert m.score == 1.0 and not m.same and m.needs_review


def test_resolver_merges_companies_and_proposes_people():
    r = EntityResolver()
    zeta, _ = r.add("Société Zeta Travaux", EntityKind.COMPANY)
    again, _ = r.add("STE ZETA TRAVAUX SARL", EntityKind.COMPANY)
    beta, _ = r.add("Beta Travaux", EntityKind.COMPANY)
    assert again is zeta and beta is not zeta
    r.add("Mohamed Ben Salah", EntityKind.PERSON)
    person, to_review = r.add("M'hamed Bensalah", EntityKind.PERSON)
    assert len(r.entities) == 4 and to_review[0][0].names == ["Mohamed Ben Salah"]
