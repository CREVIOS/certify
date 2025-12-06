"""Project endpoints."""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from loguru import logger

from app.db.session import get_db
from app.db.models import Project, Document, VerificationJob, DocumentType
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse, ProjectDetail
)
from app.services.vector_store import vector_store

router = APIRouter()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new project."""
    try:
        project = Project(**project_data.model_dump())
        db.add(project)
        await db.commit()
        await db.refresh(project)

        # Create Weaviate schema for project
        vector_store.create_schema(project.id)

        logger.info(f"Created project {project.id}")
        return project

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating project: {str(e)}"
        )


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all projects."""
    try:
        result = await db.execute(
            select(Project)
            .order_by(Project.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        projects = result.scalars().all()
        return projects

    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing projects: {str(e)}"
        )


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get project details with statistics."""
    try:
        # Get project
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        # Get statistics
        doc_count_result = await db.execute(
            select(func.count(Document.id)).where(Document.project_id == project_id)
        )
        document_count = doc_count_result.scalar()

        main_doc_result = await db.execute(
            select(func.count(Document.id)).where(
                Document.project_id == project_id,
                Document.document_type == DocumentType.MAIN
            )
        )
        main_document_count = main_doc_result.scalar()

        supporting_doc_result = await db.execute(
            select(func.count(Document.id)).where(
                Document.project_id == project_id,
                Document.document_type == DocumentType.SUPPORTING
            )
        )
        supporting_document_count = supporting_doc_result.scalar()

        job_count_result = await db.execute(
            select(func.count(VerificationJob.id)).where(
                VerificationJob.project_id == project_id
            )
        )
        verification_job_count = job_count_result.scalar()

        # Build response
        project_detail = ProjectDetail(
            **project.__dict__,
            document_count=document_count,
            main_document_count=main_document_count,
            supporting_document_count=supporting_document_count,
            verification_job_count=verification_job_count
        )

        return project_detail

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting project: {str(e)}"
        )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_data: ProjectUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update project."""
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

        # Update fields
        update_data = project_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(project, field, value)

        await db.commit()
        await db.refresh(project)

        logger.info(f"Updated project {project_id}")
        return project

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating project: {str(e)}"
        )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete project and all associated data."""
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

        # Delete Weaviate collection
        vector_store.delete_collection(project_id)

        # Delete project (cascades to documents and jobs)
        await db.delete(project)
        await db.commit()

        logger.info(f"Deleted project {project_id}")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting project: {str(e)}"
        )
