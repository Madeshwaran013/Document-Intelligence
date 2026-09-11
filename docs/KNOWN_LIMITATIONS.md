# Known Limitations

Honest account of current gaps, so they're not mistaken for bugs.

## Heuristic (no-API-key) extraction path

- **Multi-column layouts** (e.g. side-by-side "Bill From" / "Bill To"
  blocks in invoices) can get interleaved by OCR reading order. The
  heuristic extractor does simple top-to-bottom line parsing, so it
  sometimes cannot cleanly separate two side-by-side text blocks that
  Tesseract read as one merged line. The LLM extraction path (enable with
  `ANTHROPIC_API_KEY`) handles this correctly because it reasons over the
  full page text rather than pattern-matching lines.
- **Invoice line-item parsing** assumes each row ends in
  `quantity, unit_price, amount` on one line. Wrapped/multi-line
  descriptions are merged with a simple "previous line" heuristic, which
  works for the common case but isn't a general table-layout parser.
- Statement **section detection** relies on recognizing a small set of
  known section header keywords (INCOME, EXPENDITURE, ASSETS, etc.). A
  statement using different section headings than the ones in the sample
  dataset would need those keywords added to
  `app/services/heuristics/financial_statement_extractor.py`.

## OCR

- OCR quality depends on scan/image resolution; very low-quality scans or
  handwriting are not reliably read by Tesseract. No handwriting-specific
  OCR model is used.
- PDFs are rasterised at 200 DPI for OCR — sufficient for the sample
  dataset, but embedded fonts/very small print could still be misread.

## Financial validation

- Reconciliation checks use a configurable tolerance (default 1% relative
  / 1.0 absolute currency unit) to absorb rounding in source documents.
  This is a judgment call — tightening or loosening it is a one-line
  config change (`VALIDATION_RELATIVE_TOLERANCE` /
  `VALIDATION_ABSOLUTE_TOLERANCE` in `.env`).
- Validation formulas implemented are exactly the ones specified in the
  case study brief for each of the 4 document types. Documents with
  additional line items outside those formulas (e.g. an invoice with a
  shipping/handling charge not covered by
  `subtotal + tax - discount = total`) will correctly surface as a
  `FAIL` on that specific check — this is by design (see
  `sample_outputs/05_invoice_validation_failure_sample.json`), not a bug.

## Persistence & scale

- Default storage is SQLite, chosen for zero-setup local/demo use. It is
  not intended for concurrent high-throughput production use — swap
  `DATABASE_URL` to Postgres/MySQL for that (no code changes required,
  see README).
- `GET /api/v1/documents/{document_name}` returns the **latest** processed
  result for that filename; re-uploading a file with the same name creates
  a new row rather than overwriting, and history isn't exposed via a
  dedicated endpoint yet.

## Not implemented (out of scope for this submission)

- Authentication/authorization on the API (not requested by the brief).
- Async/background job processing for very large batches — processing is
  synchronous per request, which is fine for the ≤3-page documents this
  service is designed for.
- A dedicated "diff view" comparing two processed versions of the same
  document.
