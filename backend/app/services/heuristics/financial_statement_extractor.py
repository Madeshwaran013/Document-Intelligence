"""
Heuristic (no-LLM) extraction for balance sheet / P&L / cash flow
statements, built on top of statement_parser.

Produces the same shape the LLM path produces:
    {
      "<canonical_field>": {"value": ..., "page_number": ..., "source_text": ...},
      ...
      "line_items": [{"label": ..., "values": {...}, "page_number": ..., "source_text": ...}, ...],
      "periods": ["current", "prior"]   # best-effort column labels
    }
"""
import re

from app.services.heuristics.statement_parser import StatementLine, find_line, parse_pages

# canonical_field -> (keywords, section_hint, exclude_keywords)
_BALANCE_SHEET_FIELDS = {
    "total_capital_and_liabilities": (["total"], "CAPITAL AND LIABILITIES", ["assets"]),
    "total_assets": (["total"], "ASSETS", ["liabilit"]),
    "capital": (["capital"], "CAPITAL AND LIABILITIES", ["total", "liabilit"]),
    "reserves_and_surplus": (["reserves"], None, []),
    "deposits": (["deposit"], None, ["fixed"]),
    "borrowings": (["borrowing"], None, []),
    "total_liabilities": (["other liabilities"], None, []),
    "cash_and_balances": (["cash and balances"], None, []),
    "investments": (["investment"], "ASSETS", []),
    "advances": (["advance"], None, []),
    "fixed_assets": (["fixed asset"], None, []),
}

_PL_FIELDS = {
    "interest_earned": (["interest earned"], None, []),
    "other_income": (["other income"], None, []),
    "total_income": (["total"], "INCOME", []),
    "interest_expended": (["interest expended"], None, []),
    "operating_expenses": (["operating expense"], None, []),
    "provisions_and_contingencies": (["provision"], None, []),
    "total_expenditure": (["total"], "EXPENDITURE", []),
    "net_profit_before_minority_interest": (["net profit for the year before", "yearbefore", "before minorities"], None, []),
    "minority_interest": (["minorit"], None, ["before", "add", "less minority interest (opening"]),
    "net_profit_attributable_to_group": (["net profit for the year attributable"], None, []),
    "brought_forward_profit": (["brought forward"], None, []),
    "total_available_for_appropriation": (["total"], "APPROPRIATIONS", []),
    "revenue": (["revenue", "total income", "interest earned"], None, []),
    "net_profit": (["net profit"], None, ["before", "brought"]),
}

_CASH_FLOW_FIELDS = {
    "net_cash_from_operating": (["net cash flow", "net cash generated", "net cash used"], "OPERATING", []),
    "net_cash_from_investing": (["net cash flow", "net cash used", "net cash generated"], "INVESTING", []),
    "net_cash_from_financing": (["net cash flow", "net cash generated", "net cash used"], "FINANCING", []),
    "fx_translation_adjustment": (["exchange fluctuation", "translation"], None, []),
    "net_increase_in_cash": (["net increase in cash", "net (decrease)/increase"], None, []),
    "opening_cash": (["as at april", "opening", "beginning of"], None, []),
    "closing_cash": (["as at the year end", "at the end of the year", "closing"], None, []),
}

_FIELD_MAP_BY_TYPE = {
    "balance_sheet": _BALANCE_SHEET_FIELDS,
    "profit_and_loss": _PL_FIELDS,
    "cash_flow_statement": _CASH_FLOW_FIELDS,
}


def _extract_periods(pages: list[str]) -> list[str]:
    joined = "\n".join(pages)
    years = re.findall(r"(?:March|December|June)\s+\d{1,2},?\s+(\d{4})", joined)
    years += re.findall(r"\b(20\d{2})\b", joined)
    seen: list[str] = []
    for y in years:
        if y not in seen:
            seen.append(y)
    return seen[:2] if seen else ["current", "prior"]


def extract(document_type: str, pages: list[str]) -> dict:
    lines = parse_pages(pages)
    periods = _extract_periods(pages)
    field_map = _FIELD_MAP_BY_TYPE.get(document_type, {})

    extracted: dict = {}
    for canonical, (keywords, section_hint, exclude) in field_map.items():
        line = find_line(lines, keywords=keywords, section_hint=section_hint, exclude_keywords=exclude)
        extracted[canonical] = _line_to_field(line, periods)

    extracted["currency"] = {"value": _guess_currency(pages), "page_number": 1, "source_text": None}
    extracted["line_items"] = [_line_to_item(ln, periods) for ln in lines]
    extracted["periods"] = periods
    return extracted


def _line_to_field(line: StatementLine | None, periods: list[str]) -> dict:
    if line is None:
        return {"value": None, "page_number": None, "source_text": None}
    value = line.values[0] if line.values else None
    return {"value": value, "page_number": line.page, "source_text": line.raw}


def _line_to_item(line: StatementLine, periods: list[str]) -> dict:
    values = {}
    for i, v in enumerate(line.values):
        period_label = periods[i] if i < len(periods) else f"col_{i+1}"
        values[period_label] = v
    return {
        "label": line.label,
        "section": line.section,
        "values": values,
        "page_number": line.page,
        "source_text": line.raw,
    }


def _guess_currency(pages: list[str]) -> str | None:
    joined = "\n".join(pages)
    if "₹" in joined or "Rs." in joined or "crore" in joined.lower() or "INR" in joined:
        return "INR"
    if "$" in joined or "USD" in joined:
        return "USD"
    if "€" in joined or "EUR" in joined:
        return "EUR"
    return None
