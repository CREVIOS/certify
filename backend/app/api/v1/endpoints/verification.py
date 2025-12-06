"""Verification endpoints."""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from loguru import logger

from app.db.session import get_db
from app.db.models import (
    VerificationJob, Project, Document, VerifiedSentence,
    VerificationStatus, DocumentType
)
from app.schemas.verification import (
    VerificationJobCreate, VerificationJobResponse, VerificationJobDetail,
    VerifiedSentenceSchema, SentenceReview
)
from app.tasks.verification_tasks import run_verification_task

router = APIRouter()


@router.post("/jobs", response_model=VerificationJobResponse, status_code=status.HTTP_201_CREATED)
async def create_verification_job(
    job_data: VerificationJobCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new verification job."""
    try:
        # Verify project exists
        result = await db.execute(
            select(Project).where(Project.id == job_data.project_id)
        )
        project = result.scalar_one_or_none()

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        # Verify main document exists and is of type MAIN
        result = await db.execute(
            select(Document).where(Document.id == job_data.main_document_id)
        )
        main_doc = result.scalar_one_or_none()

        if not main_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Main document not found"
            )

        if main_doc.document_type != DocumentType.MAIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document must be of type MAIN"
            )

        # Check if project has indexed supporting documents
        result = await db.execute(
            select(Document).where(
                Document.project_id == job_data.project_id,
                Document.document_type == DocumentType.SUPPORTING,
                Document.indexed == True
            )
        )
        supporting_docs = result.scalars().all()

        if not supporting_docs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project must have at least one indexed supporting document"
            )

        # Create verification job
        job = VerificationJob(
            project_id=job_data.project_id,
            main_document_id=job_data.main_document_id,
            status=VerificationStatus.PENDING
        )

        db.add(job)
        await db.commit()
        await db.refresh(job)

        logger.info(f"Created verification job {job.id}")

        return job

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating verification job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating verification job: {str(e)}"
        )


@router.post("/jobs/{job_id}/start", status_code=status.HTTP_202_ACCEPTED)
async def start_verification_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Start a verification job."""
    try:
        result = await db.execute(
            select(VerificationJob).where(VerificationJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification job not found"
            )

        if job.status != VerificationStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job is already {job.status.value}"
            )

        # Trigger Celery task
        task = run_verification_task.delay(str(job_id))

        # Update job with task ID
        job.celery_task_id = task.id
        await db.commit()

        logger.info(f"Started verification job {job_id}: {task.id}")

        return {
            "message": "Verification job started",
            "job_id": str(job_id),
            "task_id": task.id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting verification job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting verification job: {str(e)}"
        )


@router.get("/jobs/{job_id}", response_model=VerificationJobDetail)
async def get_verification_job(
    job_id: UUID,
    include_sentences: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Get verification job details with sentences."""
    try:
        # Build query
        query = select(VerificationJob).where(VerificationJob.id == job_id)

        if include_sentences:
            query = query.options(selectinload(VerificationJob.sentences))

        result = await db.execute(query)
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification job not found"
            )

        # Convert to response model
        job_dict = {
            "id": job.id,
            "project_id": job.project_id,
            "main_document_id": job.main_document_id,
            "status": job.status,
            "progress": job.progress,
            "total_sentences": job.total_sentences,
            "verified_sentences": job.verified_sentences,
            "validated_count": job.validated_count,
            "uncertain_count": job.uncertain_count,
            "incorrect_count": job.incorrect_count,
            "celery_task_id": job.celery_task_id,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "error_message": job.error_message,
            "sentences": []
        }

        if include_sentences and job.sentences:
            # Convert sentences with citations
            for sentence in job.sentences:
                sentence_dict = {
                    "id": sentence.id,
                    "sentence_index": sentence.sentence_index,
                    "content": sentence.content,
                    "page_number": sentence.page_number,
                    "start_char": sentence.start_char,
                    "end_char": sentence.end_char,
                    "validation_result": sentence.validation_result,
                    "confidence_score": sentence.confidence_score,
                    "reasoning": sentence.reasoning,
                    "citations": sentence.citations or [],
                    "manually_reviewed": sentence.manually_reviewed,
                    "reviewer_notes": sentence.reviewer_notes
                }
                job_dict["sentences"].append(sentence_dict)

        return VerificationJobDetail(**job_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting verification job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting verification job: {str(e)}"
        )


@router.get("/jobs/project/{project_id}", response_model=List[VerificationJobResponse])
async def list_project_verification_jobs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all verification jobs for a project."""
    try:
        result = await db.execute(
            select(VerificationJob)
            .where(VerificationJob.project_id == project_id)
            .order_by(VerificationJob.created_at.desc())
        )
        jobs = result.scalars().all()
        return jobs

    except Exception as e:
        logger.error(f"Error listing verification jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing verification jobs: {str(e)}"
        )


@router.get("/sentences/{sentence_id}", response_model=VerifiedSentenceSchema)
async def get_verified_sentence(
    sentence_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get details of a verified sentence with citations."""
    try:
        result = await db.execute(
            select(VerifiedSentence).where(VerifiedSentence.id == sentence_id)
        )
        sentence = result.scalar_one_or_none()

        if not sentence:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verified sentence not found"
            )

        # Build response
        sentence_dict = {
            "id": sentence.id,
            "sentence_index": sentence.sentence_index,
            "content": sentence.content,
            "page_number": sentence.page_number,
            "start_char": sentence.start_char,
            "end_char": sentence.end_char,
            "validation_result": sentence.validation_result,
            "confidence_score": sentence.confidence_score,
            "reasoning": sentence.reasoning,
            "citations": sentence.citations or [],
            "manually_reviewed": sentence.manually_reviewed,
            "reviewer_notes": sentence.reviewer_notes
        }

        return VerifiedSentenceSchema(**sentence_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting verified sentence: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting verified sentence: {str(e)}"
        )


@router.patch("/sentences/{sentence_id}/review", response_model=VerifiedSentenceSchema)
async def review_sentence(
    sentence_id: UUID,
    review_data: SentenceReview,
    db: AsyncSession = Depends(get_db)
):
    """Manually review and update a verified sentence."""
    try:
        result = await db.execute(
            select(VerifiedSentence).where(VerifiedSentence.id == sentence_id)
        )
        sentence = result.scalar_one_or_none()

        if not sentence:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verified sentence not found"
            )

        # Update review
        sentence.validation_result = review_data.validation_result
        sentence.manually_reviewed = True
        if review_data.reviewer_notes:
            sentence.reviewer_notes = review_data.reviewer_notes

        await db.commit()
        await db.refresh(sentence)

        logger.info(f"Reviewed sentence {sentence_id}")

        # Build response
        sentence_dict = {
            "id": sentence.id,
            "sentence_index": sentence.sentence_index,
            "content": sentence.content,
            "page_number": sentence.page_number,
            "start_char": sentence.start_char,
            "end_char": sentence.end_char,
            "validation_result": sentence.validation_result,
            "confidence_score": sentence.confidence_score,
            "reasoning": sentence.reasoning,
            "citations": sentence.citations or [],
            "manually_reviewed": sentence.manually_reviewed,
            "reviewer_notes": sentence.reviewer_notes
        }

        return VerifiedSentenceSchema(**sentence_dict)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error reviewing sentence: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reviewing sentence: {str(e)}"
        )


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_verification_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a verification job."""
    try:
        result = await db.execute(
            select(VerificationJob).where(VerificationJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification job not found"
            )

        # Delete job (cascades to sentences)
        await db.delete(job)
        await db.commit()

        logger.info(f"Deleted verification job {job_id}")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting verification job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting verification job: {str(e)}"
        )
