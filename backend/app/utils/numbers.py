"""
Shared numeric parsing helpers.

Financial documents represent negative values with parentheses (e.g.
``(1,546.40)``), use thousands separators, and often prefix/suffix a
currency symbol. These helpers centralise that parsing so every service
handles it identically instead of re-implementing ad-hoc regexes.
"""
import re
from typing import Optional

_NUMBER_RE = re.compile(r"\(?-?\d[\d,]*\.?\d*\)?")


def parse_number(raw: Optional[str]) -> Optional[float]:
    """Parse a financial number string into a float.

    Handles thousands separators, a leading/trailing currency symbol or
    percentage sign, and parentheses/brackets to denote negative values
    (accounting convention), e.g.:

        "1,234.50"   -> 1234.5
        "(1,234.50)" -> -1234.5
        "$1,234.50"  -> 1234.5
        "-"          -> None
        ""           -> None
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text in {"-", "—", "–", "NA", "N/A", "nil", "Nil"}:
        return None

    is_negative = False
    if text.startswith("(") and text.endswith(")"):
        is_negative = True
        text = text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        is_negative = True
        text = text[1:-1]
    if text.startswith("-"):
        is_negative = True
        text = text[1:]

    # Strip currency symbols / letters / percent signs, keep digits, commas, dots
    match = _NUMBER_RE.search(text.replace(",", "").replace(" ", ""))
    cleaned = re.sub(r"[^\d.]", "", text)
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if is_negative else value


def is_close(a: Optional[float], b: Optional[float], rel_tol: float, abs_tol: float) -> bool:
    """True if two numbers reconcile within the configured tolerance."""
    if a is None or b is None:
        return False
    diff = abs(a - b)
    return diff <= abs_tol or diff <= rel_tol * max(abs(a), abs(b), 1.0)
