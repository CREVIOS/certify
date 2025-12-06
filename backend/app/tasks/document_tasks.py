"""Celery tasks for document processing and indexing."""

from uuid import UUID, uuid4
from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
import asyncio
from contextlib import asynccontextmanager

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import vector_store
from app.db.models import Document, DocumentChunk, Project
from datetime import datetime


class DocumentAlreadyProcessingError(Exception):
    """Raised when a document is already being processed by another worker."""
    pass


@asynccontextmanager
async def get_task_session():
    """
    Create a fresh async database session for Celery tasks.
    
    This creates a NEW engine and session per task to avoid event loop conflicts
    when using Celery with asyncio. The engine is disposed after the task completes.
    
    Why this is needed:
    - Celery uses fork-based multiprocessing (prefork worker pool)
    - The global engine is created in the parent process with its own event loop
    - When asyncio.run() creates a new loop in the worker, the pooled connections
      are attached to the old/different loop, causing "attached to a different loop" errors
    
    PgBouncer compatibility:
    - Uses NullPool since pgbouncer handles connection pooling
    - Disables prepared statements (statement_cache_size=0) which pgbouncer
      in transaction mode doesn't support
    """
    database_url = settings.DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://')
    
    engine = create_async_engine(
        database_url,
        echo=settings.DEBUG,
        poolclass=NullPool,
        connect_args={
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
    

    await engine.dispose()


@celery_app.task(
    bind=True,
    name='index_document',
    autoretry_for=(DocumentAlreadyProcessingError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
    # Indexing can take time for large PDFs/embeddings; keep limits generous
    soft_time_limit=1800,   # 30 minutes soft limit
    time_limit=2100,       # 35 minutes hard limit
)
def index_document_task(self, document_id: str, project_id: str):
    """
    Index a document by processing and storing in vector database.

    Args:
        document_id: Document UUID
        project_id: Project UUID
    
    Retries automatically on lock conflicts with exponential backoff.
    """
    try:
        logger.info(f"[index:{self.request.id}] Starting indexing for document {document_id} (attempt {self.request.retries + 1})")

        # Run async task
        result = asyncio.run(
            _index_document_async(
                UUID(document_id),
                UUID(project_id),
                self.request.id
            )
        )

        if result.get("status") == "already_processing":
            # Another worker has the lock - retry with backoff
            logger.info(f"[index:{self.request.id}] Document {document_id} locked, will retry")
            raise DocumentAlreadyProcessingError(f"Document {document_id} is being processed by another worker")
        
        logger.info(f"[index:{self.request.id}] Successfully indexed document {document_id}")
        return result

    except DocumentAlreadyProcessingError:
        # Let Celery handle retry via autoretry_for
        raise
    except Exception as e:
        logger.error(f"[index:{self.request.id}] Error indexing document {document_id}: {e}")
        raise


async def _index_document_async(
    document_id: UUID,
    project_id: UUID,
    task_id: str
):
    """
    Async implementation of document indexing.
    
    Uses a single transaction with FOR UPDATE lock to prevent concurrent indexing.
    The lock is held until the final commit to ensure atomicity.
    """
    async with get_task_session() as session:
        try:
            # Lock the document row to avoid concurrent indexing of the same doc
            # Using FOR UPDATE NOWAIT - fails immediately if row is locked
            try:
                result = await session.execute(
                    select(Document)
                    .where(Document.id == document_id)
                    .with_for_update(nowait=True)
                )
            except DBAPIError as e:
                # Check if it's a lock error (asyncpg wraps this differently)
                error_str = str(e)
                if "LockNotAvailable" in error_str or "could not obtain lock" in error_str:
                    # Another worker is already processing this document
                    logger.info(f"[index:{task_id}] Document {document_id} locked by another worker")
                    return {
                        "document_id": str(document_id),
                        "status": "already_processing"
                    }
                # Re-raise other database errors
                raise
            
            document = result.scalar_one_or_none()

            if not document:
                raise ValueError(f"Document {document_id} not found")

            # Idempotency check: skip if already indexed
            if document.indexed:
                logger.info(f"[index:{task_id}] Document {document_id} already indexed, skipping")
                return {
                    "document_id": str(document_id),
                    "chunks_indexed": 0,
                    "status": "already_indexed"
                }

            # Delete any existing chunks for this document (handles re-indexing)
            # Using flush() instead of commit() to keep the FOR UPDATE lock active
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
            await session.flush()
            logger.info(f"[index:{task_id}] Cleared existing chunks for {document_id}")

            # Ensure Weaviate schema exists (sync operation, doesn't affect our transaction)
            logger.info(f"[index:{task_id}] Creating schema for project {project_id}")
            vector_store.create_schema(project_id)

            # Process document (file I/O, doesn't affect DB transaction)
            logger.info(f"[index:{task_id}] Processing file {document.file_path}")
            processor = DocumentProcessor(
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP
            )

            processed = await processor.process_document_for_indexing(document.file_path)
            logger.info(f"[index:{task_id}] Extracted {len(processed['chunks'])} chunks")

            # Store chunks in database - use simple ORM approach for reliability
            chunk_records = []
            for idx, chunk in enumerate(processed["chunks"]):
                chunk_record = DocumentChunk(
                    document_id=document_id,
                    chunk_index=idx,
                    content=chunk["content"],
                    page_number=chunk.get("page_number"),
                    start_char=chunk.get("start_char"),
                    end_char=chunk.get("end_char"),
                    metadata_=chunk.get("metadata", {})
                )
                chunk_records.append(chunk_record)
                session.add(chunk_record)

            # Flush to get auto-generated IDs without releasing the lock
            await session.flush()
            logger.info(f"[index:{task_id}] Stored {len(chunk_records)} chunks in database")

            # Build Weaviate payload from chunk records (already have IDs after flush)
            chunks_for_indexing = [
                {
                    "id": str(chunk.id),
                    "content": chunk.content,
                    "page_number": chunk.page_number,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char
                }
                for chunk in chunk_records
            ]

            logger.info(f"[index:{task_id}] Indexing {len(chunks_for_indexing)} chunks in Weaviate")
            weaviate_ids = await vector_store.index_chunks(
                project_id=project_id,
                chunks=chunks_for_indexing,
                document_id=document_id,
                filename=document.original_filename,
                document_type=document.document_type.value
            )

            # Update chunk records with Weaviate IDs
            for chunk_record, weaviate_id in zip(chunk_records, weaviate_ids):
                chunk_record.weaviate_id = weaviate_id

            # Mark document as indexed
            document.indexed = True
            document.indexed_at = datetime.utcnow()
            document.page_count = processed.get("metadata", {}).get("page_count", 0)

            # Single commit at the end - this releases the lock and commits all changes atomically
            await session.commit()
            logger.info(f"[index:{task_id}] Committed all changes for document {document_id}")

            return {
                "document_id": str(document_id),
                "chunks_indexed": len(chunk_records),
                "status": "completed"
            }

        except Exception as e:
            await session.rollback()
            logger.exception(f"[index:{task_id}] Error in async indexing for {document_id}")
            raise


@celery_app.task(bind=True, name='index_project_documents')
def index_project_documents_task(self, project_id: str):
    """
    Index all documents in a project.

    Args:
        project_id: Project UUID
    """
    try:
        logger.info(f"Starting project indexing for {project_id}")
        result = asyncio.run(_index_project_documents_async(UUID(project_id)))
        logger.info(f"Successfully indexed project {project_id}")
        return result

    except Exception as e:
        logger.error(f"Error indexing project {project_id}: {e}")
        raise


async def _index_project_documents_async(project_id: UUID):
    """
    Async implementation of project document indexing.
    
    Note: Each document is indexed in its own session/transaction to avoid
    holding locks across multiple documents.
    """
    async with get_task_session() as session:
        # Get all unindexed documents (snapshot of IDs)
        result = await session.execute(
            select(Document.id).where(
                Document.project_id == project_id,
                Document.indexed == False
            )
        )
        document_ids = [row[0] for row in result.fetchall()]

    # Index each document in its own session/transaction
    indexed_count = 0
    skipped_count = 0
    failed_count = 0
    
    for doc_id in document_ids:
        try:
            result = await _index_document_async(
                doc_id,
                project_id,
                f"project_index_{project_id}"
            )
            if result.get("status") == "completed":
                indexed_count += 1
            elif result.get("status") in ("already_indexed", "already_processing"):
                skipped_count += 1
        except Exception as e:
            logger.error(f"Error indexing document {doc_id}: {e}")
            failed_count += 1

    return {
        "project_id": str(project_id),
        "documents_indexed": indexed_count,
        "documents_skipped": skipped_count,
        "documents_failed": failed_count,
        "total_documents": len(document_ids),
        "status": "completed"
    }
