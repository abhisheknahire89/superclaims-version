"""Normalisation of values as printed on Indian claim documents. Pure functions; no model involved."""
from __future__ import annotations

import re
import unicodedata
from datetime import date

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def amount(raw: str | None) -> str | None:
    """'1,72,455.75' / 'Rs. 3,420' / '₹ 85,850.25' -> '172455.75' (two decimals). None if not a plain amount."""
    if raw is None:
        return None
    s = str(raw).strip()
    s = re.sub(r"^(rs\.?|inr|₹)\s*", "", s, flags=re.I)
    s = s.replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", s):
        return None
    whole, _, frac = s.partition(".")
    return f"{int(whole)}.{(frac + '00')[:2]}"


def quantity(raw: str | None) -> str | None:
    if raw is None or str(raw).strip() == "":
        return None
    s = str(raw).strip()
    return s if re.fullmatch(r"\d+(\.\d+)?", s) else None


def to_date(raw: str | None) -> str | None:
    """Day-first parsing (Indian convention). Accepts dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy, yyyy-mm-dd, '02 Sep 2026'.
    Returns ISO yyyy-mm-dd, or None when the text is not an unambiguous date."""
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b", s)
        if m:
            d, mo, y = map(int, m.groups())
        else:
            m = re.search(r"\b(\d{1,2})[\s\-]([A-Za-z]{3})[A-Za-z]*[\s\-,]+(\d{4})\b", s)
            if not m:
                return None
            d, mon, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            if mon not in _MONTHS:
                return None
            mo = _MONTHS[mon]
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def time_of_day(raw: str | None) -> str | None:
    if raw is None:
        return None
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", str(raw))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def gender(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().upper()
    m = re.search(r"(?:^|[/\s])(F|FEMALE|M|MALE|TRANSGENDER|OTHER)\b", s)
    if not m:
        return None
    token = m.group(1)
    return {"F": "F", "FEMALE": "F", "M": "M", "MALE": "M"}.get(token, "X")


def text_for_matching(s: str) -> str:
    """Normalisation used by the grounding check: NFKC, unify dashes/quotes, collapse whitespace, case-fold."""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("–", "-").replace("—", "-").replace("−", "-").replace("‘", "'").replace("’", "'")
    s = s.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().casefold()
