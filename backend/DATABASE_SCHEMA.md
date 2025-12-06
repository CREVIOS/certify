# Database Schema Documentation

## Overview

Optimized PostgreSQL schema for IPO Document Verification System with AI-powered citation tracking.

## Performance Optimizations

### Indexes Strategy

1. **B-tree Indexes**: Standard queries on UUID, status, timestamps
2. **GIN Indexes**: Full-text search, JSONB columns
3. **Composite Indexes**: Multi-column queries (project_id + status, etc.)
4. **Partial Indexes**: Filtered queries on specific conditions

### Full-Text Search

- Projects: name, description
- Document chunks: content
- Verified sentences: content
- Citations: cited_text

### JSONB Optimization

- Metadata fields use JSONB for flexibility
- GIN indexes for fast JSON queries
- Efficient storage and query performance

## Tables

### projects

Primary table for verification projects.

**Columns:**

- `id` (UUID, PK): Unique identifier
- `name` (VARCHAR(255)): Project name
- `description` (TEXT): Optional description
- `background_context` (TEXT): Background context for verification
- `created_at`, `updated_at` (TIMESTAMP): Audit timestamps

**Indexes:**

- `idx_projects_created_at`: Order by creation date
- `idx_projects_name`: Fast name lookups with pattern ops
- `idx_projects_name_fulltext`: Full-text search on name
- `idx_projects_description_fulltext`: Full-text search on description

**Relationships:**

- 1:N with documents
- 1:N with verification_jobs

---

### documents

Stores uploaded PDF documents (main and supporting).

**Columns:**

- `id` (UUID, PK): Unique identifier
- `project_id` (UUID, FK): Parent project
- `filename` (VARCHAR(500)): Stored filename
- `original_filename` (VARCHAR(500)): Original upload name
- `file_path` (VARCHAR(1000)): Storage path (Supabase/local)
- `file_size` (INTEGER): Size in bytes
- `mime_type` (VARCHAR(100)): MIME type
- `document_type` (ENUM): 'main' or 'supporting'
- `page_count` (INTEGER): Number of pages
- `indexed` (BOOLEAN): Vector indexing status
- `indexed_at` (TIMESTAMP): Indexing completion time
- `metadata` (JSONB): Flexible metadata storage
- `created_at` (TIMESTAMP): Upload timestamp

**Indexes:**

- `idx_documents_project_id`: FK index
- `idx_documents_document_type`: Filter by type
- `idx_documents_indexed`: Find unindexed documents
- `idx_documents_created_at`: Order by upload date
- `idx_documents_metadata`: GIN index for JSON queries
- `idx_documents_project_type`: Composite for common queries

**Relationships:**

- N:1 with projects
- 1:N with document_chunks
- Referenced by citations

**ON DELETE:** CASCADE from projects

---

### document_chunks

Text chunks for vector embedding and retrieval.

**Columns:**

- `id` (UUID, PK): Unique identifier
- `document_id` (UUID, FK): Parent document
- `chunk_index` (INTEGER): Sequential order
- `content` (TEXT): Chunk text content
- `page_number` (INTEGER): Source page
- `start_char`, `end_char` (INTEGER): Character positions
- `weaviate_id` (VARCHAR(255), UNIQUE): Weaviate reference
- `metadata` (JSONB, NOT NULL): Additional metadata
- `created_at` (TIMESTAMP): Creation timestamp

**Constraints:**

- **UNIQUE** (`document_id`, `chunk_index`): Prevents duplicate chunks

**Indexes:**

- `idx_chunks_document_id`: FK index
- `idx_chunks_page_number`: Filter by page
- `idx_chunks_weaviate_id`: Unique constraint enforcement
- `idx_chunks_document_index`: Composite for ordered retrieval
- `idx_chunks_content_fulltext`: Full-text search

**Relationships:**

- N:1 with documents

**ON DELETE:** CASCADE from documents

---

### verification_jobs

Async verification tasks tracked via Celery.

**Columns:**

- `id` (UUID, PK): Unique identifier
- `project_id` (UUID, FK): Parent project
- `main_document_id` (UUID, FK): Document being verified
- `status` (ENUM): pending|indexing|processing|completed|failed
- `progress` (FLOAT, NOT NULL): 0.0 to 1.0
- `total_sentences` (INTEGER): Total count
- `verified_sentences` (INTEGER): Completed count
- `validated_count` (INTEGER): Green (correct)
- `uncertain_count` (INTEGER): Yellow (uncertain)
- `incorrect_count` (INTEGER): Red (incorrect)
- `celery_task_id` (VARCHAR(255)): Celery task reference
- `started_at`, `completed_at` (TIMESTAMP): Execution times
- `error_message` (TEXT): Failure details
- `created_at`, `updated_at` (TIMESTAMP): Audit timestamps

**Constraints:**

- **CHECK** (`progress` >= 0 AND `progress` <= 1): Validates progress range

**Indexes:**

- `idx_jobs_project_id`: FK index
- `idx_jobs_status`: Filter by status
- `idx_jobs_celery_task_id`: Lookup by Celery ID
- `idx_jobs_created_at`: Order by creation
- `idx_jobs_project_status`: Composite for active jobs

**Relationships:**

- N:1 with projects
- N:1 with documents (main_document_id)
- 1:N with verified_sentences

**ON DELETE:**

- CASCADE from projects
- SET NULL from documents

---

### verified_sentences

**Largest table** - Stores individual sentence verification results.

**Columns:**

- `id` (UUID, PK): Unique identifier
- `verification_job_id` (UUID, FK): Parent job
- `sentence_index` (INTEGER): Sequential order in document
- `content` (TEXT): Sentence text
- `page_number` (INTEGER): Source page
- `start_char`, `end_char` (INTEGER): Character positions
- `validation_result` (ENUM): validated|uncertain|incorrect|pending
- `confidence_score` (FLOAT): AI confidence (0.0-1.0)
- `reasoning` (TEXT): AI explanation
- `manually_reviewed` (BOOLEAN, NOT NULL): Human review flag
- `reviewer_notes` (TEXT): Manual review notes
- `created_at`, `updated_at` (TIMESTAMP, NOT NULL): Audit timestamps

**Note:** Citations are stored in the separate `citations` table (NOT as JSON field).

**Constraints:**

- **UNIQUE** (`verification_job_id`, `sentence_index`): Prevents duplicate sentences
- **CHECK** (`confidence_score` >= 0 AND `confidence_score` <= 1): Validates confidence range

**Indexes:**

- `idx_sentences_job_id`: FK index
- `idx_sentences_validation_result`: Filter by result
- `idx_sentences_confidence_score`: Sort by confidence
- `idx_sentences_page_number`: Filter by page
- `idx_sentences_manually_reviewed`: Find unreviewed
- `idx_sentences_job_index`: Ordered retrieval
- `idx_sentences_job_result`: Filter results per job
- `idx_sentences_job_page`: Page-specific queries
- `idx_sentences_content_fulltext`: Full-text search

**Relationships:**

- N:1 with verification_jobs
- 1:N with citations

**ON DELETE:** CASCADE from verification_jobs

**Performance Notes:**

- Will contain millions of rows for large projects
- Heavy read/write during verification
- Optimized with multiple composite indexes

---

### citations

Links verified sentences to source documents with page-level accuracy.

**Note:** This is the **ONLY** place where citations are stored (no JSON field in verified_sentences).

**Columns:**

- `id` (UUID, PK): Unique identifier
- `verified_sentence_id` (UUID, FK): Sentence being cited
- `source_document_id` (UUID, FK): Supporting document
- `cited_text` (TEXT, NOT NULL): Exact quote from source
- `page_number` (INTEGER): Source page
- `start_char`, `end_char` (INTEGER): Character positions
- `similarity_score` (FLOAT): Vector similarity (0.0-1.0)
- `relevance_rank` (INTEGER): Ranking within sentence citations
- `context_before`, `context_after` (TEXT): Surrounding text
- `created_at` (TIMESTAMP, NOT NULL): Creation timestamp

**Constraints:**

- **CHECK** (`similarity_score` >= 0 AND `similarity_score` <= 1): Validates similarity range
- **CHECK** (`relevance_rank` >= 0): Validates ranking is non-negative

**Indexes:**

- `idx_citations_sentence_id`: FK index
- `idx_citations_source_doc_id`: FK index
- `idx_citations_similarity_score`: Sort by relevance
- `idx_citations_relevance_rank`: Ranking order
- `idx_citations_sentence_rank`: Composite for ordered retrieval
- `idx_citations_text_fulltext`: Full-text search

**Relationships:**

- N:1 with verified_sentences (back-populates: verified_sentence.citations)
- N:1 with documents

**ON DELETE:**

- CASCADE from verified_sentences
- SET NULL from documents

---

## Triggers

### update_updated_at_column()

Automatically updates `updated_at` timestamp on row modification.

**Applied to:**

- projects
- verification_jobs
- verified_sentences

---

## Query Optimization Examples

### Get project with stats

```sql
SELECT
    p.*,
    COUNT(DISTINCT d.id) as document_count,
    vj.validated_count,
    vj.uncertain_count,
    vj.incorrect_count,
    vj.progress
FROM projects p
LEFT JOIN documents d ON d.project_id = p.id
LEFT JOIN verification_jobs vj ON vj.project_id = p.id
WHERE p.id = $1
GROUP BY p.id, vj.id;
```

Uses: `idx_documents_project_id`, `idx_jobs_project_id`

### Get sentences by validation result

```sql
SELECT * FROM verified_sentences
WHERE verification_job_id = $1
  AND validation_result = $2
ORDER BY sentence_index;
```

Uses: `idx_sentences_job_result`

### Full-text search across sentences

```sql
SELECT vs.*, vj.project_id
FROM verified_sentences vs
JOIN verification_jobs vj ON vs.verification_job_id = vj.id
WHERE to_tsvector('english', vs.content) @@ to_tsquery('english', $1)
  AND vj.project_id = $2;
```

Uses: `idx_sentences_content_fulltext`, `idx_sentences_job_id`

### Get citations with source context

```sql
SELECT c.*, d.original_filename, d.page_count
FROM citations c
JOIN documents d ON c.source_document_id = d.id
WHERE c.verified_sentence_id = $1
ORDER BY c.relevance_rank ASC;
```

Uses: `idx_citations_sentence_rank`

---

## Scaling Considerations

### Connection Pooling

- SQLAlchemy pool: 20 connections + 10 overflow
- PgBouncer recommended for > 100 concurrent users

### Partitioning (Future)

- `verified_sentences`: Partition by `created_at` (monthly)
- `citations`: Partition by `created_at` (monthly)
- Implement when tables exceed 10M rows

### Caching Strategy

- Redis cache for:
  - Project summaries (1 hour TTL)
  - Verification job status (5 min TTL)
  - Document metadata (6 hours TTL)
- Invalidate on updates

### Read Replicas

- Route heavy reads (sentence browsing, search) to replicas
- Primary for writes only

---

## Backup & Recovery

### Continuous Archiving

```bash
# Enable WAL archiving
archive_mode = on
archive_command = 'cp %p /archive/%f'
```

### Point-in-Time Recovery

```bash
# Create base backup
pg_basebackup -D /backup/base -Ft -z -P

# Restore to specific time
restore_command = 'cp /archive/%f %p'
recovery_target_time = '2025-01-15 12:00:00'
```

---

## Monitoring Queries

### Table sizes

```sql
SELECT
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS data_size,
    pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS index_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

### Index usage

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
```

### Slow queries

```sql
SELECT
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements
WHERE mean_time > 100
ORDER BY total_time DESC
LIMIT 20;
```
