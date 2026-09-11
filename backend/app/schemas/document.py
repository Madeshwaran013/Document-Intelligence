from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    """Row shown in the dashboard / GET /api/v1/documents list."""
    id: str
    document_name: str
    document_type: str
    processing_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentSummary]
