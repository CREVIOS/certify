"""Verification service using Google Gemini with new google-genai SDK."""

from typing import List, Dict, Tuple, Optional
from uuid import UUID
from loguru import logger
from google import genai
from google.genai import types

from app.core.config import settings
from app.services.vector_store import vector_store
from app.services.embedding_service import embedding_service

try:
    import cohere
    from cohere import ClientV2
except ImportError:
    cohere = None
from app.db.models import ValidationResult


class VerificationService:
    """Service for verifying document claims using AI."""

    def __init__(self):
        """Initialize verification service with Gemini using new google-genai SDK."""
        # Initialize Google GenAI client
        api_key = settings.GOOGLE_API_KEY or settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError("Either GOOGLE_API_KEY or GEMINI_API_KEY must be set")

        self.client = genai.Client(api_key=api_key)
        self.model = settings.GEMINI_MODEL

        # System prompt for verification
        self.system_prompt = """You are an expert document verification assistant specializing in IPO documents.
Your task is to verify claims against supporting evidence from source documents.

For each claim:
1) Analyze the claim carefully.
2) Review all evidence provided (with page numbers).
3) Decide VALIDATED, UNCERTAIN, or INCORRECT.
4) Explain reasoning and cite exact quotes with page numbers.
5) If evidence conflicts, choose INCORRECT unless a clear majority supports the claim; mention conflicts explicitly.

Classification:
- VALIDATED: fully supported with high confidence.
- UNCERTAIN: partial/ambiguous support.
- INCORRECT: contradicts or lacks support."""

        # Human prompt template
        self.verification_template = """Claim to verify:
"{claim}"

Background Context:
{context}

Supporting Evidence from Documents:
{evidence}

Respond ONLY with JSON:
{{
  "validation_result": "VALIDATED|UNCERTAIN|INCORRECT",
  "confidence_score": 0.0-1.0,
  "reasoning": "detailed rationale; note conflicts if any",
  "citations": [
    {{
      "document": "filename",
      "page": page_number,
      "quote": "exact quote from source",
      "relevance": "how this evidence relates to the claim"
    }}
  ]
}}
Rules:
- VALIDATED or UNCERTAIN requires at least one citation; otherwise set INCORRECT.
- Use multiple citations if needed to show support and conflicts."""

    async def verify_sentence(
        self,
        sentence: str,
        project_id: UUID,
        context: str = "",
        top_k: Optional[int] = None
    ) -> Dict:
        """
        Verify a single sentence against supporting documents.

        Args:
            sentence: Sentence to verify
            project_id: Project UUID
            context: Background context for the project
            top_k: Number of similar chunks to retrieve

        Returns:
            Verification result with citations
        """
        try:
            # Retrieve semantic + keyword (hybrid) chunks from vector store
            candidate_limit = max(settings.RERANK_CANDIDATES, settings.SEMANTIC_TOP_K)
            semantic_chunks = await vector_store.search_similar(
                project_id=project_id,
                query=sentence,
                limit=candidate_limit,
                min_similarity=settings.MIN_SIMILARITY_THRESHOLD
            )

            hybrid_chunks = await vector_store.search_hybrid(
                project_id=project_id,
                query=sentence,
                limit=settings.KEYWORD_TOP_K,
                alpha=settings.HYBRID_ALPHA
            )

            # Merge and deduplicate by chunk_id/content hash
            merged = []
            seen = set()
            for chunk in semantic_chunks + hybrid_chunks:
                key = chunk.get("chunk_id") or hash(chunk["content"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(chunk)

            # Rerank top candidates using embedding similarity (cross-encoder surrogate)
            reranked = await self._rerank_chunks(sentence, merged)
            final_top_k = top_k or settings.RERANK_TOP_K
            merged = reranked[: final_top_k]

            if not merged:
                logger.warning(f"No similar evidence found for sentence: {sentence[:100]}...")
                return {
                    "validation_result": ValidationResult.UNCERTAIN,
                    "confidence_score": 0.0,
                    "reasoning": "No supporting evidence found in the provided documents.",
                    "citations": []
                }

            # Format evidence for the prompt
            evidence_text = self._format_evidence(merged)

            # Create prompt using new SDK
            human_prompt = self.verification_template.format(
                claim=sentence,
                context=context or "No additional context provided.",
                evidence=evidence_text
            )

            # Call Gemini using new SDK
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=human_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=settings.GEMINI_TEMPERATURE,
                    max_output_tokens=settings.GEMINI_MAX_TOKENS,
                    response_mime_type='application/json',
                ),
            )
            result = self._parse_verification_response(response.text, merged)

            logger.info(f"Verified sentence: {result['validation_result']}")
            return result

        except Exception as e:
            logger.error(f"Error verifying sentence: {e}")
            return {
                "validation_result": ValidationResult.UNCERTAIN,
                "confidence_score": 0.0,
                "reasoning": f"Error during verification: {str(e)}",
                "citations": []
            }

    def _format_evidence(self, chunks: List[Dict]) -> str:
        """
        Format evidence chunks for the prompt.

        Args:
            chunks: List of similar chunks

        Returns:
            Formatted evidence string
        """
        evidence_parts = []

        for idx, chunk in enumerate(chunks, 1):
            evidence_parts.append(
                f"# Evidence {idx}\n"
                f"- similarity: {chunk['similarity']:.2f}\n"
                f"- file: {chunk.get('filename','unknown')}\n"
                f"- page: {chunk.get('page_number', 'N/A')}\n"
                f"- chunk_id: {chunk.get('chunk_id','')}\n"
                f"## content:\n{chunk['content']}\n"
            )

        return "\n".join(evidence_parts)

    def _parse_verification_response(self, response: str, chunks: List[Dict]) -> Dict:
        """
        Parse LLM response into structured format.

        Args:
            response: LLM response text
            chunks: Original evidence chunks

        Returns:
            Structured verification result
        """
        try:
            import json
            import re

            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                # Fallback parsing
                result = {
                    "validation_result": "UNCERTAIN",
                    "confidence_score": 0.5,
                    "reasoning": response,
                    "citations": []
                }

            # Map validation result to enum
            validation_map = {
                "VALIDATED": ValidationResult.VALIDATED,
                "UNCERTAIN": ValidationResult.UNCERTAIN,
                "INCORRECT": ValidationResult.INCORRECT
            }

            validation_result = validation_map.get(
                result.get("validation_result", "UNCERTAIN").upper(),
                ValidationResult.UNCERTAIN
            )

            # Ensure confidence score is in range
            confidence = float(result.get("confidence_score", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            # Process citations
            citations = []
            for citation in result.get("citations", []):
                # Try to match citation to original chunks
                matching_chunk = self._find_matching_chunk(citation, chunks)

                if matching_chunk:
                    citations.append({
                        "document_id": matching_chunk["document_id"],
                        "cited_text": citation.get("quote", matching_chunk["content"][:200]),
                        "page_number": matching_chunk.get("page_number"),
                        "start_char": matching_chunk.get("start_char"),
                        "end_char": matching_chunk.get("end_char"),
                        "similarity_score": matching_chunk["similarity"],
                        "context_before": "",
                        "context_after": "",
                        "filename": matching_chunk.get("filename", ""),
                        "relevance": citation.get("relevance", "")
                    })

            return {
                "validation_result": validation_result,
                "confidence_score": confidence,
                "reasoning": result.get("reasoning", ""),
                "citations": citations
            }

        except Exception as e:
            logger.error(f"Error parsing verification response: {e}")
            return {
                "validation_result": ValidationResult.UNCERTAIN,
                "confidence_score": 0.5,
                "reasoning": response,
                "citations": []
            }

    async def _rerank_chunks(self, query: str, chunks: List[Dict]) -> List[Dict]:
        """
        Rerank candidates. Prefer Cohere Rerank if configured; fallback to embedding cosine.
        """
        if not chunks:
            return []

        try:
            # Cohere rerank path (v2 API)
            if settings.COHERE_API_KEY and cohere:
                client = ClientV2(api_key=settings.COHERE_API_KEY)
                docs = [c["content"] for c in chunks]
                rerank_res = client.rerank(
                    model=settings.COHERE_RERANK_MODEL or "rerank-v3.5",
                    query=query,
                    documents=docs,
                    top_n=min(len(chunks), settings.RERANK_CANDIDATES),
                )
                ranked = []
                for r in rerank_res.results:
                    chunk = chunks[r.index]
                    chunk["similarity"] = max(chunk.get("similarity", 0), r.relevance_score)
                    ranked.append(chunk)
            else:
                # Fallback: embedding cosine
                query_vec = await embedding_service.embed_text(query)
                texts = [c["content"] for c in chunks]
                chunk_vecs = await embedding_service.embed_batch(texts)

                def cosine(a, b):
                    import math
                    dot = sum(x*y for x, y in zip(a, b))
                    na = math.sqrt(sum(x*x for x in a))
                    nb = math.sqrt(sum(x*x for x in b))
                    return dot / (na * nb + 1e-12)

                scored = []
                for chunk, vec in zip(chunks, chunk_vecs):
                    sim = cosine(query_vec, vec)
                    chunk["similarity"] = max(chunk.get("similarity", 0), sim)
                    scored.append((sim, chunk, vec))

                scored.sort(key=lambda t: t[0], reverse=True)
                ranked = [c for _, c, _ in scored]

            # Deduplicate near-duplicates (>0.97) by content
            deduped = []
            seen = set()
            for c in ranked:
                key = hash(c["content"])
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(c)

            return deduped
        except Exception as e:
            logger.error(f"Rerank failed: {e}")
            return chunks

    def _find_matching_chunk(self, citation: Dict, chunks: List[Dict]) -> Dict:
        """
        Find the chunk that best matches a citation.

        Args:
            citation: Citation from LLM
            chunks: List of evidence chunks

        Returns:
            Matching chunk or None
        """
        # Try to match by document name or page number
        doc_name = citation.get("document", "").lower()
        page_num = citation.get("page")

        for chunk in chunks:
            if doc_name and doc_name in chunk.get("filename", "").lower():
                if page_num is None or chunk.get("page_number") == page_num:
                    return chunk

        # Return first chunk as fallback
        return chunks[0] if chunks else None

    async def verify_batch(
        self,
        sentences: List[str],
        project_id: UUID,
        context: str = ""
    ) -> List[Dict]:
        """
        Verify multiple sentences in batch.

        Args:
            sentences: List of sentences to verify
            project_id: Project UUID
            context: Background context

        Returns:
            List of verification results
        """
        results = []

        for sentence in sentences:
            result = await self.verify_sentence(
                sentence=sentence,
                project_id=project_id,
                context=context
            )
            results.append(result)

        return results


# Singleton instance
verification_service = VerificationService()
