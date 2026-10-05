

from caligula.domain.services.privacy import minimise


def test_minimise_masks_identifiers_but_keeps_amounts_and_dates():
    text = ("Contact: a.b@mail.tn, +216 98 123 456 ou 22 333 444. CIN n° 01234567. "
            "RIB 12 345 1234567890123 45. Montant 120 000 000 TND le 21/07/2026, marché 2026-017.")
    masked, counts = minimise(text)
    assert counts == {"EMAIL": 1, "RIB": 1, "ID": 1, "PHONE": 2}
    for kept in ("120 000 000 TND", "21/07/2026", "2026-017"):
        assert kept in masked
