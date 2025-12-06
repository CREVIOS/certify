"""Main API router."""

from fastapi import APIRouter

from app.api.v1.endpoints import projects, documents, verification

api_router = APIRouter()

# Include routers
api_router.include_router(
    projects.router,
    prefix="/projects",
    tags=["projects"]
)

api_router.include_router(
    documents.router,
    prefix="/documents",
    tags=["documents"]
)

api_router.include_router(
    verification.router,
    prefix="/verification",
    tags=["verification"]
)
