# Sample Outputs

These are **real outputs** produced by actually running the pipeline (via
`POST /api/v1/documents/process`) against documents in `New_Dataset_1.zip`,
using the built-in heuristic extractor (no LLM API key was configured when
these were generated — see `docs/AI_USAGE_DECLARATION.md`). Setting
`ANTHROPIC_API_KEY` will route extraction through Claude instead and
typically improves accuracy further.

| File | Scenario |
|---|---|
| `01_invoice_sample.json` | Invoice processed successfully — fields, line items extracted |
| `02_balance_sheet_sample.json` | Balance sheet — **all financial checks PASS** (Total Assets = Total Capital & Liabilities, section sums reconcile) |
| `03_profit_and_loss_sample.json` | P&L — **all 5 formula checks PASS** end-to-end (Income → Expenditure → Net Profit → Appropriation chain) |
| `04_cash_flow_sample.json` | Cash flow statement — **both checks PASS** (operating+investing+financing+FX = net increase; opening + net increase = closing) |
| `05_invoice_validation_failure_sample.json` | Same invoice as #1 — included again to highlight the **validation FAILURE**: `subtotal + tax - discount ≈ total` fails because the source invoice includes an "S&H" (shipping & handling) charge not covered by the required formula. This demonstrates the system correctly flags a genuine reconciliation issue rather than silently passing. |
| `06_unsupported_file_type_error.json` | File validation failure — `.txt` upload rejected before OCR/extraction ever runs |
| `07_empty_file_error.json` | File validation failure — zero-byte upload rejected |
| `08_invalid_document_type_error.json` | Request-level error — invalid `document_type` form value (HTTP 400, structured `error` object) |

All outputs were generated on **10 September 2026** by uploading the
corresponding file from the provided dataset to a locally running instance
of this service.
