"""Grounding check (CAP-04 step 4, 07 §4): every extracted value must quote text that actually appears on the
cited page. A fact whose quote is not found is stored with grounding_check = NOT_FOUND and can never be used
by rules. This is the main defence against hallucinated values from any extraction provider."""
from __future__ import annotations

from .normalise import text_for_matching


def check(quote: str, page_text: str) -> str:
    if not quote or not quote.strip():
        return "NOT_FOUND"
    return "VERIFIED" if text_for_matching(quote) in text_for_matching(page_text) else "NOT_FOUND"
