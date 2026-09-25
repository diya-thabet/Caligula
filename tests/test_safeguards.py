from datetime import UTC, datetime, timedelta

import pytest

from caligula.ingest.telegram import PrivateSourceError, channel_name, parse_preview
from caligula.ledger import Ledger
from caligula.policy import ClaimType, Decision, Intake, SubjectType, decide
from caligula.privacy import minimise
from caligula.publication import Publication, PublicationError
from caligula.redflags import Award, Company, Tender, screen_companies


def test_minimise_masks_identifiers_but_keeps_amounts_and_dates():
    text = ("Contact: a.b@mail.tn, +216 98 123 456 ou 22 333 444. CIN n° 01234567. "
            "RIB 12 345 1234567890123 45. Montant 120 000 000 TND le 21/07/2026, marché 2026-017.")
    masked, counts = minimise(text)
    assert counts == {"EMAIL": 1, "RIB": 1, "ID": 1, "PHONE": 2}
    for kept in ("120 000 000 TND", "21/07/2026", "2026-017"):
        assert kept in masked


def test_ledger_detects_tampering(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = Ledger(path)
    ledger.append("capture", "official", doc_id="a", raw_sha256="x" * 64)
    ledger.append("review", "reviewer", id="P1", status="accepted")
    ledger.append("publication", "editor", step="editor_approved")
    assert Ledger(path).verify() is None
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[1].replace("accepted", "disputed"), lines[2]]) + "\n")
    assert Ledger(path).verify() == 1


SAMPLE = """
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="newsroom_tn/101">
  <div class="tgme_widget_message_bubble">
    <div class="tgme_widget_message_forwarded_from accent_color">Forwarded from <a class="tgme_widget_message_forwarded_from_name" href="https://t.me/origin"><span dir="auto">Origin Channel</span></a></div>
    <div class="tgme_widget_message_text js-message_text" dir="auto">Le marché <b>2026-017</b> aurait été attribué<br/>sans appel d'offres.</div>
    <div class="tgme_widget_message_footer"><a class="tgme_widget_message_date" href="https://t.me/newsroom_tn/101"><time datetime="2026-08-02T09:15:00+00:00" class="time">09:15</time></a></div>
  </div></div></div>
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message js-widget_message" data-post="newsroom_tn/102">
  <div class="tgme_widget_message_bubble">
    <div class="tgme_widget_message_text js-message_text" dir="auto">Weather update &amp; traffic.</div>
    <a class="tgme_widget_message_date" href="#"><time datetime="2026-08-02T10:00:00+00:00">10:00</time></a>
  </div></div></div>
"""


def test_telegram_preview_parsing():
    first, second = parse_preview(SAMPLE)
    assert first.url == "https://t.me/newsroom_tn/101"
    assert first.text == "Le marché 2026-017 aurait été attribué\nsans appel d'offres."
    assert first.forwarded_from == "Origin Channel"
    assert first.posted_at == datetime(2026, 8, 2, 9, 15, tzinfo=UTC)
    assert (second.text, second.forwarded_from) == ("Weather update & traffic.", None)


@pytest.mark.parametrize("ref", ["https://t.me/+AbCdEf123", "https://t.me/joinchat/XYZ", "+AbCdEf"])
def test_private_telegram_refs_are_refused(ref):
    with pytest.raises(PrivateSourceError):
        channel_name(ref)


def test_public_channel_refs():
    assert channel_name("@newsroom_tn") == channel_name("https://t.me/s/newsroom_tn/55") == "newsroom_tn"


def intake(**kw):
    base = dict(claim_type=ClaimType.PROCUREMENT, subject_types=[SubjectType.PUBLIC_BODY, SubjectType.COMPANY],
                public_nexus=True, documented_act=True, relies_on_sensitive_traits=False,
                involves_leaked_or_classified_material=False, rationale="")
    return Intake(**{**base, **kw})


def test_policy_decisions():
    assert decide(intake()).decision == Decision.ACCEPT
    assert decide(intake(claim_type=ClaimType.ESPIONAGE_OR_STATE_SECURITY)).decision == Decision.REFUSE
    assert decide(intake(documented_act=False)).decision == Decision.REFUSE
    assert decide(intake(public_nexus=False)).decision == Decision.REFUSE
    assert decide(intake(relies_on_sensitive_traits=True)).decision == Decision.REFUSE
    review = decide(intake(claim_type=ClaimType.FINANCIAL_CRIME_INDICATORS,
                           subject_types=[SubjectType.COMPANY, SubjectType.PRIVATE_INDIVIDUAL]))
    assert review.decision == Decision.LEGAL_REVIEW and len(review.reasons) == 2
    assert decide(intake(involves_leaked_or_classified_material=True)).decision == Decision.LEGAL_REVIEW


def test_publication_requires_approvals_and_reply_window():
    ledger = Ledger()
    now = datetime(2026, 10, 1, tzinfo=UTC)
    pub = Publication("CASE-1", "Findings...", ["Company Z"], ledger)
    with pytest.raises(PublicationError, match="needs editor then legal approval"):
        pub.publish(now)
    with pytest.raises(PublicationError):
        pub.approve_legal("lawyer")  # editor first
    pub.approve_editorial("editor")
    pub.approve_legal("lawyer")
    with pytest.raises(PublicationError, match="not been asked for comment"):
        pub.publish(now)
    pub.request_reply("Company Z", now=now)
    with pytest.raises(PublicationError, match="may reply until 2026-10-08"):
        pub.publish(now + timedelta(days=3))
    text = pub.publish(now + timedelta(days=8))
    assert text.endswith("No response by the deadline from: Company Z.")
    assert [e.data["step"] for e in ledger.entries] == [
        "editor_approved", "legal_approved", "reply_requested", "published"]
    assert ledger.verify() is None


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
