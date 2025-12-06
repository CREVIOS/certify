"""Celery tasks for document verification."""

from uuid import UUID, uuid4
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.services.document_processor import DocumentProcessor
from app.services.verification_service import verification_service
from app.db.models import (
    VerificationJob, Document, Project, VerifiedSentence,
    VerificationStatus, ValidationResult
)


@asynccontextmanager
async def get_task_session():
    """
    Create a fresh async database session for Celery tasks.
    
    This creates a NEW engine and session per task to avoid event loop conflicts
    when using Celery with asyncio. The engine is disposed after the task completes.
    
    PgBouncer compatibility:
    - Uses NullPool since pgbouncer handles connection pooling
    - Disables prepared statements (statement_cache_size=0) which pgbouncer
      in transaction mode doesn't support
    """
    database_url = settings.DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://')
    
    # Use NullPool - pgbouncer handles connection pooling, not SQLAlchemy
    engine = create_async_engine(
        database_url,
        echo=settings.DEBUG,
        poolclass=NullPool,
        connect_args={
            # Disable prepared statements for pgbouncer compatibility
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            # Generate unique prepared statement names to avoid collisions in pgbouncer
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
        # Also disable SQLAlchemy-side prepared statement caching
        execution_options={"prepared_statement_cache_size": 0},
    )
    
    # Create session factory bound to this engine
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    async with session_factory() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    # Dispose the engine to clean up connections
    await engine.dispose()


@celery_app.task(
    bind=True,
    name='run_verification',
    soft_time_limit=1800,  # 30 minutes soft limit
    time_limit=2100,       # 35 minutes hard limit
)
def run_verification_task(self, verification_job_id: str):
    """
    Run verification job to verify all sentences in main document.

    Args:
        verification_job_id: Verification job UUID
    """
    try:
        logger.info(f"[verify:{self.request.id}] Starting verification job {verification_job_id}")

        # Run async task
        result = asyncio.run(
            _run_verification_async(
                UUID(verification_job_id),
                self.request.id
            )
        )

        logger.info(f"[verify:{self.request.id}] Successfully completed verification job {verification_job_id}")
        return result

    except Exception as e:
        logger.error(f"[verify:{self.request.id}] Error in verification job {verification_job_id}: {e}")

        # Update job status to failed
        try:
            asyncio.run(_update_job_status(
                UUID(verification_job_id),
                VerificationStatus.FAILED,
                error_message=str(e)
            ))
        except Exception as update_error:
            logger.error(f"[verify:{self.request.id}] Failed to update job status: {update_error}")
        raise


async def _run_verification_async(job_id: UUID, task_id: str):
    """
    Async implementation of verification job.
    
    Processes sentences sequentially to avoid SQLAlchemy session conflicts,
    with periodic commits to persist progress.
    """
    async with get_task_session() as session:
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
            project_context = project.background_context if project else ""

            # Process main document to extract sentences
            logger.info(f"[verify:{task_id}] Processing document {main_doc.file_path}")
            processor = DocumentProcessor(
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP
            )
            processed = await processor.process_document_for_verification(main_doc.file_path)
            sentences = processed["sentences"]

            # Update total count
            job.total_sentences = len(sentences)
            await session.commit()
            logger.info(f"[verify:{task_id}] Found {len(sentences)} sentences to verify")

            # Counters
            validated_count = 0
            uncertain_count = 0
            incorrect_count = 0
            error_count = 0
            
            # Commit interval - commit every N sentences to persist progress
            commit_interval = getattr(settings, 'VERIFICATION_COMMIT_INTERVAL', 5)

            # Process sentences sequentially to avoid session conflicts
            for idx, sentence_data in enumerate(sentences):
                try:
                    verification_result = await verification_service.verify_sentence(
                        sentence=sentence_data["content"],
                        project_id=job.project_id,
                        context=project_context
                    )

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

                    if verification_result["validation_result"] == ValidationResult.VALIDATED:
                        validated_count += 1
                    elif verification_result["validation_result"] == ValidationResult.UNCERTAIN:
                        uncertain_count += 1
                    elif verification_result["validation_result"] == ValidationResult.INCORRECT:
                        incorrect_count += 1

                    # Update job progress
                    job.verified_sentences = idx + 1
                    # progress is stored as 0–1 per DB constraint
                    job.progress = (idx + 1) / job.total_sentences
                    job.validated_count = validated_count
                    job.uncertain_count = uncertain_count
                    job.incorrect_count = incorrect_count

                    # Commit periodically to persist progress
                    if (idx + 1) % commit_interval == 0:
                        await session.commit()
                        
                        # Send progress update
                        await send_verification_progress(
                            job_id=job_id,
                            status=VerificationStatus.PROCESSING,
                            progress=job.progress,
                            current_sentence=job.verified_sentences,
                            total_sentences=job.total_sentences
                        )
                        
                        logger.info(
                            f"[verify:{task_id}] Progress: {idx + 1}/{len(sentences)} "
                            f"(V:{validated_count} U:{uncertain_count} I:{incorrect_count})"
                        )

                except Exception as e:
                    error_count += 1
                    logger.error(f"[verify:{task_id}] Error verifying sentence {sentence_data['index']}: {e}")
                    # Continue with next sentence instead of failing entirely
                    continue

            # Final commit for any remaining uncommitted changes
            await session.commit()

            # Mark job as completed
            job.status = VerificationStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.progress = 1.0
            await session.commit()

            # Send completion update
            await send_verification_progress(
                job_id=job_id,
                status=VerificationStatus.COMPLETED,
                progress=100.0,
                current_sentence=job.total_sentences,
                total_sentences=job.total_sentences
            )

            logger.info(
                f"[verify:{task_id}] Completed: {job.total_sentences} sentences "
                f"(V:{validated_count} U:{uncertain_count} I:{incorrect_count} E:{error_count})"
            )

            return {
                "job_id": str(job_id),
                "status": "completed",
                "total_sentences": job.total_sentences,
                "validated": validated_count,
                "uncertain": uncertain_count,
                "incorrect": incorrect_count,
                "errors": error_count
            }

        except Exception as e:
            await session.rollback()
            logger.exception(f"[verify:{task_id}] Error in async verification: {e}")
            raise


async def _update_job_status(
    job_id: UUID,
    status: VerificationStatus,
    error_message: str = None
):
    """Update verification job status."""
    async with get_task_session() as session:
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
                # DB check constraint expects progress in 0–1 range
                job.progress = 1.0

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
