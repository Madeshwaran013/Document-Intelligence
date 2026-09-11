"""
Mandatory REST API (case study section 5).
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.repositories import document_repository
from app.schemas.document import DocumentListResponse, DocumentSummary
from app.services.document_service import process_document
from app.utils.exceptions import DocIntelError

router = APIRouter(prefix="/api/v1", tags=["documents"])
logger = get_logger(__name__)

VALID_DOCUMENT_TYPES = {"invoice", "balance_sheet", "profit_and_loss", "cash_flow_statement"}


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "document-intelligence-platform"}


@router.post("/documents/process")
async def process_document_endpoint(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    db: Session = Depends(get_db),
):
    if document_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail={"error": {
                "code": "INVALID_DOCUMENT_TYPE",
                "message": f"document_type must be one of {sorted(VALID_DOCUMENT_TYPES)}.",
            }},
        )

    try:
        content = await file.read()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to read upload")
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "UPLOAD_READ_FAILED", "message": "Could not read the uploaded file."}},
        ) from exc

    try:
        result = process_document(
            db=db, filename=file.filename or "uploaded_document",
            content=content, declared_content_type=file.content_type,
            document_type=document_type,
        )
    except DocIntelError as exc:
        logger.warning("Controlled processing error: %s", exc.message)
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while processing document")
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred while processing the document."}},
        )

    return result.model_dump(mode="json")


@router.get("/documents/{document_name}")
def get_document(document_name: str, db: Session = Depends(get_db)):
    row = document_repository.get_latest_by_name(db, document_name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "DOCUMENT_NOT_FOUND",
                               "message": f"No processed result found for '{document_name}'."}},
        )
    return document_repository.to_result(row)


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(limit: int = 200, offset: int = 0, db: Session = Depends(get_db)):
    rows, total = document_repository.list_documents(db, limit=limit, offset=offset)
    return DocumentListResponse(
        total=total,
        items=[DocumentSummary.model_validate(r) for r in rows],
    )
