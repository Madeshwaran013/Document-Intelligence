"""
Heuristic (no-LLM) invoice extraction: regex-based field detection plus a
best-effort line-item table parser.

This is the fallback path used when no LLM API key is configured. It
covers common invoice layouts reasonably well but will not match the LLM
path's accuracy on unusual/irregular layouts — see README for details.
"""
import re

from app.utils.numbers import parse_number

_PATTERNS = {
    "invoice_number": [
        r"invoice\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"\bINV[-\s]?([A-Za-z0-9\-]+)",
    ],
    "invoice_date": [
        r"(?<!due )date\s*[:\-]?\s*([A-Za-z0-9,\-\/ ]{6,20})",
        r"invoice date\s*[:\-]?\s*([A-Za-z0-9,\-\/ ]{6,20})",
    ],
}

_LINE_ITEM_RE = re.compile(
    r"^(?P<desc>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+(?P<price>[\$₹€]?\(?-?[\d,]+\.?\d*\)?)\s+(?P<amount>[\$₹€]?\(?-?[\d,]+\.?\d*\)?)\s*$"
)


_PURE_NUMBER_RE = re.compile(r"^[\$₹€]?\(?-?[\d,]+\.?\d*\)?$")


def _merge_wrapped_label_lines(lines: list[str]) -> list[str]:
    """OCR sometimes puts a bare label ('Total Due') on its own line with the
    value on the following line. Merge those pairs so downstream regexes
    (which expect label and value on the same line) can find them."""
    merged: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        has_digit = any(ch.isdigit() for ch in line)
        if not has_digit and i + 1 < len(lines) and _PURE_NUMBER_RE.match(lines[i + 1]):
            merged.append(f"{line} {lines[i + 1]}")
            i += 2
            continue
        merged.append(line)
        i += 1
    return merged


def extract(pages: list[str]) -> dict:
    joined = "\n".join(pages)
    raw_lines = [l.strip() for l in joined.splitlines() if l.strip()]
    lines = _merge_wrapped_label_lines(raw_lines)

    result: dict = {
        "invoice_number": _field(joined, "invoice_number"),
        "invoice_date": _field(joined, "invoice_date"),
        "vendor_name": _party(raw_lines, ["bill from", "from", "vendor", "seller"]),
        "customer_name": _party(raw_lines, ["bill to", "to", "customer", "buyer"]),
        "currency": _currency(joined),
        "subtotal": _amount_field(lines, ["subtotal", "sub total", "sub-total"]),
        "tax_amount": _amount_field(lines, ["tax", "vat", "gst"]),
        "discount": _amount_field(lines, ["discount"]),
        "total_amount": _amount_field(lines, ["total due", "grand total", "total amount", "amount due", "total"]),
        "cash_paid": _amount_field(lines, ["cash", "amount paid", "paid"]),
        "change": _amount_field(lines, ["change"]),
        "line_items": _line_items(raw_lines),
    }
    return result


def _field(text: str, key: str) -> dict:
    for pattern in _PATTERNS[key]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return {"value": m.group(1).strip(), "page_number": 1, "source_text": m.group(0).strip()}
    return {"value": None, "page_number": None, "source_text": None}


def _party(lines: list[str], labels: list[str]) -> dict:
    for i, line in enumerate(lines):
        low = line.lower().strip(" :")
        if low in labels:
            # Party name is typically the next non-empty line.
            if i + 1 < len(lines):
                return {"value": lines[i + 1].strip(), "page_number": 1, "source_text": lines[i + 1]}
    return {"value": None, "page_number": None, "source_text": None}


def _amount_field(lines: list[str], labels: list[str]) -> dict:
    for line in lines:
        low = line.lower()
        if any(low.startswith(lbl) or f" {lbl}" in low for lbl in labels):
            numbers = re.findall(r"[\$₹€]?\(?-?[\d,]+\.?\d*\)?", line)
            numbers = [n for n in numbers if re.search(r"\d", n)]
            if numbers:
                val = parse_number(numbers[-1])
                if val is not None:
                    return {"value": val, "page_number": 1, "source_text": line}
    return {"value": None, "page_number": None, "source_text": None}


def _currency(text: str) -> dict:
    if "$" in text or re.search(r"\bUSD\b", text):
        cur = "USD"
    elif "₹" in text or re.search(r"\bINR\b|\bRs\.", text):
        cur = "INR"
    elif "€" in text or re.search(r"\bEUR\b", text):
        cur = "EUR"
    else:
        cur = None
    return {"value": cur, "page_number": 1, "source_text": None}


_LINE_ITEM_3_RE = re.compile(
    r"^(?P<desc>.+?)\s+(?P<price>[\$₹€]?\(?-?[\d,]+\.?\d*\)?)\s+(?P<amount>[\$₹€]?\(?-?[\d,]+\.?\d*\)?)\s*$"
)


def _line_items(lines: list[str]) -> list[dict]:
    items = []
    for idx, line in enumerate(lines):
        m = _LINE_ITEM_RE.match(line)
        if m:
            desc = m.group("desc").strip(" |")
            qty = parse_number(m.group("qty"))
            price = parse_number(m.group("price"))
            amount = parse_number(m.group("amount"))
        else:
            m3 = _LINE_ITEM_3_RE.match(line)
            if not m3:
                continue
            desc = m3.group("desc").strip(" |")
            price = parse_number(m3.group("price"))
            amount = parse_number(m3.group("amount"))
            if price and amount and abs(price - amount) < 1e-4:
                qty = 1.0
            elif price and amount and price > 0:
                qty = round(amount / price, 2)
            else:
                qty = 1.0

        if amount is None:
            continue
        if desc.lower() in {"description", "id description", "item", "id"}:
            continue
        # OCR often splits a wrapped row as: "<description text>" on one
        # line, then "<row id> <qty> <price> <amount>" on the next — in that
        # case `desc` here is just a short row id/index. Pull the real
        # description text from the preceding line instead.
        if re.fullmatch(r"\d{1,3}", desc) and idx > 0:
            prev = lines[idx - 1].strip()
            if prev and not _LINE_ITEM_RE.match(prev) and not _LINE_ITEM_3_RE.match(prev):
                desc = prev
        items.append({"description": desc, "quantity": qty, "unit_price": price, "amount": amount})
    return items
