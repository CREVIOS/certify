"""
Pydantic schemas for Document API
"""

from typing import Optional, Dict, Any
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
