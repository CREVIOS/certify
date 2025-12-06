"""
Verified Sentences API endpoints
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import VerifiedSentence, VerificationJob, ValidationResult, Project
from app.services.excel_export import ExcelExportService
from app.schemas.sentences import VerifiedSentenceResponse

router = APIRouter(prefix="/sentences", tags=["sentences"])


class SentenceReviewUpdate(BaseModel):
    """Schema for updating sentence review"""
    manually_reviewed: bool
    reviewer_notes: Optional[str] = None


class CitationResponse(BaseModel):
    """Citation response"""
    doc_id: str
    doc_name: str
    page: int
    excerpt: str
    match_score: float
    context_before: Optional[str] = None
    context_after: Optional[str] = None


class SentenceResponse(BaseModel):
    """Verified sentence response"""
    id: str
    verification_job_id: str
    sentence_index: int
    content: str
    page_number: Optional[int]
    start_char: Optional[int]
    end_char: Optional[int]
    validation_result: str
    confidence_score: Optional[float]
    reasoning: Optional[str]
    citations: list
    manually_reviewed: bool
    reviewer_notes: Optional[str]
    created_at: str
    updated_at: str


class PaginatedSentencesResponse(BaseModel):
    """Paginated sentences response"""
    items: list[SentenceResponse]
    total: int
    page: int
    per_page: int
    pages: int


@router.get("/jobs/{job_id}/sentences", response_model=PaginatedSentencesResponse)
async def get_sentences_by_job(
    job_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Get sentences for a verification job with optional status filter
    """
    # Validate job exists
    job_result = await db.execute(select(VerificationJob).where(VerificationJob.id == job_id))
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Verification job not found")

    # Build query
    query = select(VerifiedSentence).where(VerifiedSentence.verification_job_id == job_id)

    # Apply status filter
    if status:
        try:
            validation_result = ValidationResult(status)
            query = query.where(VerifiedSentence.validation_result == validation_result)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * per_page
    query = query.order_by(VerifiedSentence.sentence_index).offset(offset).limit(per_page)

    result = await db.execute(query)
    sentences = result.scalars().all()

    # Build response
    items = [
        SentenceResponse(
            id=str(s.id),
            verification_job_id=str(s.verification_job_id),
            sentence_index=s.sentence_index,
            content=s.content,
            page_number=s.page_number,
            start_char=s.start_char,
            end_char=s.end_char,
            validation_result=s.validation_result.value,
            confidence_score=s.confidence_score,
            reasoning=s.reasoning,
            citations=s.citations or [],
            manually_reviewed=s.manually_reviewed,
            reviewer_notes=s.reviewer_notes,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat()
        )
        for s in sentences
    ]

    pages = (total + per_page - 1) // per_page

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages
    }


@router.get("/{sentence_id}", response_model=SentenceResponse)
async def get_sentence(
    sentence_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a single verified sentence by ID
    """
    result = await db.execute(
        select(VerifiedSentence).where(VerifiedSentence.id == sentence_id)
    )
    sentence = result.scalar_one_or_none()

    if not sentence:
        raise HTTPException(status_code=404, detail="Sentence not found")

    return SentenceResponse(
        id=str(sentence.id),
        verification_job_id=str(sentence.verification_job_id),
        sentence_index=sentence.sentence_index,
        content=sentence.content,
        page_number=sentence.page_number,
        start_char=sentence.start_char,
        end_char=sentence.end_char,
        validation_result=sentence.validation_result.value,
        confidence_score=sentence.confidence_score,
        reasoning=sentence.reasoning,
        citations=sentence.citations or [],
        manually_reviewed=sentence.manually_reviewed,
        reviewer_notes=sentence.reviewer_notes,
        created_at=sentence.created_at.isoformat(),
        updated_at=sentence.updated_at.isoformat()
    )


@router.put("/{sentence_id}/review", response_model=SentenceResponse)
async def update_sentence_review(
    sentence_id: UUID,
    review: SentenceReviewUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update manual review status for a sentence
    """
    result = await db.execute(
        select(VerifiedSentence).where(VerifiedSentence.id == sentence_id)
    )
    sentence = result.scalar_one_or_none()

    if not sentence:
        raise HTTPException(status_code=404, detail="Sentence not found")

    # Update review fields
    sentence.manually_reviewed = review.manually_reviewed
    if review.reviewer_notes is not None:
        sentence.reviewer_notes = review.reviewer_notes

    await db.commit()
    await db.refresh(sentence)

    return SentenceResponse(
        id=str(sentence.id),
        verification_job_id=str(sentence.verification_job_id),
        sentence_index=sentence.sentence_index,
        content=sentence.content,
        page_number=sentence.page_number,
        start_char=sentence.start_char,
        end_char=sentence.end_char,
        validation_result=sentence.validation_result.value,
        confidence_score=sentence.confidence_score,
        reasoning=sentence.reasoning,
        citations=sentence.citations or [],
        manually_reviewed=sentence.manually_reviewed,
        reviewer_notes=sentence.reviewer_notes,
        created_at=sentence.created_at.isoformat(),
        updated_at=sentence.updated_at.isoformat()
    )


@router.get("/projects/{project_id}/search", response_model=PaginatedSentencesResponse)
async def search_sentences(
    project_id: UUID,
    q: str = Query(..., min_length=3, description="Search query"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    Full-text search for sentences within a project
    """
    # Get all verification jobs for this project
    jobs_result = await db.execute(
        select(VerificationJob.id).where(VerificationJob.project_id == project_id)
    )
    job_ids = [row[0] for row in jobs_result.fetchall()]

    if not job_ids:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "per_page": per_page,
            "pages": 0
        }

    # Full-text search query
    search_term = q.strip()
    query = select(VerifiedSentence).where(
        and_(
            VerifiedSentence.verification_job_id.in_(job_ids),
            VerifiedSentence.content.ilike(f"%{search_term}%")
        )
    )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * per_page
    query = query.order_by(VerifiedSentence.sentence_index).offset(offset).limit(per_page)

    result = await db.execute(query)
    sentences = result.scalars().all()

    # Build response
    items = [
        SentenceResponse(
            id=str(s.id),
            verification_job_id=str(s.verification_job_id),
            sentence_index=s.sentence_index,
            content=s.content,
            page_number=s.page_number,
            start_char=s.start_char,
            end_char=s.end_char,
            validation_result=s.validation_result.value,
            confidence_score=s.confidence_score,
            reasoning=s.reasoning,
            citations=s.citations or [],
            manually_reviewed=s.manually_reviewed,
            reviewer_notes=s.reviewer_notes,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat()
        )
        for s in sentences
    ]

    pages = (total + per_page - 1) // per_page

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages
    }

@router.get("/jobs/{job_id}/export")
async def export_verification_results(
    job_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Export verification results to Excel
    
    Returns Excel file with all sentence details: source name, sentence,
    context, citations, AI reasoning, confidence scores, etc.
    """
    # Get verification job with project
    job_query = select(VerificationJob).where(VerificationJob.id == job_id)
    result = await db.execute(job_query)
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Verification job not found")
    
    # Get project name
    project_query = select(Project).where(Project.id == job.project_id)
    project_result = await db.execute(project_query)
    project = project_result.scalar_one_or_none()
    project_name = project.name if project else "Unknown Project"
    
    # Get all verified sentences for this job
    query = (
        select(VerifiedSentence)
        .where(VerifiedSentence.verification_job_id == job_id)
        .order_by(VerifiedSentence.page_number, VerifiedSentence.sentence_index)
    )
    
    result = await db.execute(query)
    sentences = result.scalars().all()
    
    if not sentences:
        raise HTTPException(status_code=404, detail="No verification results found")
    
    # Convert to response models
    sentence_responses = []
    for s in sentences:
        sentence_responses.append(
            VerifiedSentenceResponse(
                id=str(s.id),
                verification_job_id=str(s.verification_job_id),
                sentence_index=s.sentence_index,
                content=s.content,
                page_number=s.page_number,
                start_char=s.start_char,
                end_char=s.end_char,
                context_before=s.context_before,
                context_after=s.context_after,
                status=s.validation_result,
                confidence_score=s.confidence_score or 0.0,
                ai_reasoning=s.reasoning,
                citations=s.citations or [],
                metadata=s.metadata or {},
                manually_reviewed=s.manually_reviewed,
                reviewer_notes=s.reviewer_notes,
                created_at=s.created_at,
                updated_at=s.updated_at
            )
        )
    
    # Generate Excel file
    excel_file = ExcelExportService.export_verification_results(
        sentences=sentence_responses,
        project_name=project_name
    )
    
    # Return as streaming response
    filename = f"{project_name.replace(' ', '_')}_verification_results.xlsx"
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
