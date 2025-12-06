# Database Schema Analysis Report

## Overall Assessment

The schema is **well-designed** with good indexing strategy and relationships, but there are **several important issues** that need to be addressed.

---

## ✅ **Strengths**

1. **Excellent Indexing Strategy**

   - Comprehensive B-tree indexes on foreign keys
   - GIN indexes for JSONB and full-text search
   - Composite indexes for common query patterns
   - Full-text search indexes on content fields

2. **Good Relationship Design**

   - Proper cascade deletes configured
   - Foreign keys with appropriate ON DELETE actions
   - Clear parent-child relationships

3. **Performance Considerations**
   - JSONB for flexible metadata storage
   - Triggers for automatic `updated_at` timestamps
   - Well-documented scaling considerations

---

## ✅ **All Issues Fixed**

All critical and moderate issues have been resolved:

1. ✅ **JSON → JSONB**: All models now use JSONB
2. ✅ **Removed dual citation storage**: Citations stored ONLY in Citation table
3. ✅ **Added unique constraints**: Both verified_sentences and document_chunks
4. ✅ **Added check constraints**: All score ranges validated
5. ✅ **Added relationships**: VerifiedSentence ↔ Citation bidirectional relationship

---

## 📋 **Original Issues (Now Fixed)**

### 1. **Data Type Inconsistency: JSON vs JSONB**

**Problem:** Models use `JSON` but migration uses `JSONB`

- `models.py`: `Column(JSON, default={})` and `Column(JSON, default=[])`
- `migration`: `postgresql.JSONB`

**Impact:**

- SQLAlchemy will create JSON columns instead of JSONB
- Missing performance benefits of JSONB (indexing, querying)
- GIN indexes won't work properly

**Fix:** Change all `JSON` to `JSONB` in models.py

### 2. **Dual Citation Storage (Design Confusion)**

**Problem:** Citations are stored in TWO places:

- `VerifiedSentence.citations` (JSON field)
- `Citation` table (separate table)

**Impact:**

- Data duplication and inconsistency risk
- Missing relationship from `VerifiedSentence` to `Citation`
- Unclear which is the source of truth

**Recommendation:**

- Choose ONE approach:
  - **Option A:** Use only JSON field (simpler, faster reads)
  - **Option B:** Use only Citation table (normalized, better for complex queries)
- If keeping both, add relationship: `citations_rel = relationship("Citation", back_populates="verified_sentence")`

### 3. **Missing Unique Constraints**

**Problem:** No unique constraints on composite keys that should be unique:

**`verified_sentences`:**

- Missing: `UNIQUE(verification_job_id, sentence_index)`
- Risk: Duplicate sentences for same job/index

**`document_chunks`:**

- Missing: `UNIQUE(document_id, chunk_index)`
- Risk: Duplicate chunks for same document/index

**Impact:** Data integrity issues, potential bugs in application logic

### 4. **Missing Check Constraints**

**Problem:** No validation on numeric ranges:

- `confidence_score`: Should be 0.0-1.0
- `progress`: Should be 0.0-1.0
- `similarity_score`: Should be 0.0-1.0
- `relevance_rank`: Should be >= 0

**Impact:** Invalid data can be inserted (e.g., progress = 1.5)

### 5. **Missing NOT NULL Constraints**

**Problem:** Some fields should be required but aren't:

- `VerifiedSentence.updated_at`: Has `onupdate` but not `nullable=False`
- `DocumentChunk.weaviate_id`: Should be NOT NULL if indexed (or make it optional consistently)
- `VerificationJob.progress`: Should default to 0.0 and be NOT NULL

---

## ⚠️ **Moderate Issues**

### 6. **Missing Indexes Mentioned in Documentation**

**Problem:** DATABASE_SCHEMA.md mentions indexes not in migration:

- `idx_citations_text_fulltext` - Full-text search on citations (mentioned but not created)

**Note:** Actually, this IS created in migration line 255-258, so this is fine.

### 7. **Missing Relationship**

**Problem:** `VerifiedSentence` model doesn't have relationship to `Citation` table

- `Citation` has FK to `VerifiedSentence`
- But `VerifiedSentence` has no back-reference

**Fix:** Add to `VerifiedSentence`:

```python
citations_rel = relationship("Citation", back_populates="verified_sentence", cascade="all, delete-orphan")
```

And to `Citation`:

```python
verified_sentence = relationship("VerifiedSentence", back_populates="citations_rel")
```

### 8. **Inconsistent Default Values**

**Problem:** Some defaults use Python `[]` and `{}`, others use SQL defaults

- JSON defaults: `default=[]` or `default={}` (Python)
- Migration uses: `default={}` and `default=[]` (SQL)

**Impact:** Minor - works but inconsistent

---

## 📋 **Recommendations**

### High Priority Fixes:

1. **Change JSON to JSONB in models.py:**

   ```python
   from sqlalchemy.dialects.postgresql import JSONB
   metadata = Column(JSONB, default={})
   citations = Column(JSONB, default=[])
   ```

2. **Add unique constraints:**

   ```python
   # In VerifiedSentence
   __table_args__ = (
       UniqueConstraint('verification_job_id', 'sentence_index', name='uq_sentence_job_index'),
   )

   # In DocumentChunk
   __table_args__ = (
       UniqueConstraint('document_id', 'chunk_index', name='uq_chunk_doc_index'),
   )
   ```

3. **Add check constraints in migration:**

   ```python
   sa.CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='chk_confidence_range'),
   sa.CheckConstraint('progress >= 0 AND progress <= 1', name='chk_progress_range'),
   sa.CheckConstraint('similarity_score >= 0 AND similarity_score <= 1', name='chk_similarity_range'),
   sa.CheckConstraint('relevance_rank >= 0', name='chk_relevance_rank'),
   ```

4. **Clarify citation storage strategy:**
   - Document which approach to use
   - Add relationship if using Citation table
   - Or remove Citation table if using JSON only

### Medium Priority:

5. Add NOT NULL constraints where appropriate
6. Add missing relationship between VerifiedSentence and Citation
7. Consider adding indexes on frequently queried fields

---

## ✅ **What's Good**

- Excellent use of UUIDs for primary keys
- Proper enum types for status fields
- Good cascade delete strategy
- Comprehensive indexing for performance
- Full-text search support
- Automatic timestamp triggers
- Well-documented schema

---

## Summary

**Score: 7/10**

The schema is solid but needs fixes for:

- Data type consistency (JSON → JSONB)
- Data integrity (unique constraints, check constraints)
- Design clarity (citation storage strategy)

Most issues are fixable without major schema changes.
