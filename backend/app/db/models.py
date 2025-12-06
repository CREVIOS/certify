"""SQLAlchemy database models."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    Float, ForeignKey, Enum as SQLEnum, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
import uuid
import enum

from app.db.session import Base


class DocumentType(str, enum.Enum):
    """Document type enumeration."""
    MAIN = "main"
    SUPPORTING = "supporting"


class VerificationStatus(str, enum.Enum):
    """Verification status enumeration."""
    PENDING = "pending"
    INDEXING = "indexing"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationResult(str, enum.Enum):
    """Validation result enumeration for sentences."""
    VALIDATED = "validated"  # Green - Correct
    UNCERTAIN = "uncertain"  # Yellow - Needs review
    INCORRECT = "incorrect"  # Red - Contradicts evidence
    PENDING = "pending"      # Not yet verified


class Project(Base):
    """Project model - represents a verification project."""

    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    background_context = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    verification_jobs = relationship("VerificationJob", back_populates="project", cascade="all, delete-orphan")


class Document(Base):
    """Document model - represents uploaded documents."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    document_type = Column(SQLEnum(DocumentType), nullable=False)
    page_count = Column(Integer)
    indexed = Column(Boolean, default=False)
    indexed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Metadata
    metadata = Column(JSONB, default={}, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    """Document chunk model - represents text chunks for vector embedding."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint('document_id', 'chunk_index', name='uq_chunk_doc_index'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    page_number = Column(Integer)
    start_char = Column(Integer)
    end_char = Column(Integer)

    # Vector store reference
    weaviate_id = Column(String(255), unique=True)

    # Metadata
    metadata = Column(JSONB, default={}, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="chunks")


class VerificationJob(Base):
    """Verification job model - represents a document verification task."""

    __tablename__ = "verification_jobs"
    __table_args__ = (
        CheckConstraint('progress >= 0 AND progress <= 1', name='chk_progress_range'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    main_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"))

    status = Column(SQLEnum(VerificationStatus), default=VerificationStatus.PENDING, nullable=False)
    progress = Column(Float, default=0.0, nullable=False)

    # Statistics
    total_sentences = Column(Integer, default=0)
    verified_sentences = Column(Integer, default=0)
    validated_count = Column(Integer, default=0)
    uncertain_count = Column(Integer, default=0)
    incorrect_count = Column(Integer, default=0)

    # Celery task ID
    celery_task_id = Column(String(255))

    # Timestamps
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Error tracking
    error_message = Column(Text)

    # Relationships
    project = relationship("Project", back_populates="verification_jobs")
    main_document = relationship("Document", foreign_keys=[main_document_id])
    sentences = relationship("VerifiedSentence", back_populates="verification_job", cascade="all, delete-orphan")


class VerifiedSentence(Base):
    """Verified sentence model - represents a verified claim with citations."""

    __tablename__ = "verified_sentences"
    __table_args__ = (
        UniqueConstraint('verification_job_id', 'sentence_index', name='uq_sentence_job_index'),
        CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='chk_confidence_range'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    verification_job_id = Column(UUID(as_uuid=True), ForeignKey("verification_jobs.id", ondelete="CASCADE"), nullable=False)

    # Sentence information
    sentence_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    page_number = Column(Integer)
    start_char = Column(Integer)
    end_char = Column(Integer)

    # Verification result
    validation_result = Column(SQLEnum(ValidationResult), default=ValidationResult.PENDING, nullable=False)
    confidence_score = Column(Float)

    # AI reasoning
    reasoning = Column(Text)

    # Manual review
    manually_reviewed = Column(Boolean, default=False, nullable=False)
    reviewer_notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    verification_job = relationship("VerificationJob", back_populates="sentences")
    citations = relationship("Citation", back_populates="verified_sentence", cascade="all, delete-orphan")


class Citation(Base):
    """Citation model - represents a citation linking to source documents."""

    __tablename__ = "citations"
    __table_args__ = (
        CheckConstraint('similarity_score >= 0 AND similarity_score <= 1', name='chk_similarity_range'),
        CheckConstraint('relevance_rank >= 0', name='chk_relevance_rank'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    verified_sentence_id = Column(UUID(as_uuid=True), ForeignKey("verified_sentences.id", ondelete="CASCADE"), nullable=False)
    source_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"))

    # Citation details
    cited_text = Column(Text, nullable=False)
    page_number = Column(Integer)
    start_char = Column(Integer)
    end_char = Column(Integer)

    # Relevance metrics
    similarity_score = Column(Float)
    relevance_rank = Column(Integer)

    # Context
    context_before = Column(Text)
    context_after = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    verified_sentence = relationship("VerifiedSentence", back_populates="citations")
    source_document = relationship("Document")
