"""Document endpoints with Supabase Storage integration."""

import os
import re
import shutil
import json
from typing import List
from uuid import UUID, uuid4
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.db.session import get_db
from app.db.models import Document, Project, DocumentType
from app.schemas.document import (
    DocumentResponse,
    DocumentUpdate,
    DocumentUploadResponse,
    SectionSuggestionResponse,
    SectionSchema,
)
from app.core.config import settings
from app.tasks.document_tasks import index_document_task, index_project_documents_task
from app.services.storage_service import storage_service
from app.services.document_processor import DocumentProcessor
from langchain_openai import ChatOpenAI

router = APIRouter()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    project_id: UUID = Form(...),
    document_type: DocumentType = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload a document (PDF or DOCX)."""
    try:
        # Verify project exists
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        # Validate file extension
        file_ext = Path(file.filename).suffix.lower().replace('.', '')
        if file_ext not in settings.allowed_extensions_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed: {settings.ALLOWED_EXTENSIONS}"
            )

        # Validate file size
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Max size: {settings.MAX_UPLOAD_SIZE} bytes"
            )

        # Generate unique filename
        unique_filename = f"{uuid4()}_{file.filename}"

        # Upload to Supabase Storage or local filesystem
        if settings.USE_SUPABASE_STORAGE:
            # Reset file position
            file.file.seek(0)

            # Upload to Supabase Storage
            storage_path = storage_service.upload_file(
                file=file.file,
                filename=unique_filename,
                project_id=project_id,
                content_type=file.content_type
            )
            file_path = storage_path
        else:
            # Fallback to local filesystem
            upload_dir = Path(settings.UPLOAD_DIR) / str(project_id)
            upload_dir.mkdir(parents=True, exist_ok=True)

            file_path_local = upload_dir / unique_filename

            # Save file locally
            file.file.seek(0)
            with open(file_path_local, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            file_path = str(file_path_local)

        # Create document record
        document = Document(
            project_id=project_id,
            filename=unique_filename,
            original_filename=file.filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            document_type=document_type
        )

        db.add(document)
        await db.commit()
        await db.refresh(document)

        logger.info(f"Uploaded document {document.id}: {file.filename}")

        # Kick off async indexing in Celery to keep request light
        task = index_document_task.delay(str(document.id), str(project_id))

        return DocumentUploadResponse(
            document_id=document.id,
            filename=file.filename,
            file_size=file_size,
            document_type=document_type,
            task_id=task.id,
            message="Document uploaded and indexing started."
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading document: {str(e)}"
        )


@router.post("/{document_id}/index", status_code=status.HTTP_202_ACCEPTED)
async def index_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Index a document for semantic search."""
    try:
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        if document.indexed:
            return {
                "message": "Document already indexed",
                "document_id": str(document_id)
            }

        # Trigger Celery task
        task = index_document_task.delay(
            str(document_id),
            str(document.project_id)
        )

        logger.info(f"Started indexing task for document {document_id}: {task.id}")

        return {
            "message": "Indexing started",
            "document_id": str(document_id),
            "task_id": task.id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting indexing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting indexing: {str(e)}"
        )


@router.post("/index-project/{project_id}", status_code=status.HTTP_202_ACCEPTED)
async def index_project_documents(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Index all documents in a project."""
    try:
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        # Trigger Celery task
        task = index_project_documents_task.delay(str(project_id))

        logger.info(f"Started project indexing task for {project_id}: {task.id}")

        return {
            "message": "Project indexing started",
            "project_id": str(project_id),
            "task_id": task.id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting project indexing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting project indexing: {str(e)}"
        )


@router.get("/project/{project_id}", response_model=List[DocumentResponse])
async def list_project_documents(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all documents in a project."""
    try:
        result = await db.execute(
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.desc())
        )
        documents = result.scalars().all()
        return documents

    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing documents: {str(e)}"
        )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get document details."""
    try:
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting document: {str(e)}"
        )


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    document_data: DocumentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update document metadata."""
    try:
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        # Update fields
        update_data = document_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(document, field, value)

        await db.commit()
        await db.refresh(document)

        logger.info(f"Updated document {document_id}")
        return document

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating document: {str(e)}"
        )


@router.post("/{document_id}/sections/suggest", response_model=SectionSuggestionResponse)
async def suggest_document_sections(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Suggest IPO sections using Gemini based on the uploaded main document.
    Returns lightweight title/start_page/end_page suggestions for user review.
    """
    try:
        # Fetch document
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        if document.document_type != DocumentType.MAIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sectioning is only supported for main IPO documents"
            )

        # Extract text (limit to keep prompt lean)
        processor = DocumentProcessor(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP
        )
        extraction = await processor.extract_text(document.file_path)
        text = extraction.get("full_text", "")[:15000]  # cap tokens for speed
        page_hint = extraction.get("page_count") or len(extraction.get("pages", [])) or 1

        llm = ChatOpenAI(
            model="gpt-5-mini",  # OpenAI mini model
            api_key=settings.OPENAI_API_KEY,
            max_tokens=1024,
        )

        prompt = (
            "You are structuring an IPO prospectus.\n"
            "- Given the raw text below, propose concise sections the reviewer can edit.\n"
            "- Return 8-15 sections max.\n"
            "- Each section must have: title, start_page (int >=1), end_page (int >= start_page), "
            "and a one-sentence summary.\n"
            "- Be conservative with page spans; estimate using page numbers mentioned in text when possible; "
            f"assume total pages around {page_hint}.\n"
            "- OUTPUT FORMAT: return ONLY valid JSON, **no markdown fences**, **no code block labels**, **no extra text**.\n"
            '- Exact schema: { "sections": [ { "title": "string", "start_page": 1, '
            '"end_page": 2, "summary": "string" } ] }\n'
            "- The first and last characters of your reply must be '{' and '}' so it parses with json.loads.\n"
        )

        response = await llm.ainvoke(prompt + "\n\nTEXT:\n" + text)

        # Normalize Gemini response content (handles list-of-chunks format)
        raw_content = response.content or ""
        if isinstance(raw_content, list):
            raw_content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in raw_content
            )
        raw_content = str(raw_content).strip()

        # Strip markdown fences and pull out JSON payload
        if raw_content.startswith("```"):
            raw_content = raw_content.strip("`")
            if raw_content.lower().startswith("json"):
                raw_content = raw_content[4:].strip()

        match = re.search(r"\{[\s\S]*\}", raw_content)
        content_to_parse = match.group(0) if match else raw_content

        try:
            payload = json.loads(content_to_parse)
            sections_raw = payload.get("sections", [])
        except Exception:
            logger.warning(f"Gemini section suggestion returned unparsable content: {raw_content}")
            # Fallback: return a single full-document section instead of 502
            fallback_sections = [
                SectionSchema(
                    title="Full Document",
                    start_page=1,
                    end_page=max(1, int(page_hint)),
                    summary="Fallback section because the model response was not valid JSON."
                )
            ]
            return SectionSuggestionResponse(
                document_id=document_id,
                sections=fallback_sections,
                model=settings.GEMINI_MODEL
            )

        if not sections_raw:
            logger.warning("Gemini section suggestion returned no sections")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Section suggestion returned no sections"
            )

        sections: List[SectionSchema] = []
        for sec in sections_raw:
            try:
                sections.append(SectionSchema(
                    title=sec.get("title", "Untitled"),
                    start_page=int(sec.get("start_page", 1)),
                    end_page=int(sec.get("end_page", sec.get("start_page", 1))),
                    summary=sec.get("summary")
                ))
            except Exception:
                continue

        return SectionSuggestionResponse(
            document_id=document_id,
            sections=sections,
            model="gpt-5-mini"  # reflect actual model used
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error suggesting sections: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error suggesting sections: {str(e)}"
        )




@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete document and associated chunks."""
    try:
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        # Delete file from storage
        if settings.USE_SUPABASE_STORAGE:
            storage_service.delete_file(document.file_path)
        else:
            if os.path.exists(document.file_path):
                os.remove(document.file_path)

        # Delete from Weaviate
        from app.services.vector_store import vector_store
        vector_store.delete_document_chunks(document.project_id, document_id)

        # Delete document record (cascades to chunks)
        await db.delete(document)
        await db.commit()

        logger.info(f"Deleted document {document_id}")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting document: {str(e)}"
        )
