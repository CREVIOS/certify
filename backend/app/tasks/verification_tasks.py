"""Celery tasks for document verification."""

from uuid import UUID
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import asyncio
from datetime import datetime

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.services.document_processor import DocumentProcessor
from app.services.verification_service import verification_service
from app.db.models import (
    VerificationJob, Document, Project, VerifiedSentence,
    VerificationStatus, ValidationResult
)


def get_async_session():
    """Create async database session for Celery tasks."""
    DATABASE_URL = settings.DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://')
    engine = create_async_engine(DATABASE_URL)
    return AsyncSession(engine)


@celery_app.task(bind=True, name='run_verification')
def run_verification_task(self, verification_job_id: str):
    """
    Run verification job to verify all sentences in main document.

    Args:
        verification_job_id: Verification job UUID
    """
    try:
        logger.info(f"Starting verification job {verification_job_id}")

        # Run async task
        result = asyncio.run(
            _run_verification_async(
                UUID(verification_job_id),
                self.request.id
            )
        )

        logger.info(f"Successfully completed verification job {verification_job_id}")
        return result

    except Exception as e:
        logger.error(f"Error in verification job {verification_job_id}: {e}")

        # Update job status to failed
        asyncio.run(_update_job_status(
            UUID(verification_job_id),
            VerificationStatus.FAILED,
            error_message=str(e)
        ))
        raise


async def _run_verification_async(job_id: UUID, task_id: str):
    """Async implementation of verification job."""
    async with get_async_session() as session:
        try:
            # Get verification job
            result = await session.execute(
                select(VerificationJob).where(VerificationJob.id == job_id)
            )
            job = result.scalar_one_or_none()

            if not job:
                raise ValueError(f"Verification job {job_id} not found")

            # Update status to processing
            job.status = VerificationStatus.PROCESSING
            job.started_at = datetime.utcnow()
            job.celery_task_id = task_id
            await session.commit()

            # Get main document
            result = await session.execute(
                select(Document).where(Document.id == job.main_document_id)
            )
            main_doc = result.scalar_one_or_none()

            if not main_doc:
                raise ValueError(f"Main document {job.main_document_id} not found")

            # Get project for context
            result = await session.execute(
                select(Project).where(Project.id == job.project_id)
            )
            project = result.scalar_one_or_none()

            # Process main document to extract sentences
            processor = DocumentProcessor()
            processed = await processor.process_document_for_verification(main_doc.file_path)
            sentences = processed["sentences"]

            # Update total count
            job.total_sentences = len(sentences)
            await session.commit()

            # Verify sentences in batches
            batch_size = settings.VERIFICATION_BATCH_SIZE
            validated_count = 0
            uncertain_count = 0
            incorrect_count = 0

            for i in range(0, len(sentences), batch_size):
                batch = sentences[i:i + batch_size]

                for sentence_data in batch:
                    try:
                        # Verify sentence
                        verification_result = await verification_service.verify_sentence(
                            sentence=sentence_data["content"],
                            project_id=job.project_id,
                            context=project.background_context if project else ""
                        )

                        # Create verified sentence record
                        verified_sentence = VerifiedSentence(
                            verification_job_id=job_id,
                            sentence_index=sentence_data["index"],
                            content=sentence_data["content"],
                            page_number=sentence_data.get("page_number"),
                            start_char=sentence_data.get("start_char"),
                            end_char=sentence_data.get("end_char"),
                            validation_result=verification_result["validation_result"],
                            confidence_score=verification_result.get("confidence_score"),
                            reasoning=verification_result.get("reasoning"),
                            citations=verification_result.get("citations", [])
                        )

                        session.add(verified_sentence)

                        # Update counts
                        if verification_result["validation_result"] == ValidationResult.VALIDATED:
                            validated_count += 1
                        elif verification_result["validation_result"] == ValidationResult.UNCERTAIN:
                            uncertain_count += 1
                        elif verification_result["validation_result"] == ValidationResult.INCORRECT:
                            incorrect_count += 1

                        # Update progress
                        job.verified_sentences = i + len(batch)
                        job.progress = (job.verified_sentences / job.total_sentences) * 100
                        job.validated_count = validated_count
                        job.uncertain_count = uncertain_count
                        job.incorrect_count = incorrect_count

                        await session.commit()

                        logger.info(
                            f"Verified sentence {sentence_data['index'] + 1}/{len(sentences)}: "
                            f"{verification_result['validation_result'].value}"
                        )

                        # Send real-time update via WebSocket
                        await send_verification_progress(
                            job_id=job_id,
                            status=VerificationStatus.PROCESSING,
                            progress=job.progress,
                            current_sentence=job.verified_sentences,
                            total_sentences=job.total_sentences
                        )

                    except Exception as e:
                        logger.error(f"Error verifying sentence {sentence_data['index']}: {e}")
                        # Continue with next sentence

            # Mark job as completed
            job.status = VerificationStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.progress = 100.0
            await session.commit()

            # Send completion update
            await send_verification_progress(
                job_id=job_id,
                status=VerificationStatus.COMPLETED,
                progress=100.0,
                current_sentence=job.total_sentences,
                total_sentences=job.total_sentences
            )

            return {
                "job_id": str(job_id),
                "status": "completed",
                "total_sentences": job.total_sentences,
                "validated": validated_count,
                "uncertain": uncertain_count,
                "incorrect": incorrect_count
            }

        except Exception as e:
            await session.rollback()
            logger.error(f"Error in async verification: {e}")
            raise


async def _update_job_status(
    job_id: UUID,
    status: VerificationStatus,
    error_message: str = None
):
    """Update verification job status."""
    async with get_async_session() as session:
        result = await session.execute(
            select(VerificationJob).where(VerificationJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if job:
            job.status = status
            if error_message:
                job.error_message = error_message
            if status == VerificationStatus.COMPLETED:
                job.completed_at = datetime.utcnow()
                job.progress = 100.0

            await session.commit()


async def send_verification_progress(
    job_id: UUID,
    status: VerificationStatus,
    progress: float,
    current_sentence: int,
    total_sentences: int
):
    """
    Send verification progress update via WebSocket.

    This would normally use the Socket.IO instance from main.py,
    but for Celery tasks we can use Redis pub/sub or HTTP callback.
    """
    try:
        import redis
        from app.core.config import settings

        redis_client = redis.from_url(settings.REDIS_URL)

        # Publish progress update to Redis channel
        progress_data = {
            "job_id": str(job_id),
            "status": status.value,
            "progress": progress,
            "current_sentence": current_sentence,
            "total_sentences": total_sentences,
            "message": f"Verified {current_sentence} of {total_sentences} sentences"
        }

        redis_client.publish(
            f"verification_progress_{job_id}",
            str(progress_data)
        )

        logger.debug(f"Published progress update for job {job_id}")

    except Exception as e:
        logger.error(f"Error sending progress update: {e}")
