"""
Data-access layer for processed documents. All persistence/database
access is isolated here — services never talk to SQLAlchemy directly.
"""
import json

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.document import ProcessedDocument
from app.schemas.extraction import DocumentProcessResult


def save_result(db: Session, result: DocumentProcessResult) -> ProcessedDocument:
    """Insert a new processed-document row (latest-wins is handled at read time)."""
    row = ProcessedDocument(
        document_name=result.document_name,
        document_type=result.document_type or "unknown",
        processing_status=result.processing_status,
        result_json=result.model_dump_json(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_latest_by_name(db: Session, document_name: str) -> ProcessedDocument | None:
    return (
        db.query(ProcessedDocument)
        .filter(ProcessedDocument.document_name == document_name)
        .order_by(desc(ProcessedDocument.created_at))
        .first()
    )


def list_documents(db: Session, limit: int = 200, offset: int = 0) -> tuple[list[ProcessedDocument], int]:
    query = db.query(ProcessedDocument).order_by(desc(ProcessedDocument.created_at))
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return items, total


def to_result(row: ProcessedDocument) -> dict:
    return json.loads(row.result_json)
