"""Enhanced verification service using Mistral AI for superior citation tracking.

This service provides production-grade claim verification with:
- Page-by-page citation accuracy
- Precise text extraction and matching
- Superior reasoning with Mistral Large
- Structured JSON responses
"""

from typing import List, Dict
from uuid import UUID
from loguru import logger

from app.core.config import settings
from app.services.vector_store import vector_store
from app.services.mistral_service import mistral_service
from app.db.models import ValidationResult


class MistralVerificationService:
    """Enhanced verification service using Mistral AI."""

    async def verify_sentence(
        self,
        sentence: str,
        sentence_page: Optional[int],
        project_id: UUID,
        context: str = "",
        top_k: int = 5
    ) -> Dict:
        """
        Verify a single sentence against supporting documents using Mistral.

        Args:
            sentence: Sentence to verify
            sentence_page: Page number where sentence appears
            project_id: Project UUID
            context: Background context for the project
            top_k: Number of similar chunks to retrieve

        Returns:
            Verification result with precise citations including page numbers
        """
        try:
            # Retrieve similar chunks from vector store
            similar_chunks = await vector_store.search_similar(
                project_id=project_id,
                query=sentence,
                limit=top_k,
                min_similarity=settings.MIN_SIMILARITY_THRESHOLD
            )

            if not similar_chunks:
                logger.warning(f"No similar evidence found for sentence on page {sentence_page}")
                return {
                    "validation_result": ValidationResult.UNCERTAIN,
                    "confidence_score": 0.0,
                    "reasoning": "No supporting evidence found in the provided documents.",
                    "citations": []
                }

            # Use Mistral for verification with precise citation tracking
            verification_result = await mistral_service.verify_claim_with_citations(
                claim=sentence,
                claim_page=sentence_page,
                supporting_evidence=similar_chunks,
                background_context=context
            )

            # Convert Mistral response to our format
            validation_map = {
                "VALIDATED": ValidationResult.VALIDATED,
                "UNCERTAIN": ValidationResult.UNCERTAIN,
                "INCORRECT": ValidationResult.INCORRECT
            }

            validation_result = validation_map.get(
                verification_result.get("validation_result", "UNCERTAIN").upper(),
                ValidationResult.UNCERTAIN
            )

            # Process citations from Mistral
            citations = self._process_mistral_citations(
                verification_result.get("citations", []),
                similar_chunks
            )

            result = {
                "validation_result": validation_result,
                "confidence_score": verification_result.get("confidence_score", 0.5),
                "reasoning": verification_result.get("reasoning", ""),
                "citations": citations,
                "key_findings": verification_result.get("key_findings", [])
            }

            logger.info(
                f"Verified sentence (page {sentence_page}): {result['validation_result']} "
                f"with {len(citations)} citations"
            )
            return result

        except Exception as e:
            logger.error(f"Error verifying sentence: {e}")
            return {
                "validation_result": ValidationResult.UNCERTAIN,
                "confidence_score": 0.0,
                "reasoning": f"Error during verification: {str(e)}",
                "citations": []
            }

    def _process_mistral_citations(
        self,
        mistral_citations: List[Dict],
        original_chunks: List[Dict]
    ) -> List[Dict]:
        """
        Process citations from Mistral and match with original chunks.

        Args:
            mistral_citations: Citations from Mistral AI
            original_chunks: Original vector search results

        Returns:
            Processed citations with complete information
        """
        processed_citations = []

        for citation in mistral_citations:
            # Extract page number from citation
            page_num = citation.get("source_page") or citation.get("page_number")

            # Try to match with original chunks for document_id
            matching_chunk = self._find_chunk_by_page(page_num, original_chunks)

            processed_citation = {
                "document_id": matching_chunk.get("document_id", "") if matching_chunk else "",
                "cited_text": citation.get("cited_text", ""),
                "page_number": page_num,
                "start_char": citation.get("start_char"),
                "end_char": citation.get("end_char"),
                "similarity_score": citation.get("similarity_score", 0.85),
                "context_before": citation.get("context_before", ""),
                "context_after": citation.get("context_after", ""),
                "filename": matching_chunk.get("filename", "") if matching_chunk else "",
                "relevance": citation.get("relevance", "")
            }

            processed_citations.append(processed_citation)

        return processed_citations

    def _find_chunk_by_page(
        self,
        page_number: any,
        chunks: List[Dict]
    ) -> Optional[Dict]:
        """Find chunk matching a specific page number."""
        if page_number is None:
            return chunks[0] if chunks else None

        # Try to convert page_number to int
        try:
            page_num = int(page_number)
        except (ValueError, TypeError):
            return chunks[0] if chunks else None

        # Find chunk with matching page
        for chunk in chunks:
            if chunk.get("page_number") == page_num:
                return chunk

        # Fallback to first chunk
        return chunks[0] if chunks else None

    async def verify_batch(
        self,
        sentences: List[Dict],
        project_id: UUID,
        context: str = ""
    ) -> List[Dict]:
        """
        Verify multiple sentences in batch.

        Args:
            sentences: List of sentence dictionaries with 'content' and 'page_number'
            project_id: Project UUID
            context: Background context

        Returns:
            List of verification results
        """
        results = []

        for sentence_data in sentences:
            result = await self.verify_sentence(
                sentence=sentence_data.get("content", ""),
                sentence_page=sentence_data.get("page_number"),
                project_id=project_id,
                context=context
            )
            results.append(result)

        return results


# Singleton instance
mistral_verification_service = MistralVerificationService()
