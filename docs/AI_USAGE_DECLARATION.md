# AI Usage Declaration

Transparency on how AI tools were used to build this submission, as
requested by the case study.

## Building this project

- **Claude (Anthropic)**, via Claude's agentic coding environment, was used
  to design the architecture, write the backend (FastAPI services, OCR
  pipeline, heuristic extractors, financial validation logic, tests), the
  frontend (HTML/CSS/JS dashboard), and this documentation.
- The dataset (`New_Dataset_1.zip`) was inspected first (rendering sample
  PDFs/images to view their actual layout) before designing the extraction
  and validation logic, so the field names and validation formulas match
  what's genuinely present in the provided documents (e.g. the bank-style
  Balance Sheet / P&L / Cash Flow layout, confirmed against the exact
  formulas given in the case study brief).
- All code was iteratively run and tested against the real sample dataset
  (not just written and assumed correct) — see `sample_outputs/` for
  genuine pipeline output, and `backend/tests/` for the automated test
  suite (32 tests, all passing at time of submission).

## AI usage inside the running application itself

- **Document field/table extraction** (`app/services/extraction_service.py`)
  optionally uses an LLM (Claude, model `claude-sonnet-4-6`, via the
  Anthropic Messages API) to read the OCR'd/extracted document text and
  return structured JSON fields. This path is only active when
  `ANTHROPIC_API_KEY` is configured — the case study allows any available
  LLM/model, and Claude was used here since it was the most convenient
  API to integrate with in this environment.
  - The prompt explicitly instructs the model to **never invent or infer
    values** — any field not present in the source text must be returned
    as `null` — and to cite a `page_number` and `source_text` snippet for
    every value it does return, so extracted data stays traceable back to
    the document.
- When no API key is configured, the same extraction interface falls back
  automatically to a **zero-dependency heuristic extractor** (regex/rules,
  `app/services/heuristics/`), so the application is fully functional,
  testable, and demoable without requiring any external AI service or
  credentials. `processing_metadata.extraction_method` in every API
  response reports which of the two paths was actually used for that
  document.
- OCR itself (Tesseract, `app/services/ocr_service.py`) is a traditional
  (non-LLM) open-source OCR engine, not an AI/LLM call — used to obtain the
  raw text that either extraction path then works from.

## What was NOT AI-generated

- The dataset itself (provided by NeoStats).
- The case study requirements and validation formulas (provided by
  NeoStats — implemented as specified, not invented).
