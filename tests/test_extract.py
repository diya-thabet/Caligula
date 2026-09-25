from datetime import date

from caligula.extract import extract_amounts, extract_dates, extract_decrees
from caligula.hashing import normalize_text, text_sha256


def test_normalize_folds_arabic_digits_tatweel_and_spacing():
    assert normalize_text("  ١٢٠ 000   دينـــار ") == "120 000 دينار"


def test_text_hash_ignores_whitespace_and_case():
    assert text_sha256("Montant :  120 TND") == text_sha256("montant : 120 tnd\n")


def test_amounts_in_french_and_arabic_notations():
    text = "montant de 120 000 000 TND, puis 1,5 millions de dinars, 80 MD, 3.200.000 DT et ٤٥٠ دينار"
    assert extract_amounts(text) == [120_000_000, 1_500_000, 80_000_000, 3_200_000, 450]


def test_numbers_without_currency_are_ignored():
    assert extract_amounts("pointe de 4 870 MW, 2 MDS de projets") == []


def test_dates_numeric_iso_and_french():
    found = extract_dates("le 21/07/2026, le 2026-03-01 et le 1er août 2026 ; pas le 31/02/2026")
    assert sorted(found) == [date(2026, 3, 1), date(2026, 7, 21), date(2026, 8, 1)]


def test_decree_numbers():
    assert extract_decrees("en application du Décret n° 2026-0412 et de l'arrêté n°2025-7") == [
        "2026-0412",
        "2025-7",
    ]


def test_year_before_amount_is_not_merged_into_it():
    assert extract_amounts("en 2025 120 000 TND") == [120_000]
