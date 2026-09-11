"""Application-level exceptions mapped to controlled API error responses."""


class DocIntelError(Exception):
    """Base class for all handled application errors."""
    code = "INTERNAL_ERROR"
    http_status = 500

    def __init__(self, message: str, code: str | None = None, http_status: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if http_status:
            self.http_status = http_status


class UnsupportedFileTypeError(DocIntelError):
    code = "UNSUPPORTED_FILE_TYPE"
    http_status = 415


class EmptyFileError(DocIntelError):
    code = "EMPTY_FILE"
    http_status = 400


class CorruptedFileError(DocIntelError):
    code = "CORRUPTED_FILE"
    http_status = 400


class PageLimitExceededError(DocIntelError):
    code = "PAGE_LIMIT_EXCEEDED"
    http_status = 400


class OCRFailedError(DocIntelError):
    code = "OCR_FAILED"
    http_status = 422


class ExtractionFailedError(DocIntelError):
    code = "EXTRACTION_FAILED"
    http_status = 422


class DocumentNotFoundError(DocIntelError):
    code = "DOCUMENT_NOT_FOUND"
    http_status = 404
