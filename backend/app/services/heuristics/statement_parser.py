"""
Heuristic line-item parser for financial statements (balance sheet,
profit & loss, cash flow statement).

Bank/company statements in the sample dataset are laid out as:

    <label text>                    <schedule?>   <value col 1>   <value col 2>
    Capital                              1           557.97          554.55

This parser walks OCR/native text line by line, tracks the current
section header (so a repeated label like "Total" can be disambiguated
by the section it falls under), and pulls out every trailing numeric
token on the line as a period column value.

It is intentionally forgiving — designed as a zero-dependency fallback
extractor, not a layout-perfect parser. The LLM extraction path (used
automatically when an API key is configured) will outperform this on
complex/irregular layouts.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from app.utils.numbers import parse_number

# A trailing numeric token: optional parentheses/brackets, optional minus,
# digits with optional thousands separators and decimal part, or a bare "-"
_TRAILING_NUMBER = re.compile(
    r"(\(?-?[\d][\d,]*\.?\d*\)?|\[-?[\d][\d,]*\.?\d*\]|^-$)"
)
# Known section headers to watch for. OCR frequently mangles the leading
# roman numeral ("I INCOME" -> "| INCOME", "II EXPENDITURE" -> "ll
# EXPENDITURE", "III PROFIT" -> "Ill PROFIT"), so section detection matches
# on the keyword appearing anywhere in an otherwise short, digit-free line
# rather than requiring the whole line to be clean uppercase text.
_SECTION_KEYWORDS = (
    "CAPITAL AND LIABILITIES", "ASSETS", "INCOME", "EXPENDITURE", "PROFIT",
    "APPROPRIATIONS", "OPERATING ACTIVITIES", "INVESTING ACTIVITIES",
    "FINANCING ACTIVITIES",
)

# Boilerplate (signature blocks, firm registration numbers, footers) that
# occasionally matches the "label + trailing numbers" pattern but is not a
# real financial line item.
_NOISE_LABEL_SUBSTRINGS = (
    "membership number", "mumbai,", "chartered accountant", "registration number",
    "as per our report", "for and on behalf", "significant accounting policies",
)


def _detect_section_header(stripped_line: str) -> Optional[str]:
    if any(ch.isdigit() for ch in stripped_line) or len(stripped_line) > 55:
        return None
    upper = stripped_line.upper()
    for keyword in _SECTION_KEYWORDS:
        if keyword in upper:
            return keyword
    return None


@dataclass
class StatementLine:
    label: str
    section: Optional[str]
    values: list[float] = field(default_factory=list)
    page: int = 1
    raw: str = ""


def _tokenize_trailing_numbers(line: str) -> tuple[str, list[float]]:
    """Split a line into (label_text, [numbers...]) by peeling numeric
    tokens off the end of the line."""
    tokens = line.strip().split()
    numbers: list[float] = []
    while len(tokens) > 1:
        candidate = tokens[-1]
        val = parse_number(candidate)
        if val is not None:
            numbers.insert(0, val)
            tokens.pop()
        elif candidate in {"-", "—", "–", "nil", "Nil", "N/A"}:
            numbers.insert(0, 0.0)
            tokens.pop()
        elif _TRAILING_NUMBER.fullmatch(candidate.replace(",", "")) or _TRAILING_NUMBER.fullmatch(candidate):
            parsed = parse_number(candidate)
            numbers.insert(0, parsed if parsed is not None else 0.0)
            tokens.pop()
        else:
            break
    label = " ".join(tokens).strip(" :.-")
    return label, numbers


def parse_pages(pages: list[str]) -> list[StatementLine]:
    lines: list[StatementLine] = []
    current_section: Optional[str] = None

    for page_idx, page_text in enumerate(pages, start=1):
        for raw_line in page_text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue

            # Section header detection (short, digit-free line containing a
            # known section keyword — tolerant of OCR-mangled roman numerals).
            detected = _detect_section_header(stripped)
            if detected:
                current_section = detected
                continue

            label, numbers = _tokenize_trailing_numbers(stripped)
            if not label or not numbers:
                continue
            if any(noise in label.lower() or noise in stripped.lower() for noise in _NOISE_LABEL_SUBSTRINGS):
                continue
            # Drop a lone "schedule/note number" masquerading as the first value
            # when there are 3+ numbers and the first looks like a small int index.
            if len(numbers) >= 3 and numbers[0] == int(numbers[0]) and 0 < numbers[0] < 50:
                numbers = numbers[1:]

            lines.append(
                StatementLine(
                    label=label, section=current_section, values=numbers,
                    page=page_idx, raw=stripped,
                )
            )

    return lines


def find_line(lines: list[StatementLine], *, keywords: list[str],
              section_hint: Optional[str] = None,
              exclude_keywords: Optional[list[str]] = None) -> Optional[StatementLine]:
    """Find the best-matching line for a canonical field.

    Matching is case-insensitive substring matching on the label. If
    `section_hint` is given, lines within a section whose header contains
    the hint are preferred over lines with no/other section.
    """
    exclude_keywords = exclude_keywords or []
    candidates = []
    for ln in lines:
        label_lower = ln.label.lower()
        if any(kw.lower() in label_lower for kw in keywords):
            if any(ex.lower() in label_lower for ex in exclude_keywords):
                continue
            candidates.append(ln)

    if not candidates:
        return None
    if section_hint:
        preferred = [c for c in candidates if c.section and section_hint.lower() in c.section.lower()]
        if preferred:
            return preferred[0]
    return candidates[0]
