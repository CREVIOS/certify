"""Initial database schema with optimized indexes

Revision ID: 001
Revises:
Create Date: 2025-01-15 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ENUM types
    verification_status = postgresql.ENUM(
        'pending', 'indexing', 'processing', 'completed', 'failed',
        name='verification_status'
    )
    verification_status.create(op.get_bind())

    validation_result = postgresql.ENUM(
        'validated', 'uncertain', 'incorrect', 'pending',
        name='validation_result'
    )
    validation_result.create(op.get_bind())

    document_type = postgresql.ENUM(
        'main', 'supporting',
        name='document_type'
    )
    document_type.create(op.get_bind())

    # Projects table
    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('background_context', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create indexes for projects
    op.create_index('idx_projects_created_at', 'projects', ['created_at'])
    op.create_index('idx_projects_name', 'projects', ['name'], postgresql_ops={'name': 'text_pattern_ops'})

    # Enable full-text search on project name and description
    op.execute("""
        CREATE INDEX idx_projects_name_fulltext ON projects
        USING gin(to_tsvector('english', name));
    """)
    op.execute("""
        CREATE INDEX idx_projects_description_fulltext ON projects
        USING gin(to_tsvector('english', coalesce(description, '')));
    """)

    # Documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('file_path', sa.String(1000), nullable=False),
        sa.Column('file_size', sa.Integer, nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('document_type', document_type, nullable=False),
        sa.Column('page_count', sa.Integer),
        sa.Column('indexed', sa.Boolean, default=False),
        sa.Column('indexed_at', sa.DateTime),
        sa.Column('metadata', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    )

    # Create indexes for documents
    op.create_index('idx_documents_project_id', 'documents', ['project_id'])
    op.create_index('idx_documents_document_type', 'documents', ['document_type'])
    op.create_index('idx_documents_indexed', 'documents', ['indexed'])
    op.create_index('idx_documents_created_at', 'documents', ['created_at'])
    op.create_index('idx_documents_metadata', 'documents', ['metadata'], postgresql_using='gin')

    # Composite index for common queries
    op.create_index(
        'idx_documents_project_type',
        'documents',
        ['project_id', 'document_type']
    )

    # Document chunks table with partitioning support
    op.create_table(
        'document_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('page_number', sa.Integer),
        sa.Column('start_char', sa.Integer),
        sa.Column('end_char', sa.Integer),
        sa.Column('weaviate_id', sa.String(255), unique=True),
        sa.Column('metadata', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('document_id', 'chunk_index', name='uq_chunk_doc_index'),
    )

    # Create indexes for document_chunks
    op.create_index('idx_chunks_document_id', 'document_chunks', ['document_id'])
    op.create_index('idx_chunks_page_number', 'document_chunks', ['page_number'])
    op.create_index('idx_chunks_weaviate_id', 'document_chunks', ['weaviate_id'])

    # Composite index for ordered chunk retrieval
    op.create_index(
        'idx_chunks_document_index',
        'document_chunks',
        ['document_id', 'chunk_index']
    )

    # Full-text search on chunk content
    op.execute("""
        CREATE INDEX idx_chunks_content_fulltext ON document_chunks
        USING gin(to_tsvector('english', content));
    """)

    # Verification jobs table
    op.create_table(
        'verification_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('main_document_id', postgresql.UUID(as_uuid=True)),
        sa.Column('status', verification_status, nullable=False, server_default='pending'),
        sa.Column('progress', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('total_sentences', sa.Integer, default=0),
        sa.Column('verified_sentences', sa.Integer, default=0),
        sa.Column('validated_count', sa.Integer, default=0),
        sa.Column('uncertain_count', sa.Integer, default=0),
        sa.Column('incorrect_count', sa.Integer, default=0),
        sa.Column('celery_task_id', sa.String(255)),
        sa.Column('started_at', sa.DateTime),
        sa.Column('completed_at', sa.DateTime),
        sa.Column('error_message', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['main_document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.CheckConstraint('progress >= 0 AND progress <= 1', name='chk_progress_range'),
    )

    # Create indexes for verification_jobs
    op.create_index('idx_jobs_project_id', 'verification_jobs', ['project_id'])
    op.create_index('idx_jobs_status', 'verification_jobs', ['status'])
    op.create_index('idx_jobs_celery_task_id', 'verification_jobs', ['celery_task_id'])
    op.create_index('idx_jobs_created_at', 'verification_jobs', ['created_at'])

    # Composite index for active job queries
    op.create_index(
        'idx_jobs_project_status',
        'verification_jobs',
        ['project_id', 'status']
    )

    # Verified sentences table - this will be the largest table
    op.create_table(
        'verified_sentences',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('verification_job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sentence_index', sa.Integer, nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('page_number', sa.Integer),
        sa.Column('start_char', sa.Integer),
        sa.Column('end_char', sa.Integer),
        sa.Column('validation_result', validation_result, nullable=False, server_default='pending'),
        sa.Column('confidence_score', sa.Float),
        sa.Column('reasoning', sa.Text),
        sa.Column('manually_reviewed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('reviewer_notes', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['verification_job_id'], ['verification_jobs.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('verification_job_id', 'sentence_index', name='uq_sentence_job_index'),
        sa.CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='chk_confidence_range'),
    )

    # Create indexes for verified_sentences
    op.create_index('idx_sentences_job_id', 'verified_sentences', ['verification_job_id'])
    op.create_index('idx_sentences_validation_result', 'verified_sentences', ['validation_result'])
    op.create_index('idx_sentences_confidence_score', 'verified_sentences', ['confidence_score'])
    op.create_index('idx_sentences_page_number', 'verified_sentences', ['page_number'])
    op.create_index('idx_sentences_manually_reviewed', 'verified_sentences', ['manually_reviewed'])

    # Composite indexes for common queries
    op.create_index(
        'idx_sentences_job_index',
        'verified_sentences',
        ['verification_job_id', 'sentence_index']
    )
    op.create_index(
        'idx_sentences_job_result',
        'verified_sentences',
        ['verification_job_id', 'validation_result']
    )
    op.create_index(
        'idx_sentences_job_page',
        'verified_sentences',
        ['verification_job_id', 'page_number']
    )

    # Full-text search on sentence content
    op.execute("""
        CREATE INDEX idx_sentences_content_fulltext ON verified_sentences
        USING gin(to_tsvector('english', content));
    """)

    # Citations table
    op.create_table(
        'citations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('verified_sentence_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_document_id', postgresql.UUID(as_uuid=True)),
        sa.Column('cited_text', sa.Text, nullable=False),
        sa.Column('page_number', sa.Integer),
        sa.Column('start_char', sa.Integer),
        sa.Column('end_char', sa.Integer),
        sa.Column('similarity_score', sa.Float),
        sa.Column('relevance_rank', sa.Integer),
        sa.Column('context_before', sa.Text),
        sa.Column('context_after', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['verified_sentence_id'], ['verified_sentences.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.CheckConstraint('similarity_score >= 0 AND similarity_score <= 1', name='chk_similarity_range'),
        sa.CheckConstraint('relevance_rank >= 0', name='chk_relevance_rank'),
    )

    # Create indexes for citations
    op.create_index('idx_citations_sentence_id', 'citations', ['verified_sentence_id'])
    op.create_index('idx_citations_source_doc_id', 'citations', ['source_document_id'])
    op.create_index('idx_citations_similarity_score', 'citations', ['similarity_score'])
    op.create_index('idx_citations_relevance_rank', 'citations', ['relevance_rank'])

    # Composite index for citation retrieval
    op.create_index(
        'idx_citations_sentence_rank',
        'citations',
        ['verified_sentence_id', 'relevance_rank']
    )

    # Full-text search on cited text
    op.execute("""
        CREATE INDEX idx_citations_text_fulltext ON citations
        USING gin(to_tsvector('english', cited_text));
    """)

    # Create function for automatic updated_at timestamp
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # Create triggers for updated_at
    op.execute("""
        CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    op.execute("""
        CREATE TRIGGER update_verification_jobs_updated_at BEFORE UPDATE ON verification_jobs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    op.execute("""
        CREATE TRIGGER update_verified_sentences_updated_at BEFORE UPDATE ON verified_sentences
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS update_verified_sentences_updated_at ON verified_sentences")
    op.execute("DROP TRIGGER IF EXISTS update_verification_jobs_updated_at ON verification_jobs")
    op.execute("DROP TRIGGER IF EXISTS update_projects_updated_at ON projects")

    # Drop function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop tables in reverse order
    op.drop_table('citations')
    op.drop_table('verified_sentences')
    op.drop_table('verification_jobs')
    op.drop_table('document_chunks')
    op.drop_table('documents')
    op.drop_table('projects')

    # Drop ENUM types
    op.execute("DROP TYPE IF EXISTS document_type")
    op.execute("DROP TYPE IF EXISTS validation_result")
    op.execute("DROP TYPE IF EXISTS verification_status")
