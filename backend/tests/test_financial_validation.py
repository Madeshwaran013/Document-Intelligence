from app.services.financial_validation_service import validate


def _f(value):
    return {"value": value, "page_number": 1, "source_text": None}


def test_invoice_validation_all_pass():
    data = {
        "subtotal": _f(804.0),
        "tax_amount": _f(64.32),
        "discount": _f(0.0),
        "total_amount": _f(868.32),
        "line_items": [
            {"description": "Widget", "quantity": 2, "unit_price": 300.0, "amount": 600.0},
            {"description": "Gadget", "quantity": 1, "unit_price": 204.0, "amount": 204.0},
        ],
    }
    result = validate("invoice", data)
    assert result.overall_status == "PASS"
    by_name = {c.name: c for c in result.checks}
    assert by_name["line_item_quantity_times_price"].status == "PASS"
    assert by_name["line_items_sum_reconciles_to_subtotal"].status == "PASS"
    assert by_name["subtotal_plus_tax_minus_discount_equals_total"].status == "PASS"


def test_invoice_validation_detects_mismatch():
    data = {
        "subtotal": _f(100.0),
        "tax_amount": _f(10.0),
        "discount": _f(0.0),
        "total_amount": _f(999.0),  # deliberately wrong
        "line_items": [],
    }
    result = validate("invoice", data)
    assert result.overall_status == "FAIL"
    assert any(c.status == "FAIL" for c in result.checks)


def test_invoice_validation_missing_fields_not_applicable():
    result = validate("invoice", {})
    assert result.overall_status == "NOT_APPLICABLE"
    assert all(c.status == "NOT_APPLICABLE" for c in result.checks)


def test_balance_sheet_validation_pass():
    data = {
        "total_assets": _f(1000.0),
        "total_capital_and_liabilities": _f(1000.0),
        "periods": ["2023"],
        "line_items": [],
    }
    result = validate("balance_sheet", data)
    assert result.overall_status == "PASS"


def test_balance_sheet_validation_fail_on_mismatch():
    data = {
        "total_assets": _f(1000.0),
        "total_capital_and_liabilities": _f(900.0),
        "periods": ["2023"],
        "line_items": [],
    }
    result = validate("balance_sheet", data)
    assert result.overall_status == "FAIL"


def test_profit_and_loss_full_chain_pass():
    data = {
        "interest_earned": _f(170754.05),
        "other_income": _f(33912.05),
        "total_income": _f(204666.10),
        "interest_expended": _f(77779.94),
        "operating_expenses": _f(51533.69),
        "provisions_and_contingencies": _f(29203.77),
        "total_expenditure": _f(158517.40),
        "net_profit_before_minority_interest": _f(46148.70),
        "minority_interest": _f(151.59),
        "net_profit_attributable_to_group": _f(45997.11),
        "brought_forward_profit": _f(99062.77),
        "total_available_for_appropriation": _f(145059.88),
    }
    result = validate("profit_and_loss", data)
    assert result.overall_status == "PASS"
    assert len(result.checks) == 5


def test_cash_flow_validation_pass():
    data = {
        "net_cash_from_operating": _f(20813.70),
        "net_cash_from_investing": _f(-3423.89),
        "net_cash_from_financing": _f(23940.56),
        "fx_translation_adjustment": _f(431.71),
        "net_increase_in_cash": _f(41762.08),
        "opening_cash": _f(155385.73),
        "closing_cash": _f(197147.81),
    }
    result = validate("cash_flow_statement", data)
    assert result.overall_status == "PASS"
