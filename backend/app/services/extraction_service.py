"""
AI-based field & table extraction (case study section 4.2).

Two strategies:

  * "llm"       — sends the OCR/native text to an LLM (Anthropic Claude)
                  with a document-type-specific prompt and a strict
                  JSON-only response format. Used automatically whenever
                  ANTHROPIC_API_KEY is configured and USE_LLM_EXTRACTION
                  is not disabled. Best accuracy on varied real-world
                  layouts.

  * "heuristic" — zero-dependency regex/rule-based extractor (see
                  services/heuristics/). Used automatically when no LLM
                  key is configured, so the service is fully functional
                  out of the box (local dev, tests, evaluators without a
                  key). Lower accuracy on irregular layouts — documented
                  as a known limitation in the README.

The function never invents values: fields it cannot find are returned
as null, consistent with the "do not hallucinate" requirement.
"""
import json
import re

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.heuristics import financial_statement_extractor, invoice_extractor
from app.utils.exceptions import ExtractionFailedError

logger = get_logger(__name__)

_SCHEMA_HINTS = {
    "invoice": (
        "invoice_number, invoice_date, vendor_name, customer_name, currency, "
        "subtotal, tax_amount, discount, total_amount, cash_paid, change, "
        "and a `line_items` array of {description, quantity, unit_price, amount}."
    ),
    "balance_sheet": (
        "total_assets, total_capital_and_liabilities, capital, reserves_and_surplus, "
        "deposits, borrowings, investments, advances, fixed_assets, currency, "
        "periods (array of period labels found in the document), and a `line_items` "
        "array covering EVERY visible line item as "
        "{label, section, values: {<period label>: number, ...}, page_number}."
    ),
    "profit_and_loss": (
        "interest_earned, other_income, total_income, interest_expended, "
        "operating_expenses, provisions_and_contingencies, total_expenditure, "
        "net_profit_before_minority_interest, minority_interest, "
        "net_profit_attributable_to_group, brought_forward_profit, "
        "total_available_for_appropriation, revenue, cost_of_sales, gross_profit, "
        "net_profit, tax, currency, periods, and a `line_items` array covering EVERY "
        "visible line item as {label, section, values: {<period label>: number}, page_number}."
    ),
    "cash_flow_statement": (
        "net_cash_from_operating, net_cash_from_investing, net_cash_from_financing, "
        "fx_translation_adjustment, net_increase_in_cash, opening_cash, closing_cash, "
        "currency, periods, and a `line_items` array covering EVERY visible line item as "
        "{label, section, values: {<period label>: number}, page_number}."
    ),
}


def extract_fields(document_type: str, ocr_pages: list[str]) -> tuple[dict, str]:
    """Returns (extracted_data, method) where method is "llm" or "heuristic"."""
    settings = get_settings()
    if settings.USE_LLM_EXTRACTION and settings.ANTHROPIC_API_KEY:
        try:
            data = _extract_with_llm(document_type, ocr_pages, settings)
            return data, "llm"
        except Exception:  # noqa: BLE001
            logger.exception("LLM extraction failed, falling back to heuristic extractor")

    return _extract_with_heuristics(document_type, ocr_pages), "heuristic"


def _extract_with_heuristics(document_type: str, ocr_pages: list[str]) -> dict:
    if document_type == "invoice":
        return invoice_extractor.extract(ocr_pages)
    return financial_statement_extractor.extract(document_type, ocr_pages)


def _extract_with_llm(document_type: str, ocr_pages: list[str], settings) -> dict:
    import anthropic  # local import so the package is only required when LLM path is used

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    numbered_text = "\n\n".join(
        f"[PAGE {i + 1}]\n{text}" for i, text in enumerate(ocr_pages)
    )
    schema_hint = _SCHEMA_HINTS.get(document_type, "all meaningful fields visible in the document")

    system_prompt = (
        "You are a precise document-extraction engine for financial documents. "
        "Extract ONLY values that are actually present in the provided text. "
        "Never guess, infer, or invent a value. If a field is not present, its "
        "value MUST be null. Respond with STRICT JSON ONLY — no markdown fences, "
        "no commentary, no trailing text."
    )
    user_prompt = (
        f"Document type: {document_type}\n\n"
        f"Extract the following fields where present: {schema_hint}\n\n"
        "For every extracted field, also provide the page_number it was found on "
        "and, where practical, a short source_text snippet copied verbatim from the "
        "document that supports the value, in this shape: "
        '{"value": ..., "page_number": <int|null>, "source_text": <string|null>}.\n\n'
        "For line_items / statement rows, include every visible row — do not "
        "truncate or summarise.\n\n"
        f"--- DOCUMENT TEXT (OCR/extracted, page-delimited) ---\n{numbered_text}\n"
        "--- END DOCUMENT TEXT ---\n\n"
        "Return a single JSON object only."
    )

    response = client.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    return _parse_json_response(raw_text)


def _parse_json_response(raw_text: str) -> dict:
    text = raw_text.strip()
    # Strip markdown code fences if the model added them despite instructions.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Try to recover the largest {...} block.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise ExtractionFailedError(f"LLM did not return valid JSON: {exc}") from exc
