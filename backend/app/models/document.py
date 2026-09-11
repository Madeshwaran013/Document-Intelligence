"""
Persistence model for processed documents.

We store the full structured result as JSON alongside a handful of
promoted columns (name, type, status, timestamp) so the dashboard/list
endpoint can query cheaply without deserialising every row.
"""
import uuid

from sqlalchemy import Column, DateTime, String, Text, func

from app.core.database import Base


class ProcessedDocument(Base):
    __tablename__ = "processed_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_name = Column(String(512), nullable=False, index=True)
    document_type = Column(String(64), nullable=False, index=True)
    processing_status = Column(String(16), nullable=False, index=True)  # PASS | FAILED
    result_json = Column(Text, nullable=False)  # full structured response, JSON-encoded
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
