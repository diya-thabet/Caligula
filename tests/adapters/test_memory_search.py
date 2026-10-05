
from caligula.domain.model.documents import SourceKind
from conftest import add_doc


def test_memory_search_finds_exact_reference_and_paraphrase(store):
    add_doc(store, "award", "Avis d'attribution du marché n° 2026-017, procédure de gré à gré", kind=SourceKind.ARCHIVE)
    add_doc(store, "weather", "Relevé météorologique de juillet")
    add_doc(store, "news", "Le contrat 2026-017 aurait été conclu sans concurrence")
    hits = store.search("marché 2026-017 gré à gré")
    assert hits[0].doc_id == "award"
    assert "news" in [h.doc_id for h in hits[:2]]
    assert [h.doc_id for h in store.search("2026-017", kinds=[SourceKind.NEWS])] == ["news"]
    assert "2026-017" in hits[0].snippet
