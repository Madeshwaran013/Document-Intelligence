from app.utils.numbers import is_close, parse_number


def test_parse_plain_number():
    assert parse_number("1234.50") == 1234.5


def test_parse_thousands_separator():
    assert parse_number("1,234,567.89") == 1234567.89


def test_parse_parentheses_negative():
    assert parse_number("(1,546.40)") == -1546.4


def test_parse_currency_symbol():
    assert parse_number("$1,234.50") == 1234.5
    assert parse_number("₹804") == 804.0


def test_parse_dash_returns_none():
    assert parse_number("-") is None
    assert parse_number("") is None
    assert parse_number(None) is None


def test_is_close_within_tolerance():
    assert is_close(100.0, 100.5, rel_tol=0.01, abs_tol=1.0)
    assert not is_close(100.0, 110.0, rel_tol=0.01, abs_tol=1.0)


def test_is_close_none_is_never_close():
    assert not is_close(None, 100.0, rel_tol=0.01, abs_tol=1.0)
    assert not is_close(100.0, None, rel_tol=0.01, abs_tol=1.0)
