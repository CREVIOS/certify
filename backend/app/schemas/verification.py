"""Verification schemas."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.db.models import VerificationStatus, ValidationResult


class CitationSchema(BaseModel):
    """Citation schema."""
    source_document_id: UUID
    cited_text: str
    page_number: Optional[int] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    similarity_score: float
    context_before: Optional[str] = None
    context_after: Optional[str] = None


class VerifiedSentenceSchema(BaseModel):
    """Verified sentence schema."""
    id: UUID
    sentence_index: int
    content: str
    page_number: Optional[int] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    validation_result: ValidationResult
    confidence_score: Optional[float] = None
    reasoning: Optional[str] = None
    citations: List[CitationSchema] = []
    manually_reviewed: bool = False
    reviewer_notes: Optional[str] = None

    model_config = {"from_attributes": True}


class VerificationJobCreate(BaseModel):
    """Schema for creating a verification job."""
    project_id: UUID
    main_document_id: UUID


class VerificationJobResponse(BaseModel):
    """Schema for verification job response."""
    id: UUID
    project_id: UUID
    main_document_id: Optional[UUID] = None
    status: VerificationStatus
    progress: float = 0.0
    total_sentences: int = 0
    verified_sentences: int = 0
    validated_count: int = 0
    uncertain_count: int = 0
    incorrect_count: int = 0
    celery_task_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class VerificationJobDetail(VerificationJobResponse):
    """Detailed verification job schema with sentences."""
    sentences: List[VerifiedSentenceSchema] = []


class VerificationProgress(BaseModel):
    """Schema for verification progress updates."""
    job_id: UUID
    status: VerificationStatus
    progress: float
    current_sentence: int
    total_sentences: int
    message: str


class SentenceReview(BaseModel):
    """Schema for manual sentence review."""
    validation_result: ValidationResult
    reviewer_notes: Optional[str] = None
