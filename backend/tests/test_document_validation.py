from tests.conftest import FIXTURES_DIR

from app.services.document_validation_service import validate_file


def test_valid_pdf_passes():
    content = (FIXTURES_DIR / "sample_balance_sheet.pdf").read_bytes()
    result = validate_file("sample_balance_sheet.pdf", content, "application/pdf")
    assert result.status == "PASS"
    assert result.is_readable is True
    assert result.page_count == 1


def test_valid_image_passes():
    content = (FIXTURES_DIR / "sample_invoice.jpg").read_bytes()
    result = validate_file("sample_invoice.jpg", content, "image/jpeg")
    assert result.status == "PASS"


def test_empty_file_fails():
    result = validate_file("empty.pdf", b"", "application/pdf")
    assert result.status == "FAILED"
    assert "empty" in result.reason.lower()


def test_corrupted_pdf_fails():
    content = (FIXTURES_DIR / "corrupted.pdf").read_bytes()
    result = validate_file("corrupted.pdf", content, "application/pdf")
    assert result.status == "FAILED"


def test_unsupported_file_type_fails():
    content = (FIXTURES_DIR / "unsupported.txt").read_bytes()
    result = validate_file("unsupported.txt", content, "text/plain")
    assert result.status == "FAILED"
    assert result.is_supported is False


def test_page_limit_exceeded(monkeypatch):
    import app.services.document_validation_service as svc
    # Temporarily lower the page limit to 0 so any real (1-page) PDF trips it.
    from app.core.config import get_settings
    settings = get_settings()
    original = settings.MAX_PAGE_COUNT
    settings.MAX_PAGE_COUNT = 0
    try:
        content = (FIXTURES_DIR / "sample_balance_sheet.pdf").read_bytes()
        result = svc.validate_file("sample_balance_sheet.pdf", content, "application/pdf")
        assert result.status == "FAILED"
        assert "pages" in result.reason.lower()
    finally:
        settings.MAX_PAGE_COUNT = original
