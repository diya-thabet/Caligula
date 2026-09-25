"""Two hashes per document.

`raw_sha256` proves chain of custody for the exact bytes we hold. It changes on
any re-render (PDF metadata, HTML template), so it cannot detect a retcon on
its own. `text_sha256` is taken over normalized text: if it changes, the
*content* changed, and `retcon.py` then diffs the extracted fields.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Arabic-Indic (U+0660..) and Extended Arabic-Indic (U+06F0..) digits -> ASCII.
_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGITS |= {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_TATWEEL = "ـ"
_WS = re.compile(r"\s+")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DIGITS).replace(_TATWEEL, "")
    # Narrow/regular no-break spaces are used as thousands separators in French.
    text = text.replace(" ", " ").replace(" ", " ")
    return _WS.sub(" ", text).strip().lower()


def text_sha256(text: str) -> str:
    return sha256_bytes(normalize_text(text).encode("utf-8"))
