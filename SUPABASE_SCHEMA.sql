-- ============================================
-- SUPABASE DATABASE SCHEMA
-- IPO Document Verification System
-- ============================================
-- This schema is optimized for Supabase PostgreSQL
-- Run this entire file in the Supabase SQL Editor
-- ============================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For fuzzy text search

-- ============================================
-- ENUM TYPES
-- ============================================

CREATE TYPE verification_status AS ENUM (
    'pending',
    'indexing', 
    'processing',
    'completed',
    'failed'
);

CREATE TYPE validation_result AS ENUM (
    'validated',   -- Green - Correct
    'uncertain',   -- Yellow - Needs review
    'incorrect',   -- Red - Contradicts evidence
    'pending'      -- Not yet verified
);

CREATE TYPE document_type AS ENUM (
    'main',
    'supporting'
);

-- ============================================
-- USERS TABLE
-- ============================================
-- Custom users table that extends Supabase auth.users
-- This table stores additional user profile information

CREATE TABLE users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    last_active TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    
    -- Additional user fields
    avatar_url TEXT,
    organization VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user',
    
    CONSTRAINT email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$')
);

-- Indexes for users table
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_last_active ON users(last_active DESC);
CREATE INDEX idx_users_organization ON users(organization) WHERE organization IS NOT NULL;
CREATE INDEX idx_users_role ON users(role);

-- ============================================
-- PROJECTS TABLE
-- ============================================

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    background_context TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    
    -- Project metadata
    status VARCHAR(50) DEFAULT 'active',
    is_archived BOOLEAN DEFAULT FALSE,
    archived_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for projects
CREATE INDEX idx_projects_user_id ON projects(user_id);
CREATE INDEX idx_projects_created_at ON projects(created_at DESC);
CREATE INDEX idx_projects_status ON projects(status);
CREATE INDEX idx_projects_is_archived ON projects(is_archived);
CREATE INDEX idx_projects_name ON projects(name text_pattern_ops);
CREATE INDEX idx_projects_user_created ON projects(user_id, created_at DESC);
CREATE INDEX idx_projects_user_status ON projects(user_id, status) WHERE is_archived = FALSE;

-- Full-text search indexes
CREATE INDEX idx_projects_name_fulltext ON projects 
    USING gin(to_tsvector('english', name));
CREATE INDEX idx_projects_description_fulltext ON projects 
    USING gin(to_tsvector('english', COALESCE(description, '')));

-- ============================================
-- DOCUMENTS TABLE
-- ============================================

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    original_filename VARCHAR(500) NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    document_type document_type NOT NULL,
    page_count INTEGER,
    indexed BOOLEAN DEFAULT FALSE,
    indexed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    
    CONSTRAINT file_size_positive CHECK (file_size > 0),
    CONSTRAINT page_count_positive CHECK (page_count IS NULL OR page_count > 0)
);

-- Indexes for documents
CREATE INDEX idx_documents_project_id ON documents(project_id);
CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_document_type ON documents(document_type);
CREATE INDEX idx_documents_indexed ON documents(indexed);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX idx_documents_metadata ON documents USING gin(metadata);
CREATE INDEX idx_documents_project_type ON documents(project_id, document_type);
CREATE INDEX idx_documents_user_created ON documents(user_id, created_at DESC);

-- ============================================
-- DOCUMENT CHUNKS TABLE
-- ============================================

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page_number INTEGER,
    start_char INTEGER,
    end_char INTEGER,
    weaviate_id VARCHAR(255) UNIQUE,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    
    CONSTRAINT uq_chunk_doc_index UNIQUE (document_id, chunk_index),
    CONSTRAINT chunk_index_positive CHECK (chunk_index >= 0),
    CONSTRAINT char_positions_valid CHECK (end_char IS NULL OR start_char IS NULL OR end_char > start_char)
);

-- Indexes for document_chunks
CREATE INDEX idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX idx_chunks_page_number ON document_chunks(page_number);
CREATE INDEX idx_chunks_weaviate_id ON document_chunks(weaviate_id);
CREATE INDEX idx_chunks_document_index ON document_chunks(document_id, chunk_index);

-- Full-text search on chunk content
CREATE INDEX idx_chunks_content_fulltext ON document_chunks 
    USING gin(to_tsvector('english', content));

-- ============================================
-- VERIFICATION JOBS TABLE
-- ============================================

CREATE TABLE verification_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    main_document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    status verification_status NOT NULL DEFAULT 'pending',
    progress FLOAT NOT NULL DEFAULT 0.0,
    
    -- Statistics
    total_sentences INTEGER DEFAULT 0,
    verified_sentences INTEGER DEFAULT 0,
    validated_count INTEGER DEFAULT 0,
    uncertain_count INTEGER DEFAULT 0,
    incorrect_count INTEGER DEFAULT 0,
    
    -- Task tracking
    celery_task_id VARCHAR(255),
    
    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    
    -- Error tracking
    error_message TEXT,
    
    CONSTRAINT chk_progress_range CHECK (progress >= 0 AND progress <= 1),
    CONSTRAINT chk_sentences_counts CHECK (
        total_sentences >= 0 AND
        verified_sentences >= 0 AND
        validated_count >= 0 AND
        uncertain_count >= 0 AND
        incorrect_count >= 0 AND
        verified_sentences <= total_sentences
    )
);

-- Indexes for verification_jobs
CREATE INDEX idx_jobs_project_id ON verification_jobs(project_id);
CREATE INDEX idx_jobs_user_id ON verification_jobs(user_id);
CREATE INDEX idx_jobs_status ON verification_jobs(status);
CREATE INDEX idx_jobs_celery_task_id ON verification_jobs(celery_task_id);
CREATE INDEX idx_jobs_created_at ON verification_jobs(created_at DESC);
CREATE INDEX idx_jobs_project_status ON verification_jobs(project_id, status);
CREATE INDEX idx_jobs_user_created ON verification_jobs(user_id, created_at DESC);
CREATE INDEX idx_jobs_user_status ON verification_jobs(user_id, status);

-- ============================================
-- VERIFIED SENTENCES TABLE (LARGEST TABLE)
-- ============================================

CREATE TABLE verified_sentences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    verification_job_id UUID NOT NULL REFERENCES verification_jobs(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Sentence information
    sentence_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page_number INTEGER,
    start_char INTEGER,
    end_char INTEGER,
    
    -- Verification result
    validation_result validation_result NOT NULL DEFAULT 'pending',
    confidence_score FLOAT,
    reasoning TEXT,
    
    -- Manual review
    manually_reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    reviewer_notes TEXT,
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    
    CONSTRAINT uq_sentence_job_index UNIQUE (verification_job_id, sentence_index),
    CONSTRAINT chk_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT chk_sentence_index_positive CHECK (sentence_index >= 0),
    CONSTRAINT chk_char_positions_valid CHECK (end_char IS NULL OR start_char IS NULL OR end_char > start_char),
    CONSTRAINT chk_review_consistency CHECK (
        (manually_reviewed = FALSE AND reviewed_by IS NULL AND reviewed_at IS NULL) OR
        (manually_reviewed = TRUE AND reviewed_by IS NOT NULL)
    )
);

-- Indexes for verified_sentences (critical for performance)
CREATE INDEX idx_sentences_job_id ON verified_sentences(verification_job_id);
CREATE INDEX idx_sentences_user_id ON verified_sentences(user_id);
CREATE INDEX idx_sentences_validation_result ON verified_sentences(validation_result);
CREATE INDEX idx_sentences_confidence_score ON verified_sentences(confidence_score DESC NULLS LAST);
CREATE INDEX idx_sentences_page_number ON verified_sentences(page_number);
CREATE INDEX idx_sentences_manually_reviewed ON verified_sentences(manually_reviewed);
CREATE INDEX idx_sentences_reviewed_by ON verified_sentences(reviewed_by) WHERE reviewed_by IS NOT NULL;

-- Composite indexes for common queries
CREATE INDEX idx_sentences_job_index ON verified_sentences(verification_job_id, sentence_index);
CREATE INDEX idx_sentences_job_result ON verified_sentences(verification_job_id, validation_result);
CREATE INDEX idx_sentences_job_page ON verified_sentences(verification_job_id, page_number);
CREATE INDEX idx_sentences_user_reviewed ON verified_sentences(user_id, manually_reviewed);

-- Full-text search on sentence content
CREATE INDEX idx_sentences_content_fulltext ON verified_sentences 
    USING gin(to_tsvector('english', content));

-- ============================================
-- CITATIONS TABLE
-- ============================================

CREATE TABLE citations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    verified_sentence_id UUID NOT NULL REFERENCES verified_sentences(id) ON DELETE CASCADE,
    source_document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    
    -- Citation details
    cited_text TEXT NOT NULL,
    page_number INTEGER,
    start_char INTEGER,
    end_char INTEGER,
    
    -- Relevance metrics
    similarity_score FLOAT,
    relevance_rank INTEGER,
    
    -- Context
    context_before TEXT,
    context_after TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    
    CONSTRAINT chk_similarity_range CHECK (similarity_score IS NULL OR (similarity_score >= 0 AND similarity_score <= 1)),
    CONSTRAINT chk_relevance_rank CHECK (relevance_rank IS NULL OR relevance_rank >= 0),
    CONSTRAINT chk_char_positions_valid CHECK (end_char IS NULL OR start_char IS NULL OR end_char > start_char)
);

-- Indexes for citations
CREATE INDEX idx_citations_sentence_id ON citations(verified_sentence_id);
CREATE INDEX idx_citations_source_doc_id ON citations(source_document_id);
CREATE INDEX idx_citations_similarity_score ON citations(similarity_score DESC NULLS LAST);
CREATE INDEX idx_citations_relevance_rank ON citations(relevance_rank ASC NULLS LAST);
CREATE INDEX idx_citations_sentence_rank ON citations(verified_sentence_id, relevance_rank);

-- Full-text search on cited text
CREATE INDEX idx_citations_text_fulltext ON citations 
    USING gin(to_tsvector('english', cited_text));

-- ============================================
-- ACTIVITY LOG TABLE (NEW)
-- ============================================
-- Track user activities for audit and analytics

CREATE TABLE activity_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID,
    metadata JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Indexes for activity_log
CREATE INDEX idx_activity_user_id ON activity_log(user_id);
CREATE INDEX idx_activity_created_at ON activity_log(created_at DESC);
CREATE INDEX idx_activity_entity ON activity_log(entity_type, entity_id);
CREATE INDEX idx_activity_user_created ON activity_log(user_id, created_at DESC);
CREATE INDEX idx_activity_action ON activity_log(action);

-- ============================================
-- TRIGGERS & FUNCTIONS
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Function to update user's last_active timestamp
CREATE OR REPLACE FUNCTION update_user_last_active()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = NEW.user_id;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_projects_updated_at 
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_verification_jobs_updated_at 
    BEFORE UPDATE ON verification_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_verified_sentences_updated_at 
    BEFORE UPDATE ON verified_sentences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Apply last_active triggers
CREATE TRIGGER update_user_last_active_on_project 
    AFTER INSERT ON projects
    FOR EACH ROW EXECUTE FUNCTION update_user_last_active();

CREATE TRIGGER update_user_last_active_on_document 
    AFTER INSERT ON documents
    FOR EACH ROW EXECUTE FUNCTION update_user_last_active();

CREATE TRIGGER update_user_last_active_on_verification 
    AFTER INSERT ON verification_jobs
    FOR EACH ROW EXECUTE FUNCTION update_user_last_active();

CREATE TRIGGER update_user_last_active_on_sentence_review 
    AFTER UPDATE ON verified_sentences
    FOR EACH ROW 
    WHEN (NEW.manually_reviewed = TRUE AND OLD.manually_reviewed = FALSE)
    EXECUTE FUNCTION update_user_last_active();

-- ============================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================
-- Enable RLS for multi-tenant security in Supabase

-- Enable RLS on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE verified_sentences ENABLE ROW LEVEL SECURITY;
ALTER TABLE citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;

-- Users policies
CREATE POLICY "Users can view their own profile"
    ON users FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update their own profile"
    ON users FOR UPDATE
    USING (auth.uid() = id);

CREATE POLICY "Service role can manage all users"
    ON users FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- Projects policies
CREATE POLICY "Users can view their own projects"
    ON projects FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can create their own projects"
    ON projects FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own projects"
    ON projects FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own projects"
    ON projects FOR DELETE
    USING (auth.uid() = user_id);

-- Documents policies
CREATE POLICY "Users can view documents from their projects"
    ON documents FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM projects 
            WHERE projects.id = documents.project_id 
            AND projects.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can create documents in their projects"
    ON documents FOR INSERT
    WITH CHECK (
        auth.uid() = user_id AND
        EXISTS (
            SELECT 1 FROM projects 
            WHERE projects.id = project_id 
            AND projects.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete documents from their projects"
    ON documents FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM projects 
            WHERE projects.id = documents.project_id 
            AND projects.user_id = auth.uid()
        )
    );

-- Document chunks policies
CREATE POLICY "Users can view chunks from their documents"
    ON document_chunks FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM documents d
            JOIN projects p ON p.id = d.project_id
            WHERE d.id = document_chunks.document_id 
            AND p.user_id = auth.uid()
        )
    );

CREATE POLICY "Service role can manage chunks"
    ON document_chunks FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- Verification jobs policies
CREATE POLICY "Users can view their verification jobs"
    ON verification_jobs FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM projects 
            WHERE projects.id = verification_jobs.project_id 
            AND projects.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can create verification jobs in their projects"
    ON verification_jobs FOR INSERT
    WITH CHECK (
        auth.uid() = user_id AND
        EXISTS (
            SELECT 1 FROM projects 
            WHERE projects.id = project_id 
            AND projects.user_id = auth.uid()
        )
    );

CREATE POLICY "Service role can manage verification jobs"
    ON verification_jobs FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- Verified sentences policies
CREATE POLICY "Users can view sentences from their verification jobs"
    ON verified_sentences FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM verification_jobs vj
            JOIN projects p ON p.id = vj.project_id
            WHERE vj.id = verified_sentences.verification_job_id 
            AND p.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update sentences from their verification jobs"
    ON verified_sentences FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM verification_jobs vj
            JOIN projects p ON p.id = vj.project_id
            WHERE vj.id = verified_sentences.verification_job_id 
            AND p.user_id = auth.uid()
        )
    );

CREATE POLICY "Service role can manage verified sentences"
    ON verified_sentences FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- Citations policies
CREATE POLICY "Users can view citations from their sentences"
    ON citations FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM verified_sentences vs
            JOIN verification_jobs vj ON vj.id = vs.verification_job_id
            JOIN projects p ON p.id = vj.project_id
            WHERE vs.id = citations.verified_sentence_id 
            AND p.user_id = auth.uid()
        )
    );

CREATE POLICY "Service role can manage citations"
    ON citations FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- Activity log policies
CREATE POLICY "Users can view their own activity"
    ON activity_log FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own activity"
    ON activity_log FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- ============================================
-- HELPFUL VIEWS
-- ============================================

-- View for project statistics
CREATE OR REPLACE VIEW project_stats AS
SELECT 
    p.id as project_id,
    p.user_id,
    p.name as project_name,
    COUNT(DISTINCT d.id) as document_count,
    COUNT(DISTINCT CASE WHEN d.document_type = 'main' THEN d.id END) as main_document_count,
    COUNT(DISTINCT CASE WHEN d.document_type = 'supporting' THEN d.id END) as supporting_document_count,
    COUNT(DISTINCT vj.id) as verification_job_count,
    MAX(vj.created_at) as last_verification_at,
    SUM(vj.total_sentences) as total_sentences,
    SUM(vj.verified_sentences) as verified_sentences,
    SUM(vj.validated_count) as validated_count,
    SUM(vj.uncertain_count) as uncertain_count,
    SUM(vj.incorrect_count) as incorrect_count,
    p.created_at,
    p.updated_at
FROM projects p
LEFT JOIN documents d ON d.project_id = p.id
LEFT JOIN verification_jobs vj ON vj.project_id = p.id
GROUP BY p.id, p.user_id, p.name, p.created_at, p.updated_at;

-- View for user statistics
CREATE OR REPLACE VIEW user_stats AS
SELECT 
    u.id as user_id,
    u.name,
    u.email,
    u.last_active,
    COUNT(DISTINCT p.id) as project_count,
    COUNT(DISTINCT d.id) as document_count,
    COUNT(DISTINCT vj.id) as verification_job_count,
    COUNT(DISTINCT vs.id) as verified_sentence_count,
    COUNT(DISTINCT CASE WHEN vs.manually_reviewed = TRUE THEN vs.id END) as reviewed_sentence_count,
    u.created_at as user_since
FROM users u
LEFT JOIN projects p ON p.user_id = u.id
LEFT JOIN documents d ON d.user_id = u.id
LEFT JOIN verification_jobs vj ON vj.user_id = u.id
LEFT JOIN verified_sentences vs ON vs.user_id = u.id
GROUP BY u.id, u.name, u.email, u.last_active, u.created_at;

-- ============================================
-- UTILITY FUNCTIONS
-- ============================================

-- Function to get project statistics
CREATE OR REPLACE FUNCTION get_project_stats(project_uuid UUID)
RETURNS TABLE (
    project_id UUID,
    document_count BIGINT,
    verification_job_count BIGINT,
    total_sentences BIGINT,
    verified_sentences BIGINT,
    validated_count BIGINT,
    uncertain_count BIGINT,
    incorrect_count BIGINT,
    completion_percentage FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.id,
        COUNT(DISTINCT d.id),
        COUNT(DISTINCT vj.id),
        COALESCE(SUM(vj.total_sentences), 0),
        COALESCE(SUM(vj.verified_sentences), 0),
        COALESCE(SUM(vj.validated_count), 0),
        COALESCE(SUM(vj.uncertain_count), 0),
        COALESCE(SUM(vj.incorrect_count), 0),
        CASE 
            WHEN COALESCE(SUM(vj.total_sentences), 0) = 0 THEN 0.0
            ELSE (COALESCE(SUM(vj.verified_sentences), 0)::FLOAT / SUM(vj.total_sentences)::FLOAT) * 100
        END
    FROM projects p
    LEFT JOIN documents d ON d.project_id = p.id
    LEFT JOIN verification_jobs vj ON vj.project_id = p.id
    WHERE p.id = project_uuid
    GROUP BY p.id;
END;
$$ LANGUAGE plpgsql;

-- Function to log user activity
CREATE OR REPLACE FUNCTION log_activity(
    p_user_id UUID,
    p_action VARCHAR,
    p_entity_type VARCHAR,
    p_entity_id UUID DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'
)
RETURNS UUID AS $$
DECLARE
    v_log_id UUID;
BEGIN
    INSERT INTO activity_log (user_id, action, entity_type, entity_id, metadata)
    VALUES (p_user_id, p_action, p_entity_type, p_entity_id, p_metadata)
    RETURNING id INTO v_log_id;
    
    RETURN v_log_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- SAMPLE DATA (OPTIONAL - REMOVE IN PRODUCTION)
-- ============================================

-- Insert a sample user (you'll need to create this user in Supabase Auth first)
-- Uncomment and modify with your actual auth.users ID
/*
INSERT INTO users (id, name, email) VALUES
    ('00000000-0000-0000-0000-000000000000', 'Test User', 'test@example.com');
*/

-- ============================================
-- PERFORMANCE MONITORING
-- ============================================

-- Create a view for monitoring table sizes
CREATE OR REPLACE VIEW table_sizes AS
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS data_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS index_size,
    pg_total_relation_size(schemaname||'.'||tablename) AS bytes
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY bytes DESC;

-- ============================================
-- COMPLETION MESSAGE
-- ============================================

DO $$ 
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Database schema created successfully!';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Tables created: users, projects, documents, document_chunks,';
    RAISE NOTICE '                verification_jobs, verified_sentences, citations, activity_log';
    RAISE NOTICE '';
    RAISE NOTICE 'Features enabled:';
    RAISE NOTICE '  ✓ Row Level Security (RLS)';
    RAISE NOTICE '  ✓ Full-text search indexes';
    RAISE NOTICE '  ✓ Automatic timestamps';
    RAISE NOTICE '  ✓ User activity tracking';
    RAISE NOTICE '  ✓ Performance indexes';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  1. Create users via Supabase Auth';
    RAISE NOTICE '  2. Add users to the users table';
    RAISE NOTICE '  3. Configure Supabase Storage for document uploads';
    RAISE NOTICE '  4. Update your backend configuration with Supabase credentials';
    RAISE NOTICE '============================================';
END $$;

