import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from caligula.adapters.media.text_extraction import extract_text, ocr_available
from caligula.domain.services.extraction import extract_amounts


def test_plain_text_passthrough():
    assert extract_text("Montant : 5 TND".encode(), "a.txt").method == "plain"


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
