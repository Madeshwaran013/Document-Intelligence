from tests.conftest import FIXTURES_DIR


def _upload(client, filename, document_type, content_type="application/pdf"):
    path = FIXTURES_DIR / filename
    with open(path, "rb") as f:
        return client.post(
            "/api/v1/documents/process",
            files={"file": (filename, f, content_type)},
            data={"document_type": document_type},
        )


def test_health(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_process_balance_sheet_end_to_end(client):
    res = _upload(client, "sample_balance_sheet.pdf", "balance_sheet")
    assert res.status_code == 200
    body = res.json()
    assert body["processing_status"] == "PASS"
    assert body["validation"]["overall_status"] == "PASS"
    assert body["extracted_data"]["total_assets"]["value"] is not None


def test_process_profit_and_loss_end_to_end(client):
    res = _upload(client, "sample_profit_and_loss.pdf", "profit_and_loss")
    assert res.status_code == 200
    body = res.json()
    assert body["processing_status"] == "PASS"
    assert body["validation"]["overall_status"] == "PASS"


def test_process_cash_flow_end_to_end(client):
    res = _upload(client, "sample_cash_flow.pdf", "cash_flow_statement")
    assert res.status_code == 200
    body = res.json()
    assert body["processing_status"] == "PASS"


def test_process_invoice_end_to_end(client):
    res = _upload(client, "sample_invoice.jpg", "invoice", content_type="image/jpeg")
    assert res.status_code == 200
    body = res.json()
    assert body["processing_status"] == "PASS"
    assert len(body["extracted_data"]["line_items"]) > 0


def test_process_unsupported_file_type(client):
    res = _upload(client, "unsupported.txt", "invoice", content_type="text/plain")
    assert res.status_code == 200
    body = res.json()
    assert body["processing_status"] == "FAILED"
    assert body["file_validation"]["status"] == "FAILED"


def test_process_empty_file(client):
    res = _upload(client, "empty.pdf", "invoice")
    body = res.json()
    assert body["processing_status"] == "FAILED"
    assert "empty" in body["file_validation"]["reason"].lower()


def test_process_invalid_document_type(client):
    path = FIXTURES_DIR / "sample_invoice.jpg"
    with open(path, "rb") as f:
        res = client.post(
            "/api/v1/documents/process",
            files={"file": ("sample_invoice.jpg", f, "image/jpeg")},
            data={"document_type": "not_a_real_type"},
        )
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "INVALID_DOCUMENT_TYPE"


def test_get_document_not_found(client):
    res = client.get("/api/v1/documents/does-not-exist.pdf")
    assert res.status_code == 404


def test_get_document_after_processing(client):
    _upload(client, "sample_balance_sheet.pdf", "balance_sheet")
    res = client.get("/api/v1/documents/sample_balance_sheet.pdf")
    assert res.status_code == 200
    assert res.json()["document_name"] == "sample_balance_sheet.pdf"


def test_list_documents(client):
    _upload(client, "sample_invoice.jpg", "invoice", content_type="image/jpeg")
    res = client.get("/api/v1/documents")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert isinstance(body["items"], list)


def test_dashboard_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
