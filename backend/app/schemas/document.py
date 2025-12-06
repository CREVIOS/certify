"""
Pydantic schemas for Document API
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel
from uuid import UUID


class DocumentResponse(BaseModel):
    """Document response schema"""
    id: UUID
    project_id: UUID
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    document_type: str
    page_count: Optional[int] = None
    indexed: bool
    indexed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document."""
    document_id: UUID
    filename: str
    file_size: int
    document_type: str
    task_id: str | None = None
    message: str


class DocumentUpdate(BaseModel):
    """Updatable fields for a document."""
    filename: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SectionSchema(BaseModel):
    """Lightweight section schema for IPO manual/AI sectioning."""
    title: str
    start_page: int
    end_page: int
    summary: Optional[str] = None


class SectionSuggestionResponse(BaseModel):
    """Response for AI section suggestions."""
    document_id: UUID
    sections: List[SectionSchema]
    model: str
