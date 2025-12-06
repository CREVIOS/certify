"""
Projects API endpoints
Handles project CRUD operations, document uploads, and verification
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.db.models import (
    Project, Document, VerificationJob, VerifiedSentence,
    DocumentType, VerificationStatus
)
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse, ProjectWithStatsResponse,
    PaginatedProjectsResponse
)
from app.schemas.document import DocumentResponse
from app.services.storage_service import StorageService
from app.services.document_processor import DocumentProcessor

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=PaginatedProjectsResponse)
async def list_projects(
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """
    List all projects with pagination
    Returns projects with document count and latest job stats
    """
    if page < 1 or per_page < 1 or per_page > 100:
        raise HTTPException(status_code=400, detail="Invalid pagination parameters")

    offset = (page - 1) * per_page

    # Count total projects
    count_query = select(func.count(Project.id))
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get projects with relationships
    query = (
        select(Project)
        .options(
            selectinload(Project.documents),
            selectinload(Project.verification_jobs)
        )
        .order_by(Project.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )

    result = await db.execute(query)
    projects = result.scalars().all()

    # Build response with stats
    items = []
    for project in projects:
        # Count documents
        doc_count = len(project.documents)

        # Get main document
        main_doc = next((d for d in project.documents if d.document_type == DocumentType.MAIN), None)

        # Get supporting documents
        supporting_docs = [d for d in project.documents if d.document_type == DocumentType.SUPPORTING]

        # Get latest job
        latest_job = max(project.verification_jobs, key=lambda j: j.created_at) if project.verification_jobs else None

        items.append({
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "background_context": project.background_context,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
            "document_count": doc_count,
            "main_document": DocumentResponse.from_orm(main_doc) if main_doc else None,
            "supporting_documents": [DocumentResponse.from_orm(d) for d in supporting_docs],
            "latest_job": {
                "id": str(latest_job.id),
                "status": latest_job.status.value,
                "progress": latest_job.progress,
                "total_sentences": latest_job.total_sentences,
                "verified_sentences": latest_job.verified_sentences,
                "validated_count": latest_job.validated_count,
                "uncertain_count": latest_job.uncertain_count,
                "incorrect_count": latest_job.incorrect_count,
            } if latest_job else None
        })

    pages = (total + per_page - 1) // per_page

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages
    }


@router.get("/{project_id}", response_model=ProjectWithStatsResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a single project with full statistics
    """
    query = (
        select(Project)
        .options(
            selectinload(Project.documents),
            selectinload(Project.verification_jobs)
        )
        .where(Project.id == project_id)
    )

    result = await db.execute(query)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Build response
    doc_count = len(project.documents)
    main_doc = next((d for d in project.documents if d.document_type == DocumentType.MAIN), None)
    supporting_docs = [d for d in project.documents if d.document_type == DocumentType.SUPPORTING]
    latest_job = max(project.verification_jobs, key=lambda j: j.created_at) if project.verification_jobs else None

    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "background_context": project.background_context,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "document_count": doc_count,
        "main_document": DocumentResponse.from_orm(main_doc) if main_doc else None,
        "supporting_documents": [DocumentResponse.from_orm(d) for d in supporting_docs],
        "latest_job": {
            "id": str(latest_job.id),
            "status": latest_job.status.value,
            "progress": latest_job.progress,
            "total_sentences": latest_job.total_sentences,
            "verified_sentences": latest_job.verified_sentences,
            "validated_count": latest_job.validated_count,
            "uncertain_count": latest_job.uncertain_count,
            "incorrect_count": latest_job.incorrect_count,
            "started_at": latest_job.started_at.isoformat() if latest_job.started_at else None,
            "completed_at": latest_job.completed_at.isoformat() if latest_job.completed_at else None,
        } if latest_job else None
    }


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new verification project
    """
    # Validate name
    if not project.name or len(project.name) < 3:
        raise HTTPException(status_code=400, detail="Project name must be at least 3 characters")

    if len(project.name) > 255:
        raise HTTPException(status_code=400, detail="Project name too long (max 255 characters)")

    # Check for duplicate name
    existing = await db.execute(
        select(Project).where(func.lower(Project.name) == func.lower(project.name))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Project with this name already exists")

    # Create project
    db_project = Project(
        name=project.name,
        description=project.description,
        background_context=project.background_context
    )

    db.add(db_project)
    await db.commit()
    await db.refresh(db_project)

    return ProjectResponse.from_orm(db_project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project: ProjectUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing project
    """
    # Get project
    result = await db.execute(select(Project).where(Project.id == project_id))
    db_project = result.scalar_one_or_none()

    if not db_project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Update fields
    if project.name is not None:
        if len(project.name) < 3:
            raise HTTPException(status_code=400, detail="Project name must be at least 3 characters")
        db_project.name = project.name

    if project.description is not None:
        db_project.description = project.description

    if project.background_context is not None:
        db_project.background_context = project.background_context

    await db.commit()
    await db.refresh(db_project)

    return ProjectResponse.from_orm(db_project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a project and all associated data (CASCADE)
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    db_project = result.scalar_one_or_none()

    if not db_project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete from storage
    storage_service = StorageService()
    for document in db_project.documents:
        try:
            storage_service.delete_file(document.file_path)
        except Exception as e:
            # Log but don't fail delete
            print(f"Warning: Could not delete file {document.file_path}: {e}")

    await db.delete(db_project)
    await db.commit()

    return None


@router.post("/{project_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_documents(
    project_id: UUID,
    files: List[UploadFile] = File(...),
    document_type: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload documents (main or supporting) for a project
    """
    # Validate project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate document type
    try:
        doc_type = DocumentType(document_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document type")

    # Check if main document already exists
    if doc_type == DocumentType.MAIN:
        existing_main = await db.execute(
            select(Document).where(
                and_(
                    Document.project_id == project_id,
                    Document.document_type == DocumentType.MAIN
                )
            )
        )
        if existing_main.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Main document already exists for this project")

        if len(files) > 1:
            raise HTTPException(status_code=400, detail="Only one main document allowed")

    # Process uploads
    storage_service = StorageService()
    processor = DocumentProcessor()
    uploaded_docs = []

    for file in files:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail=f"Invalid file type: {file.filename}. Only PDF files allowed")

        # Upload to storage
        try:
            file_path = storage_service.upload_file(
                file.file,
                file.filename,
                project_id,
                file.content_type
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

        # Extract metadata
        try:
            metadata = await processor.extract_metadata(file_path)
        except Exception as e:
            # Clean up uploaded file
            storage_service.delete_file(file_path)
            raise HTTPException(status_code=500, detail=f"PDF processing failed: {str(e)}")

        # Create document record
        document = Document(
            project_id=project_id,
            filename=file_path.split('/')[-1],
            original_filename=file.filename,
            file_path=file_path,
            file_size=file.size,
            mime_type=file.content_type or 'application/pdf',
            document_type=doc_type,
            page_count=metadata.get('page_count'),
            metadata=metadata
        )

        db.add(document)
        uploaded_docs.append(document)

    await db.commit()

    # Refresh to get IDs
    for doc in uploaded_docs:
        await db.refresh(doc)

    return {
        "message": f"Uploaded {len(uploaded_docs)} document(s)",
        "documents": [DocumentResponse.from_orm(doc) for doc in uploaded_docs]
    }


@router.post("/{project_id}/verify")
async def start_verification(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Start verification job for a project
    Triggers async Celery task
    """
    # Validate project exists
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.documents))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check for main document
    main_doc = next((d for d in project.documents if d.document_type == DocumentType.MAIN), None)
    if not main_doc:
        raise HTTPException(status_code=400, detail="No main document found. Upload main document first")

    # Check for supporting documents
    supporting_docs = [d for d in project.documents if d.document_type == DocumentType.SUPPORTING]
    if not supporting_docs:
        raise HTTPException(status_code=400, detail="No supporting documents found. Upload at least one supporting document")

    # Check for existing active job
    active_job_query = select(VerificationJob).where(
        and_(
            VerificationJob.project_id == project_id,
            VerificationJob.status.in_([
                VerificationStatus.PENDING,
                VerificationStatus.INDEXING,
                VerificationStatus.PROCESSING
            ])
        )
    )
    active_job_result = await db.execute(active_job_query)
    if active_job_result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Verification already in progress for this project")

    # Create verification job
    job = VerificationJob(
        project_id=project_id,
        main_document_id=main_doc.id,
        status=VerificationStatus.PENDING
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    # TODO: Trigger Celery task
    # from app.tasks.verification import verify_document_task
    # task = verify_document_task.delay(str(job.id))
    # job.celery_task_id = task.id
    # await db.commit()

    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "message": "Verification started"
    }
