from caligula.domain.model.documents import SourceKind
from caligula.provenance import group_by_cluster, origin_clusters
from caligula.retcon import detect_retcons
from conftest import add_doc

URL = "https://jort.example/award"


def test_cosmetic_change_is_not_a_retcon(store):
    add_doc(store, "v1", "Montant : 120 000 000 TND.", canonical_url=URL, day=1)
    add_doc(store, "v2", "MONTANT :   120 000 000 TND.\n", canonical_url=URL, day=2)
    assert detect_retcons(store) == []


def test_reworded_text_without_field_change_is_not_flagged(store):
    add_doc(store, "v1", "Montant : 120 000 000 TND.", canonical_url=URL, day=1)
    add_doc(store, "v2", "Le montant retenu est de 120 000 000 TND.", canonical_url=URL, day=2)
    assert detect_retcons(store) == []


def test_amount_change_is_flagged_in_observation_order(store):
    # Inserted out of order: detection must sort by observed_at.
    add_doc(store, "live", "Montant : 80 000 000 TND, décret n° 2026-12.", canonical_url=URL, day=9)
    add_doc(store, "archive", "Montant : 120 000 000 TND, décret n° 2026-12.", canonical_url=URL, day=1)
    [flag] = detect_retcons(store)
    assert (flag.earlier_doc_id, flag.later_doc_id) == ("archive", "live")
    [change] = flag.changes
    assert (change.kind, change.removed, change.added) == ("amount_tnd", ["120000000"], ["80000000"])


def test_citation_chain_collapses_to_one_cluster(store):
    add_doc(store, "leak", "original leak", kind=SourceKind.ARCHIVE)
    add_doc(store, "a", "article a", cites=["leak"])
    add_doc(store, "b", "article b", cites=["a"])
    add_doc(store, "c", "article c", derived_from=["b"])
    add_doc(store, "copy", "Article C")  # same normalized text as c
    add_doc(store, "mirror", "independent record", kind=SourceKind.FOREIGN_MIRROR)
    groups = group_by_cluster(["a", "b", "c", "copy", "mirror"], origin_clusters(store))
    assert sorted(groups) == [["a", "b", "c", "copy"], ["mirror"]]


def test_versions_of_one_document_are_not_independent(store):
    add_doc(store, "v1", "120 TND", canonical_url=URL, day=1)
    add_doc(store, "v2", "80 TND", canonical_url=URL, day=2)
    clusters = origin_clusters(store)
    assert clusters["v1"] == clusters["v2"]
