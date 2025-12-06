"""
Pydantic schemas for Project API
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID

from app.schemas.document import DocumentResponse


class ProjectBase(BaseModel):
    """Base project schema"""
    name: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    background_context: Optional[str] = Field(None, max_length=10000)


class ProjectCreate(ProjectBase):
    """Schema for creating a new project"""
    pass


class ProjectUpdate(BaseModel):
    """Schema for updating a project"""
    name: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None
    background_context: Optional[str] = None


class ProjectResponse(ProjectBase):
    """Schema for project response"""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VerificationJobSummary(BaseModel):
    """Summary of verification job"""
    id: UUID
    status: str
    progress: float
    total_sentences: int
    verified_sentences: int
    validated_count: int
    uncertain_count: int
    incorrect_count: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ProjectDetail(ProjectResponse):
    """Detailed project view with statistics"""
    document_count: int
    main_document_count: int
    supporting_document_count: int
    verification_job_count: int


class ProjectWithStatsResponse(ProjectResponse):
    """Project with full statistics"""
    document_count: int
    main_document: Optional[DocumentResponse] = None
    supporting_documents: List[DocumentResponse] = []
    latest_job: Optional[VerificationJobSummary] = None


class PaginatedProjectsResponse(BaseModel):
    """Paginated list of projects"""
    items: List[ProjectWithStatsResponse]
    total: int
    page: int
    per_page: int
    pages: int
