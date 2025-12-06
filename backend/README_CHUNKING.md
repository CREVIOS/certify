# Document Chunking & Retrieval Guide

## Document Processing

Uses LangChain's `RecursiveCharacterTextSplitter` - the industry-standard best practice for text chunking.

### Basic Usage

```python
from app.services.document_processor import DocumentProcessor

# Initialize with optimal defaults
processor = DocumentProcessor(
    chunk_size=1000,        # Recommended: 1000-1500
    chunk_overlap=200,      # Recommended: 10-20% of chunk_size
    use_mistral_ocr=True
)

# Process PDF or DOCX
result = await processor.process_document_for_indexing("document.pdf")

# Get chunks with metadata
chunks = result["chunks"]
# Each chunk has: content, start_char, end_char, page_number, metadata
```

### How RecursiveCharacterTextSplitter Works

Splits text at natural boundaries in priority order:
1. Paragraphs (`\n\n`)
2. Lines (`\n`)
3. Sentences (`. `, `! `, `? `)
4. Clauses (`; `, `: `, `, `)
5. Words (` `)
6. Characters (fallback)

This ensures chunks break at logical points, preserving context.

### Configuration Guide

**Chunk Size:**
- Small (500-700): Precise retrieval, more chunks
- Medium (1000-1200): **Recommended** - balanced
- Large (1500-2000): More context, fewer chunks

**Overlap:**
- 10-20% of chunk_size is optimal
- Maintains context across chunk boundaries
- Prevents information loss at splits

## Advanced Retrieval (RSE)

The `app/helpers/rse.py` module provides Relevance Segment Extraction for better retrieval.

### What is RSE?

Instead of retrieving individual chunks, RSE finds optimal **segments** (contiguous groups of chunks) that maximize relevance while minimizing noise.

### Usage

```python
from app.helpers import (
    get_best_segments,
    get_meta_document,
    get_relevance_values,
    RSE_PARAMS_PRESETS
)

# Use preset configuration
config = RSE_PARAMS_PRESETS["balanced"]
# Options: "balanced", "precision", "find_all"

# 1. Get search results from vector store
search_results = [
    vector_store.search(query1, top_k=50),
    vector_store.search(query2, top_k=50),
]

# 2. Create meta-document
doc_splits, doc_starts, unique_ids = get_meta_document(
    all_ranked_results=search_results,
    top_k_for_document_selection=config["top_k_for_document_selection"]
)

# 3. Calculate relevance values
relevance_values = get_relevance_values(
    all_ranked_results=search_results,
    meta_document_length=doc_splits[-1],
    document_start_points=doc_starts,
    unique_document_ids=unique_ids,
    irrelevant_chunk_penalty=config["irrelevant_chunk_penalty"],
    decay_rate=config["decay_rate"],
    chunk_length_adjustment=config["chunk_length_adjustment"]
)

# 4. Get best segments
segments, scores = get_best_segments(
    all_relevance_values=relevance_values,
    document_splits=doc_splits,
    max_length=config["max_length"],
    overall_max_length=config["overall_max_length"],
    minimum_value=config["minimum_value"]
)

# 5. Use segments
for (start_idx, end_idx), score in zip(segments, scores):
    segment_chunks = chunks[start_idx:end_idx]
    # Use for LLM context
```

### RSE Presets

**Balanced** (Default)
- Best for general use
- max_length: 15 chunks
- overall_max_length: 30 chunks

**Precision**
- High-confidence results only
- Stricter minimum_value threshold
- Use when accuracy is critical

**Find All**
- Comprehensive retrieval
- max_length: 40 chunks
- overall_max_length: 200 chunks
- Use for compliance/verification tasks

## Complete Example

```python
from app.services.document_processor import DocumentProcessor
from app.helpers import get_best_segments, RSE_PARAMS_PRESETS

# 1. Process documents
processor = DocumentProcessor()

docs = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
all_chunks = []

for doc_path in docs:
    result = await processor.process_document_for_indexing(doc_path)
    all_chunks.extend(result["chunks"])

# 2. Index in vector store (your code here)
# vector_store.index(chunks)

# 3. Search with queries
queries = ["What are the risk factors?", "Financial performance?"]
search_results = [vector_store.search(q, top_k=50) for q in queries]

# 4. Apply RSE
config = RSE_PARAMS_PRESETS["balanced"]
# ... (follow RSE usage above)

# 5. Build context for LLM
context = "\n\n---\n\n".join([
    all_chunks[start:end]["content"]
    for start, end in segments
])

# 6. Query LLM with optimal context
response = llm.query(query, context=context)
```

## Best Practices

1. **Always use RecursiveCharacterTextSplitter** - it's the LangChain best practice
2. **Chunk size 1000-1500** for most documents
3. **Overlap 10-20%** to maintain context
4. **Use RSE for retrieval** instead of just top-k chunks
5. **Track page numbers** for citations (automatically done)

## Files Structure

```
app/
├── services/
│   └── document_processor.py    # Main chunking with LangChain
└── helpers/
    └── rse.py                    # Advanced retrieval (RSE)
```

That's it! Simple, effective, using industry best practices.
