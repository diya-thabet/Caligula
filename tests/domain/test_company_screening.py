from datetime import UTC, datetime

from caligula.domain.model.procurement import Award, Company, Tender
from caligula.domain.services.red_flags import screen_companies


def test_company_screening():
    d = lambda s: datetime.fromisoformat(s).replace(tzinfo=UTC)
    companies = [
        Company(id="z", name="Zeta Travaux", capital_tnd=10_000, address="12, Rue X, Tunis",
                managers=["Mohamed Ben Salah"]),
        Company(id="y", name="Ypsilon SARL", address="12 rue x tunis", managers=["Mohamed Ben Salah"]),
        Company(id="o", name="Omega Energie", capital_tnd=5_000_000, address="Sousse"),
    ]
    awards = [Award(id="A1", buyer="B", supplier="Zeta Travaux", object="o", amount_tnd=120e6,
                    procedure="negotiated", award_date=d("2026-02-20"))]
    tenders = [Tender(id="T1", buyer="B", bidder_ids=["z", "y", "o"], award_id="A1", signatories=["M'hamed Bensalah"])]
    results = {s.subject_id: {f.code for f in s.flags} for s in screen_companies(companies, awards, tenders)}
    assert results["z"] == {"low_capital_vs_award", "bidders_share_people", "bidders_share_address", "official_name_match"}
    assert results["y"] == {"bidders_share_people", "bidders_share_address"}
    assert "o" not in results
