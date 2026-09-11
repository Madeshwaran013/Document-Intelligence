"""
Pydantic schemas describing the structured extraction/validation output.

These mirror the mandatory response contract in the case study (section
5.2) exactly: every extracted field is a {value, confidence?, page_number}
object, missing values are null, and validation checks carry the
formula/operands/calculated/reported/variance/status tuple.
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

DocumentType = Literal[
    "invoice", "balance_sheet", "profit_and_loss", "cash_flow_statement"
]
CheckStatus = Literal["PASS", "FAIL", "NOT_APPLICABLE"]
ProcessingStatus = Literal["PASS", "FAILED"]


class FieldValue(BaseModel):
    """A single extracted field with optional evidence/confidence."""
    value: Optional[Any] = None
    confidence: Optional[float] = None
    source_text: Optional[str] = None
    page_number: Optional[int] = None


class LineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class StatementLineItem(BaseModel):
    """A generic (label, value-per-period) row for financial statements."""
    label: str
    values: Dict[str, Optional[float]] = Field(default_factory=dict)
    page_number: Optional[int] = None
    source_text: Optional[str] = None


class FileValidation(BaseModel):
    file_type: Optional[str] = None
    is_supported: bool
    is_readable: bool
    page_count: Optional[int] = None
    status: Literal["PASS", "FAILED"]
    reason: Optional[str] = None


class ValidationCheck(BaseModel):
    name: str
    formula: str
    operands: Dict[str, Optional[float]]
    calculated_value: Optional[float] = None
    reported_value: Optional[float] = None
    variance: Optional[float] = None
    status: CheckStatus
    period: Optional[str] = None
    note: Optional[str] = None


class ValidationResult(BaseModel):
    checks: List[ValidationCheck] = Field(default_factory=list)
    overall_status: CheckStatus = "NOT_APPLICABLE"
    issues: List[str] = Field(default_factory=list)


class ProcessingMetadata(BaseModel):
    ocr_used: bool = False
    ocr_provider: Optional[str] = None
    extraction_method: Optional[str] = None  # "llm" | "heuristic"
    processed_at: datetime
    processing_time_ms: int


class DocumentProcessResult(BaseModel):
    document_name: str
    document_type: Optional[str] = None
    processing_status: ProcessingStatus
    overall_confidence: Optional[float] = None
    file_validation: FileValidation
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    validation: Optional[ValidationResult] = None
    processing_metadata: Optional[ProcessingMetadata] = None
    errors: List[str] = Field(default_factory=list)


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
