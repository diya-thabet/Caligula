"""Turn raw bytes into text: text layer first, OCR only when needed.

Much of the JORT archive is scanned. OCR runs Tesseract on pages rendered by
poppler, with French + English models by default (add `ara` for Arabic). OCR
text is marked as such, because an OCR misread of "120" as "720" must not
become a retcon finding: retcon flags on OCR text require human review.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from caligula.application.ports.sources import ExtractedText

OCR_LANGS = "fra+eng"
# Below this many characters per page, a PDF text layer is treated as missing.
MIN_CHARS_PER_PAGE = 40


def _run(args: list[str], stdin: bytes | None = None) -> str:
    return subprocess.run(args, input=stdin, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def _pdf_pages(raw: bytes) -> int:
    info = _run(["pdfinfo", "-"], raw)
    for line in info.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return 1


def extract_text(raw: bytes, filename: str = "") -> ExtractedText:
    if raw.startswith(b"%PDF"):
        return _from_pdf(raw)
    if Path(filename).suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
        return ExtractedText(ocr_image(raw), "ocr")
    return ExtractedText(raw.decode("utf-8", "replace"), "plain")


def _from_pdf(raw: bytes) -> ExtractedText:
    text = _run(["pdftotext", "-layout", "-enc", "UTF-8", "-", "-"], raw)
    if len(text.strip()) >= MIN_CHARS_PER_PAGE * _pdf_pages(raw):
        return ExtractedText(text, "pdf_text")
    return ExtractedText(ocr_pdf(raw), "ocr")


_LOOKALIKES = str.maketrans("OoQDIl|", "0000111")
# A 3-character group of digits and digit lookalikes that continues a number ("120 000 OOO").
_GROUP_AFTER_NUMBER = re.compile(r"(?<=\d[ .,])[0-9OoQDIl|]{3}(?![\w])")
# A token that mixes real digits with lookalikes ("1O0", "2O26").
_MIXED = re.compile(r"\b(?=[0-9OoIl]*\d)(?=[0-9OoIl]*[OoIl])[0-9OoIl]{2,}\b")


def repair_ocr_digits(text: str) -> str:
    """Fix letter/digit confusions inside numbers only. Words are left alone."""
    previous = None
    while previous != text:
        previous = text
        text = _GROUP_AFTER_NUMBER.sub(lambda m: m.group().translate(_LOOKALIKES), text)
        text = _MIXED.sub(lambda m: m.group().translate(_LOOKALIKES), text)
    return text


def ocr_available() -> bool:
    return all(shutil.which(t) for t in ("tesseract", "pdftoppm", "pdftotext", "pdfinfo"))


def ocr_image(raw: bytes, langs: str = OCR_LANGS) -> str:
    return repair_ocr_digits(_run(["tesseract", "stdin", "stdout", "-l", langs], raw))


def ocr_pdf(raw: bytes, langs: str = OCR_LANGS, dpi: int = 300) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "in.pdf"
        pdf.write_bytes(raw)
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(Path(tmp) / "page")], check=True)
        pages = sorted(Path(tmp).glob("page*.png"))
        return "\n\f".join(ocr_image(p.read_bytes(), langs) for p in pages)


class PopplerTesseractExtractor:
    """`TextExtractor` adapter: poppler for text layers, Tesseract for scans."""

    def __init__(self, langs: str = OCR_LANGS):
        self.langs = langs

    def extract(self, raw: bytes, filename: str = "") -> ExtractedText:
        return extract_text(raw, filename)
