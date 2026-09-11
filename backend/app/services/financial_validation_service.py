"""
Financial calculation validation (case study section 4.4).

Every check returns a ValidationCheck with formula, operands, calculated
value, reported value, variance and PASS/FAIL/NOT_APPLICABLE status. A
check is NOT_APPLICABLE (never invented/assumed) whenever a required
input field is missing from the extracted data.
"""
from typing import Any, Optional

from app.core.config import get_settings
from app.schemas.extraction import ValidationCheck, ValidationResult
from app.utils.numbers import is_close


def _val(extracted: dict, key: str) -> Optional[float]:
    field = extracted.get(key)
    if isinstance(field, dict):
        v = field.get("value")
        return float(v) if isinstance(v, (int, float)) else None
    return float(field) if isinstance(field, (int, float)) else None


def _check(name: str, formula: str, operands: dict, calculated: Optional[float],
           reported: Optional[float], rel_tol: float, abs_tol: float,
           period: Optional[str] = None) -> ValidationCheck:
    if calculated is None or reported is None:
        return ValidationCheck(
            name=name, formula=formula, operands=operands, calculated_value=calculated,
            reported_value=reported, variance=None, status="NOT_APPLICABLE", period=period,
            note="One or more required fields were not found in the extracted data.",
        )
    variance = round(calculated - reported, 2)
    status = "PASS" if is_close(calculated, reported, rel_tol, abs_tol) else "FAIL"
    return ValidationCheck(
        name=name, formula=formula, operands=operands, calculated_value=round(calculated, 2),
        reported_value=round(reported, 2), variance=variance, status=status, period=period,
    )


def validate(document_type: str, extracted: dict) -> ValidationResult:
    settings = get_settings()
    rel_tol = settings.VALIDATION_RELATIVE_TOLERANCE
    abs_tol = settings.VALIDATION_ABSOLUTE_TOLERANCE

    if document_type == "invoice":
        checks = _validate_invoice(extracted, rel_tol, abs_tol)
    elif document_type == "balance_sheet":
        checks = _validate_balance_sheet(extracted, rel_tol, abs_tol)
    elif document_type == "profit_and_loss":
        checks = _validate_profit_and_loss(extracted, rel_tol, abs_tol)
    elif document_type == "cash_flow_statement":
        checks = _validate_cash_flow(extracted, rel_tol, abs_tol)
    else:
        checks = []

    statuses = {c.status for c in checks}
    if not checks or statuses == {"NOT_APPLICABLE"}:
        overall = "NOT_APPLICABLE"
    elif "FAIL" in statuses:
        overall = "FAIL"
    else:
        overall = "PASS"

    issues = [f"{c.name}: reported {c.reported_value} vs calculated {c.calculated_value}"
              for c in checks if c.status == "FAIL"]

    return ValidationResult(checks=checks, overall_status=overall, issues=issues)


# ---------------------------------------------------------------- invoice --

def _validate_invoice(data: dict, rel_tol: float, abs_tol: float) -> list[ValidationCheck]:
    checks = []
    subtotal = _val(data, "subtotal")
    tax = _val(data, "tax_amount")
    discount = _val(data, "discount") or (0.0 if subtotal is not None else None)
    total = _val(data, "total_amount")
    line_items = data.get("line_items") or []

    # 1. line total = quantity * unit price (per line item, aggregated pass/fail)
    if line_items:
        bad_lines = []
        checked_any = False
        for item in line_items:
            qty, price, amount = item.get("quantity"), item.get("unit_price"), item.get("amount")
            if qty is None or price is None or amount is None:
                continue
            checked_any = True
            if not is_close(qty * price, amount, rel_tol, abs_tol):
                bad_lines.append(item.get("description", "line item"))
        if checked_any:
            checks.append(ValidationCheck(
                name="line_item_quantity_times_price",
                formula="quantity * unit_price ≈ amount (per line item)",
                operands={"line_items_checked": len(line_items)},
                calculated_value=None, reported_value=None, variance=None,
                status="FAIL" if bad_lines else "PASS",
                note=f"Mismatched line items: {bad_lines}" if bad_lines else None,
            ))
        else:
            checks.append(_check("line_item_quantity_times_price",
                                  "quantity * unit_price ≈ amount", {}, None, None, rel_tol, abs_tol))

        # 2. sum of line totals reconciles to subtotal
        line_sum = sum(i["amount"] for i in line_items if isinstance(i.get("amount"), (int, float)))
        checks.append(_check(
            "line_items_sum_reconciles_to_subtotal", "sum(line_totals) ≈ subtotal",
            {"sum_line_totals": line_sum, "subtotal": subtotal}, line_sum, subtotal, rel_tol, abs_tol,
        ))

    # 3. taxable amount + tax ≈ total
    if subtotal is not None and tax is not None:
        calc = subtotal + tax - (discount or 0.0)
        checks.append(_check(
            "subtotal_plus_tax_minus_discount_equals_total",
            "subtotal + tax_amount - discount ≈ total_amount",
            {"subtotal": subtotal, "tax_amount": tax, "discount": discount or 0.0},
            calc, total, rel_tol, abs_tol,
        ))
    else:
        checks.append(_check("subtotal_plus_tax_minus_discount_equals_total",
                              "subtotal + tax_amount - discount ≈ total_amount",
                              {"subtotal": subtotal, "tax_amount": tax, "discount": discount},
                              None, total, rel_tol, abs_tol))

    # 4. cash paid - total ≈ change
    cash_paid = _val(data, "cash_paid")
    change = _val(data, "change")
    if cash_paid is not None and total is not None:
        checks.append(_check(
            "cash_paid_minus_total_equals_change", "cash_paid - total_amount ≈ change",
            {"cash_paid": cash_paid, "total_amount": total}, cash_paid - total, change, rel_tol, abs_tol,
        ))

    return checks


# ---------------------------------------------------------- balance sheet --

def _validate_balance_sheet(data: dict, rel_tol: float, abs_tol: float) -> list[ValidationCheck]:
    checks = []
    periods = data.get("periods") or ["current"]
    line_items = data.get("line_items") or []

    total_assets_field = data.get("total_assets", {})
    total_liab_field = data.get("total_capital_and_liabilities", {})

    for period in periods:
        assets = _period_value(total_assets_field, period)
        liab = _period_value(total_liab_field, period)
        checks.append(_check(
            "total_capital_and_liabilities_equals_total_assets",
            "Total Capital & Liabilities ≈ Total Assets",
            {"total_capital_and_liabilities": liab, "total_assets": assets},
            liab, assets, rel_tol, abs_tol, period=str(period),
        ))

    # Sum of components within each labelled section reconciling to that
    # section's own "total" row, per period — only when we have >=2 non-total rows.
    for section_name, total_keywords in [
        ("CAPITAL AND LIABILITIES", ["total"]),
        ("ASSETS", ["total"]),
    ]:
        section_lines = [li for li in line_items if (li.get("section") or "").upper() == section_name]
        total_idx = next((i for i, li in enumerate(section_lines)
                           if li.get("label", "").strip().lower() == "total"), None)
        if total_idx is None:
            continue
        # Only rows *before* the section's own "Total" row count as its
        # components — anything after belongs to the next section/footer
        # (e.g. signature blocks, contingent liabilities) even if our
        # section-header tracking didn't catch the boundary.
        component_lines = [li for li in section_lines[:total_idx]
                            if "total" not in li.get("label", "").lower()]
        total_line = section_lines[total_idx]
        if len(component_lines) < 2:
            continue
        for period in periods:
            comp_sum = sum(
                v for li in component_lines
                for k, v in li.get("values", {}).items()
                if str(k) == str(period) and isinstance(v, (int, float))
            )
            reported = _period_value_from_values(total_line.get("values", {}), period)
            checks.append(_check(
                f"{section_name.lower().replace(' ', '_')}_components_reconcile",
                f"sum(components in {section_name.title()}) ≈ reported total ({section_name.title()})",
                {"component_sum": comp_sum}, comp_sum, reported, rel_tol, abs_tol, period=str(period),
            ))

    return checks


def _period_value(field: dict, period) -> Optional[float]:
    if not isinstance(field, dict):
        return None
    v = field.get("value")
    return float(v) if isinstance(v, (int, float)) else None


def _period_value_from_values(values: dict, period) -> Optional[float]:
    v = values.get(period) or values.get(str(period))
    return float(v) if isinstance(v, (int, float)) else None


# --------------------------------------------------------- profit & loss --

def _validate_profit_and_loss(data: dict, rel_tol: float, abs_tol: float) -> list[ValidationCheck]:
    checks = []
    interest_earned = _val(data, "interest_earned")
    other_income = _val(data, "other_income")
    total_income = _val(data, "total_income")
    interest_expended = _val(data, "interest_expended")
    operating_expenses = _val(data, "operating_expenses")
    provisions = _val(data, "provisions_and_contingencies")
    total_expenditure = _val(data, "total_expenditure")
    net_profit_before_minority = _val(data, "net_profit_before_minority_interest")
    minority_interest = _val(data, "minority_interest")
    net_profit_group = _val(data, "net_profit_attributable_to_group")
    brought_forward = _val(data, "brought_forward_profit")
    total_appropriation = _val(data, "total_available_for_appropriation")

    checks.append(_check(
        "interest_earned_plus_other_income_equals_total_income",
        "Interest Earned + Other Income ≈ Total Income",
        {"interest_earned": interest_earned, "other_income": other_income},
        (interest_earned + other_income) if None not in (interest_earned, other_income) else None,
        total_income, rel_tol, abs_tol,
    ))

    if None not in (interest_expended, operating_expenses, provisions):
        calc_exp = interest_expended + operating_expenses + provisions
    else:
        calc_exp = None
    checks.append(_check(
        "expenditure_components_equal_total_expenditure",
        "Interest Expended + Operating Expenses + Provisions & Contingencies ≈ Total Expenditure",
        {"interest_expended": interest_expended, "operating_expenses": operating_expenses,
         "provisions_and_contingencies": provisions}, calc_exp, total_expenditure, rel_tol, abs_tol,
    ))

    checks.append(_check(
        "total_income_minus_total_expenditure_equals_net_profit_before_minority",
        "Total Income - Total Expenditure ≈ Consolidated Net Profit before Minority Interest",
        {"total_income": total_income, "total_expenditure": total_expenditure},
        (total_income - total_expenditure) if None not in (total_income, total_expenditure) else None,
        net_profit_before_minority, rel_tol, abs_tol,
    ))

    checks.append(_check(
        "net_profit_before_minority_minus_minority_interest_equals_group_profit",
        "Profit before Minority Interest - Minority Interest ≈ Consolidated Net Profit attributable to the Group",
        {"net_profit_before_minority_interest": net_profit_before_minority, "minority_interest": minority_interest},
        (net_profit_before_minority - minority_interest)
        if None not in (net_profit_before_minority, minority_interest) else None,
        net_profit_group, rel_tol, abs_tol,
    ))

    checks.append(_check(
        "current_plus_brought_forward_equals_total_appropriation",
        "Current Profit + Brought Forward Profit ≈ Total Available for Appropriation",
        {"net_profit_attributable_to_group": net_profit_group, "brought_forward_profit": brought_forward},
        (net_profit_group + brought_forward) if None not in (net_profit_group, brought_forward) else None,
        total_appropriation, rel_tol, abs_tol,
    ))

    return checks


# -------------------------------------------------------------- cash flow --

def _validate_cash_flow(data: dict, rel_tol: float, abs_tol: float) -> list[ValidationCheck]:
    checks = []
    op = _val(data, "net_cash_from_operating")
    inv = _val(data, "net_cash_from_investing")
    fin = _val(data, "net_cash_from_financing")
    fx = _val(data, "fx_translation_adjustment") or (0.0 if None not in (op, inv, fin) else None)
    net_increase = _val(data, "net_increase_in_cash")
    opening = _val(data, "opening_cash")
    closing = _val(data, "closing_cash")

    if None not in (op, inv, fin):
        calc_net = op + inv + fin + (fx or 0.0)
    else:
        calc_net = None
    checks.append(_check(
        "operating_investing_financing_fx_equals_net_increase",
        "Operating + Investing + Financing + FX/Translation Adjustment ≈ Net Increase in Cash",
        {"net_cash_from_operating": op, "net_cash_from_investing": inv,
         "net_cash_from_financing": fin, "fx_translation_adjustment": fx},
        calc_net, net_increase, rel_tol, abs_tol,
    ))

    checks.append(_check(
        "opening_cash_plus_net_increase_equals_closing_cash",
        "Opening Cash & Cash Equivalents + Net Increase in Cash ≈ Closing Cash & Cash Equivalents",
        {"opening_cash": opening, "net_increase_in_cash": net_increase},
        (opening + net_increase) if None not in (opening, net_increase) else None,
        closing, rel_tol, abs_tol,
    ))

    return checks
