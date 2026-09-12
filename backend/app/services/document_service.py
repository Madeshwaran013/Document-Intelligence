"""
Orchestrates the full pipeline described in case study section 1:

    Upload -> File Validation -> OCR/Text Extraction -> AI Extraction ->
    Structured JSON -> Financial Validation -> Status -> Persist

Each stage is delegated to its own service so responsibilities stay
separated (validation / OCR / extraction / financial validation /
persistence), per the mandatory repository structure.
"""
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.repositories import document_repository
from app.schemas.extraction import (
    DocumentProcessResult,
    ProcessingMetadata,
)
from app.services import (
    document_validation_service,
    extraction_service,
    financial_validation_service,
    ocr_service,
)
from app.utils.exceptions import OCRFailedError, ExtractionFailedError

logger = get_logger(__name__)


def process_document(
    db: Session,
    filename: str,
    content: bytes,
    declared_content_type: str | None,
    document_type: str,
) -> DocumentProcessResult:
    start = time.monotonic()
    logger.info("Processing document '%s' (declared type=%s)", filename, document_type)

    # 1. File validation (input-control layer, runs before anything else)
    file_validation = document_validation_service.validate_file(filename, content, declared_content_type)

    if file_validation.status == "FAILED":
        result = DocumentProcessResult(
            document_name=filename,
            document_type=document_type,
            processing_status="FAILED",
            file_validation=file_validation,
            extracted_data={},
            validation=None,
            processing_metadata=ProcessingMetadata(
                ocr_used=False, extraction_method=None,
                processed_at=datetime.now(timezone.utc),
                processing_time_ms=int((time.monotonic() - start) * 1000),
            ),
            errors=[file_validation.reason or "File validation failed."],
        )
        document_repository.save_result(db, result)
        return result

    # 2. Text extraction / OCR
    try:
        ocr_result = ocr_service.extract_text(filename, content, file_validation.file_type)
    except OCRFailedError as exc:
        result = _failed_result(filename, document_type, file_validation, [str(exc)], start,
                                 ocr_used=False, method=None)
        document_repository.save_result(db, result)
        return result

    # 3. AI-based field & table extraction
    try:
        extracted_data, method = extraction_service.extract_fields(document_type, ocr_result.pages)
    except ExtractionFailedError as exc:
        result = _failed_result(filename, document_type, file_validation, [str(exc)], start,
                                 ocr_used=ocr_result.ocr_used, method=None)
        document_repository.save_result(db, result)
        return result

    # 4. Financial calculation validation
    validation = financial_validation_service.validate(document_type, extracted_data)

    # Check if native extraction produced any fields
    has_any_value = any(
        (isinstance(v, dict) and v.get("value") not in (None, ""))
        or (isinstance(v, list) and len(v) > 0)
        for v in extracted_data.values()
    )

    # Fallback: If native PDF text yielded 0 extracted fields, force OCR rasterisation and retry extraction!
    if not has_any_value and not ocr_result.ocr_used and file_validation.file_type == "application/pdf":
        logger.info("Native PDF text layer yielded 0 fields for '%s'. Retrying with forced OCR...", filename)
        try:
            forced_ocr_result = ocr_service.force_ocr_pdf(content)
            if forced_ocr_result.pages and any(p.strip() for p in forced_ocr_result.pages):
                retry_data, retry_method = extraction_service.extract_fields(document_type, forced_ocr_result.pages)
                retry_has_value = any(
                    (isinstance(v, dict) and v.get("value") not in (None, ""))
                    or (isinstance(v, list) and len(v) > 0)
                    for v in retry_data.values()
                )
                if retry_has_value:
                    ocr_result = forced_ocr_result
                    extracted_data = retry_data
                    method = retry_method
                    has_any_value = True
                    # Re-run financial validation with the newly extracted data
                    validation = financial_validation_service.validate(document_type, extracted_data)
                    logger.info("Forced OCR fallback succeeded for '%s'", filename)
        except Exception as ocr_exc:  # noqa: BLE001
            logger.warning("Forced OCR fallback failed for '%s': %s", filename, ocr_exc)

    processing_status = "PASS" if has_any_value else "FAILED"

    result = DocumentProcessResult(
        document_name=filename,
        document_type=document_type,
        processing_status=processing_status,
        file_validation=file_validation,
        extracted_data=extracted_data,
        validation=validation,
        processing_metadata=ProcessingMetadata(
            ocr_used=ocr_result.ocr_used,
            ocr_provider=ocr_result.ocr_provider,
            extraction_method=method,
            processed_at=datetime.now(timezone.utc),
            processing_time_ms=int((time.monotonic() - start) * 1000),
        ),
        errors=[] if has_any_value else ["No fields could be extracted from the document."],
    )

    document_repository.save_result(db, result)
    logger.info("Finished processing '%s': status=%s validation=%s",
                filename, result.processing_status, validation.overall_status)
    return result


def _failed_result(filename, document_type, file_validation, errors, start, ocr_used, method):
    return DocumentProcessResult(
        document_name=filename,
        document_type=document_type,
        processing_status="FAILED",
        file_validation=file_validation,
        extracted_data={},
        validation=None,
        processing_metadata=ProcessingMetadata(
            ocr_used=ocr_used, extraction_method=method,
            processed_at=datetime.now(timezone.utc),
            processing_time_ms=int((time.monotonic() - start) * 1000),
        ),
        errors=errors,
    )
