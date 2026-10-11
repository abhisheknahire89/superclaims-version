"""Money helpers. Storage: integer paise. Computation: Decimal. API: decimal strings with two places."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

PAISE = Decimal("0.01")


def to_paise(rupees) -> int:
    d = rupees if isinstance(rupees, Decimal) else Decimal(str(rupees))
    return int((d.quantize(PAISE, rounding=ROUND_HALF_UP) * 100).to_integral_value())


def from_paise(p: int | None) -> Decimal | None:
    return None if p is None else (Decimal(p) / 100).quantize(PAISE)


def fmt(p: int | None) -> str | None:
    v = from_paise(p)
    return None if v is None else f"{v:.2f}"


def inr(p: int | None) -> str:
    """Indian digit grouping for display: 17245575 -> '1,72,455.75'."""
    if p is None:
        return "—"
    v = from_paise(p)
    neg = v < 0
    whole, frac = f"{abs(v):.2f}".split(".")
    last3, rest = whole[-3:], whole[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    s = ",".join(groups + [last3]) if groups else last3
    return ("−" if neg else "") + s + "." + frac
