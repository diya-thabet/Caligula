"""Registers where the absence of a record means something.

Absence is evidence only in proportion to how complete the searched source
is. A register that must list every public tender makes a missing tender
notice strong evidence; a web search that turns up no article proves little.
Completeness values are priors to be calibrated (and checked against the law
that governs each register) like every other weight.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Register:
    name: str
    completeness: float  # prior chance that the record would be listed if it existed
    specialist: str  # who searches it


REGISTERS: dict[str, Register] = {
    "tuneps": Register("TUNEPS: public procurement notices and awards", 0.8, "official"),
    "jort": Register("Journal Officiel (JORT): decrees, orders and official notices", 0.85, "official"),
    "rne": Register("Registre national des entreprises (companies, managers, beneficial owners)", 0.8, "official"),
    "funder_records": Register("Lenders' project documents and disbursement records", 0.7, "funders_audit"),
    "audit_reports": Register("Cour des comptes and inspection reports", 0.3, "funders_audit"),
    "official_site": Register("Website of the body concerned", 0.3, "official"),
    "news_archive": Register("News archives and press search", 0.15, "web_news"),
    "web_search": Register("General web search", 0.05, "web_news"),
}
