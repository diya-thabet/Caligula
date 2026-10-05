"""Deterministic field extraction (amounts, dates, decree numbers).

The LLM may *propose* an amount, but only an amount this module can find in
the cited text is accepted.
"""

from __future__ import annotations

import re
from datetime import date

from caligula.domain.services.text import normalize_text

_NUM = r"\d{1,3}(?:[ .,]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?"
_AMOUNT = re.compile(
    rf"(?<![\d.,])(?P<num>{_NUM})\s*(?:(?P<scale>millions?|milliards?|mille)\s+(?:de\s+)?)?"
    r"(?P<unit>tnd|dt|dinars?|د\.ت|دينار|mdt|md)\b",
)
_SCALES = {"mille": 1e3, "million": 1e6, "millions": 1e6, "milliard": 1e9, "milliards": 1e9,
           "md": 1e6, "mdt": 1e6}  # MD / MDT = millions de dinars

_MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}
_DATE_NUMERIC = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_FR = re.compile(rf"\b(\d{{1,2}})(?:er)?\s+({'|'.join(_MONTHS_FR)})\s+(\d{{4}})\b")
_DECREE = re.compile(r"(?:décret|decret|arrêté|arrete)(?:[- ]loi)?\s+n°?\s*(\d{4}-\d+)")


def _parse_number(raw: str) -> float:
    raw = raw.replace(" ", "")
    # "120.000.000" / "120,000,000" are thousands separators; "1,5" is a decimal.
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", raw):
        return float(re.sub(r"[.,]", "", raw))
    if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d+", raw):
        return float(raw.replace(".", "").replace(",", "."))
    return float(raw.replace(",", "."))


def extract_amounts(text: str) -> list[float]:
    """Amounts in Tunisian dinars, scaled to units."""
    out = []
    for m in _AMOUNT.finditer(normalize_text(text)):
        value = _parse_number(m.group("num"))
        for key in (m.group("scale"), m.group("unit")):
            value *= _SCALES.get(key, 1)
        out.append(value)
    return out


def extract_dates(text: str) -> list[date]:
    norm = normalize_text(text)
    found: list[date] = []
    for m in _DATE_ISO.finditer(norm):
        found.append(_safe_date(int(m[1]), int(m[2]), int(m[3])))
    for m in _DATE_NUMERIC.finditer(norm):
        found.append(_safe_date(int(m[3]), int(m[2]), int(m[1])))
    for m in _DATE_FR.finditer(norm):
        found.append(_safe_date(int(m[3]), _MONTHS_FR[m[2]], int(m[1])))
    return [d for d in found if d is not None]


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def extract_decrees(text: str) -> list[str]:
    return _DECREE.findall(normalize_text(text))


def extract_fields(text: str) -> dict[str, list[str]]:
    """All fields as comparable strings, used by the retcon diff."""
    return {
        "amount_tnd": [f"{a:.0f}" for a in extract_amounts(text)],
        "date": [d.isoformat() for d in extract_dates(text)],
        "decree": extract_decrees(text),
    }
