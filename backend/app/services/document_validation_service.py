"""
File-level input validation — the control layer that runs BEFORE any
OCR/AI extraction is attempted (case study section 4.1).

This purposefully does NOT try to classify or understand document
content; it only checks that the upload is a readable, supported,
non-empty, non-corrupted file within the page limit.
"""
import io

from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.extraction import FileValidation

logger = get_logger(__name__)

_EXT_TO_MIME = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


def _guess_content_type(filename: str, declared_content_type: str | None) -> str:
    if declared_content_type and declared_content_type in (
        "application/pdf", "image/jpeg", "image/png",
    ):
        return declared_content_type
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _EXT_TO_MIME.get(ext, declared_content_type or "application/octet-stream")


def validate_file(filename: str, content: bytes, declared_content_type: str | None) -> FileValidation:
    """Run all file-integrity checks and return a FileValidation result.

    Never raises for expected failure modes — callers should inspect
    ``status`` (PASS/FAILED) and ``reason``.
    """
    settings = get_settings()
    content_type = _guess_content_type(filename, declared_content_type)

    if not content:
        logger.warning("Rejected empty upload: %s", filename)
        return FileValidation(
            file_type=content_type, is_supported=content_type in settings.ALLOWED_CONTENT_TYPES,
            is_readable=False, page_count=0, status="FAILED", reason="Uploaded file is empty.",
        )

    if content_type not in settings.ALLOWED_CONTENT_TYPES:
        logger.warning("Rejected unsupported file type '%s' for %s", content_type, filename)
        return FileValidation(
            file_type=content_type, is_supported=False, is_readable=False,
            page_count=None, status="FAILED",
            reason="Only PDF / JPG / PNG documents are supported.",
        )

    if content_type == "application/pdf":
        return _validate_pdf(content_type, content, settings.MAX_PAGE_COUNT)
    else:
        return _validate_image(content_type, content)


def _validate_pdf(content_type: str, content: bytes, max_pages: int) -> FileValidation:
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                logger.warning("Rejected encrypted/password-protected PDF")
                return FileValidation(
                    file_type=content_type, is_supported=True, is_readable=False,
                    page_count=None, status="FAILED",
                    reason="PDF is password-protected and cannot be read.",
                )
        page_count = len(reader.pages)
    except (PdfReadError, Exception) as exc:  # noqa: BLE001 - deliberately broad, file may be arbitrary garbage
        logger.warning("Rejected corrupted PDF: %s", exc)
        return FileValidation(
            file_type=content_type, is_supported=True, is_readable=False,
            page_count=None, status="FAILED", reason="PDF file is corrupted or unreadable.",
        )

    if page_count == 0:
        return FileValidation(
            file_type=content_type, is_supported=True, is_readable=False,
            page_count=0, status="FAILED", reason="PDF contains no pages.",
        )

    if page_count > max_pages:
        logger.warning("Rejected PDF exceeding page limit: %d pages", page_count)
        return FileValidation(
            file_type=content_type, is_supported=True, is_readable=True,
            page_count=page_count, status="FAILED",
            reason=f"Document has {page_count} pages; maximum supported is {max_pages}.",
        )

    return FileValidation(
        file_type=content_type, is_supported=True, is_readable=True,
        page_count=page_count, status="PASS",
    )


def _validate_image(content_type: str, content: bytes) -> FileValidation:
    try:
        image = Image.open(io.BytesIO(content))
        image.verify()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rejected corrupted image: %s", exc)
        return FileValidation(
            file_type=content_type, is_supported=True, is_readable=False,
            page_count=None, status="FAILED", reason="Image file is corrupted or unreadable.",
        )

    return FileValidation(
        file_type=content_type, is_supported=True, is_readable=True,
        page_count=1, status="PASS",
    )
