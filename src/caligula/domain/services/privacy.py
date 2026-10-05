"""Data minimisation for text that the agents read and that reports may quote.

Social posts, Telegram messages and contributor uploads routinely carry third
parties' phone numbers, e-mails, ID card numbers and bank details. None of
that is needed to test a claim about public money, and holding it widens our
exposure under personal-data law (Tunisia: Organic Law 2004-63; GDPR when EU
residents are concerned). The raw bytes stay in the restricted blob store for
chain of custody; the working text is masked.
"""

from __future__ import annotations

import re

from caligula.domain.model.documents import SourceKind

# Sources whose text is minimised before any agent reads it.
MINIMISED_KINDS = {SourceKind.SOCIAL, SourceKind.CONTRIBUTOR, SourceKind.NEWS}

_PATTERNS = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[\dA-Z]{4}){4,7}\b")),
    ("RIB", re.compile(r"\b\d{2}\s?\d{3}\s?\d{13}\s?\d{2}\b")),
    ("ID", re.compile(r"(?i)\b(?:c\.?i\.?n\.?|carte d'identit[ée](?: nationale)?|passeport|passport)\s*(?:n[°o]\.?|no\.?|number|:)?\s*[A-Z]?\d{6,9}\b")),
    # Tunisian numbers (+216 / 00216 / 8 digits in 2-3-3 or 2-2-2-2 groups) and other international numbers.
    ("PHONE", re.compile(r"(?:(?:\+|00)216[\s.-]?)?\b[2-9]\d[\s.-]?\d{3}[\s.-]?\d{3}\b|(?:\+|00)\d{1,3}(?:[\s.-]?\d{2,4}){3,5}\b")),
]


def minimise(text: str) -> tuple[str, dict[str, int]]:
    """Mask personal identifiers. Returns the masked text and counts per type."""
    counts: dict[str, int] = {}
    for label, pattern in _PATTERNS:
        text, n = pattern.subn(f"[{label}]", text)
        if n:
            counts[label] = n
    return text, counts
