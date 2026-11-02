import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from caligula.adapters.media.text_extraction import extract_text, ocr_available
from caligula.domain.services.extraction import extract_amounts


def test_plain_text_passthrough():
    assert extract_text(b"Montant : 5 TND", "a.txt").method == "plain"


@pytest.mark.skipif(not ocr_available(), reason="tesseract/poppler not installed")
def test_scanned_pdf_falls_back_to_ocr():
    img = Image.new("L", (1400, 200), 255)
    ImageDraw.Draw(img).text((20, 60), "Montant : 120 000 000 TND", fill=0, font=ImageFont.load_default(size=56))
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=150)  # image-only PDF, no text layer
    result = extract_text(buf.getvalue(), "scan.pdf")
    assert result.method == "ocr"
    assert extract_amounts(result.text) == [120_000_000]


def test_ocr_digit_repair_only_touches_numbers():
    from caligula.adapters.media.text_extraction import repair_ocr_digits

    assert repair_ocr_digits("Montant : 120 000 OOO TND le 2O26-O3-01") == "Montant : 120 000 000 TND le 2026-03-01"
    assert repair_ocr_digits("Office OIL, Oil and Lol") == "Office OIL, Oil and Lol"


def test_html_is_reduced_to_visible_text():
    raw = b"""<!doctype html>
    <html><head><meta charset="utf-8"><title>Award</title>
    <style>.x{color:red}</style><script>alert('x')</script></head>
    <body><nav>Accueil | About</nav>
    <article><h1>Market 2026-017</h1><p>The audit found <b>120 000 000 TND</b>.</p></article>
    <footer>(c) 2026</footer></body></html>"""
    result = extract_text(raw, "page.html")
    assert result.method == "html"
    assert "The audit found 120 000 000 TND ." in result.text or "The audit found 120 000 000 TND." in result.text
    for junk in ("alert", "color:red", "<b>", "<p>", "Accueil", "(c) 2026", "<html>"):
        assert junk not in result.text


def test_html_is_detected_from_content_when_the_name_has_no_extension():
    raw = b"<html><body><p>Bonjour</p></body></html>"
    result = extract_text(raw, "https://example.test/article")
    assert (result.method, result.text) == ("html", "Bonjour")


def test_html_is_detected_from_the_suffix_for_a_fragment():
    result = extract_text(b"<div><p>Fragment</p></div>", "fragment.htm")
    assert (result.method, result.text) == ("html", "Fragment")


def test_html_entities_and_non_utf8_charset_are_decoded():
    raw = ('<html><head><meta charset="iso-8859-1"></head><body>'
           '<p>Décret n° 2026-0412 &amp; 120 000 TND</p></body></html>').encode("iso-8859-1")
    result = extract_text(raw, "x")
    assert "Décret n° 2026-0412 & 120 000 TND" in result.text


def test_inline_tags_do_not_split_a_word_or_a_number():
    raw = b"<html><body><p>Montant : <b>120 000</b> 000 <i>TND</i></p></body></html>"
    assert "120 000 000 TND" in extract_text(raw, "x.html").text


def test_hidden_and_form_controls_are_dropped():
    raw = (b'<html><body><div hidden>secret</div><button>Go</button>'
           b'<p aria-hidden="true">hidden text</p><p>visible</p></body></html>')
    result = extract_text(raw, "x.html")
    assert "visible" in result.text
    for junk in ("secret", "Go", "hidden text"):
        assert junk not in result.text


def test_html_block_boundaries_become_line_breaks_but_inline_text_stays_together():
    raw = b"<html><body><p>First paragraph.</p><p>Second paragraph.</p></body></html>"
    assert extract_text(raw, "x.html").text == "First paragraph.\nSecond paragraph."


def test_html_keeps_arabic_text():
    raw = "<html><body><p>المبلغ ١٢٠ 000 دينار</p></body></html>".encode()
    assert "المبلغ ١٢٠ 000 دينار" in extract_text(raw, "x.html").text


def test_an_html_shell_with_no_visible_text_is_empty_not_markup():
    raw = b"<html><head><script>var x = 1</script></head><body></body></html>"
    result = extract_text(raw, "x.html")
    assert (result.method, result.text) == ("html", "")


def test_plain_text_with_angle_brackets_is_not_treated_as_html():
    result = extract_text(b"Montant : 5 TND < 10 TND", "a.txt")
    assert (result.method, result.text) == ("plain", "Montant : 5 TND < 10 TND")

