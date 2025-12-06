"""Celery tasks for document processing and indexing."""

from uuid import UUID
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import asyncio

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import vector_store
from app.db.models import Document, DocumentChunk, Project
from datetime import datetime


def get_async_session():
    """Create async database session for Celery tasks."""
    DATABASE_URL = settings.DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://')
    engine = create_async_engine(DATABASE_URL)
    return AsyncSession(engine)


@celery_app.task(bind=True, name='index_document')
def index_document_task(self, document_id: str, project_id: str):
    """
    Index a document by processing and storing in vector database.

    Args:
        document_id: Document UUID
        project_id: Project UUID
    """
    try:
        logger.info(f"Starting indexing for document {document_id}")

        # Run async task
        result = asyncio.run(
            _index_document_async(
                UUID(document_id),
                UUID(project_id),
                self.request.id
            )
        )

        logger.info(f"Successfully indexed document {document_id}")
        return result

    except Exception as e:
        logger.error(f"Error indexing document {document_id}: {e}")
        raise


async def _index_document_async(
    document_id: UUID,
    project_id: UUID,
    task_id: str
):
    """Async implementation of document indexing."""
    async with get_async_session() as session:
        try:
            # Get document
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()

            if not document:
                raise ValueError(f"Document {document_id} not found")

            # Ensure Weaviate schema exists
            vector_store.create_schema(project_id)

            # Process document
            processor = DocumentProcessor(
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP
            )

            processed = await processor.process_document_for_indexing(document.file_path)

            # Store chunks in database
            chunk_records = []
            for idx, chunk in enumerate(processed["chunks"]):
                chunk_record = DocumentChunk(
                    document_id=document_id,
                    chunk_index=idx,
                    content=chunk["content"],
                    page_number=chunk.get("page_number"),
                    start_char=chunk.get("start_char"),
                    end_char=chunk.get("end_char"),
                    metadata=chunk.get("metadata", {})
                )
                chunk_records.append(chunk_record)
                session.add(chunk_record)

            await session.commit()

            # Index chunks in Weaviate
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

            await session.commit()

            return {
                "document_id": str(document_id),
                "chunks_indexed": len(chunk_records),
                "status": "completed"
            }

        except Exception as e:
            await session.rollback()
            logger.error(f"Error in async indexing: {e}")
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
    """Async implementation of project document indexing."""
    async with get_async_session() as session:
        # Get all unindexed documents
        result = await session.execute(
            select(Document).where(
                Document.project_id == project_id,
                Document.indexed == False
            )
        )
        documents = result.scalars().all()

        indexed_count = 0
        for document in documents:
            try:
                await _index_document_async(
                    document.id,
                    project_id,
                    f"project_index_{project_id}"
                )
                indexed_count += 1
            except Exception as e:
                logger.error(f"Error indexing document {document.id}: {e}")

        return {
            "project_id": str(project_id),
            "documents_indexed": indexed_count,
            "total_documents": len(documents),
            "status": "completed"
        }
