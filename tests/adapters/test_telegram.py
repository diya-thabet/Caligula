from datetime import UTC, datetime

import pytest

from caligula.adapters.sources.telegram import channel_name, parse_preview
from caligula.application.ports.sources import PrivateSourceError

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
