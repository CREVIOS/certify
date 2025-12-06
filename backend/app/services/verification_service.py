"""Verification service using Langchain and Google Gemini."""

from typing import List, Dict, Tuple
from uuid import UUID
from loguru import logger

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, SystemMessage

from app.core.config import settings
from app.services.vector_store import vector_store
from app.db.models import ValidationResult


class VerificationService:
    """Service for verifying document claims using AI."""

    def __init__(self):
        """Initialize verification service with Gemini LLM."""
        self.llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=settings.GEMINI_TEMPERATURE,
            max_output_tokens=settings.GEMINI_MAX_TOKENS,
        )

        # Verification prompt template
        self.verification_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert document verification assistant specializing in IPO documents.
Your task is to verify claims made in IPO documents against supporting evidence from source documents.

For each claim, you must:
1. Analyze the claim carefully
2. Review all provided evidence from supporting documents
3. Determine if the claim is VALIDATED, UNCERTAIN, or INCORRECT
4. Provide detailed reasoning for your assessment
5. Cite specific evidence that supports or contradicts the claim

Classification criteria:
- VALIDATED (Green): The claim is fully supported by evidence from supporting documents with high confidence
- UNCERTAIN (Yellow): The claim is partially supported, evidence is ambiguous, or confidence is moderate
- INCORRECT (Red): The claim contradicts evidence or is not supported by any evidence

Be thorough, objective, and cite specific page numbers and quotes."""),
            ("human", """Claim to verify:
"{claim}"

Background Context:
{context}

Supporting Evidence from Documents:
{evidence}

Based on the evidence, classify this claim as VALIDATED, UNCERTAIN, or INCORRECT.
Provide your response in the following JSON format:
{{
    "validation_result": "VALIDATED|UNCERTAIN|INCORRECT",
    "confidence_score": 0.0-1.0,
    "reasoning": "Detailed explanation of your assessment",
    "citations": [
        {{
            "document": "filename",
            "page": page_number,
            "quote": "exact quote from source",
            "relevance": "how this evidence relates to the claim"
        }}
    ]
}}""")
        ])

    async def verify_sentence(
        self,
        sentence: str,
        project_id: UUID,
        context: str = "",
        top_k: int = 5
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
            # Retrieve similar chunks from vector store
            similar_chunks = vector_store.search_similar(
                project_id=project_id,
                query=sentence,
                limit=top_k,
                min_similarity=settings.MIN_SIMILARITY_THRESHOLD
            )

            if not similar_chunks:
                logger.warning(f"No similar evidence found for sentence: {sentence[:100]}...")
                return {
                    "validation_result": ValidationResult.UNCERTAIN,
                    "confidence_score": 0.0,
                    "reasoning": "No supporting evidence found in the provided documents.",
                    "citations": []
                }

            # Format evidence for the prompt
            evidence_text = self._format_evidence(similar_chunks)

            # Create prompt
            messages = self.verification_prompt.format_messages(
                claim=sentence,
                context=context or "No additional context provided.",
                evidence=evidence_text
            )

            # Call Gemini
            response = await self.llm.ainvoke(messages)
            result = self._parse_verification_response(response.content, similar_chunks)

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
                f"Evidence {idx} (Similarity: {chunk['similarity']:.2f}):\n"
                f"Source: {chunk['filename']}\n"
                f"Page: {chunk.get('page_number', 'N/A')}\n"
                f"Content: {chunk['content']}\n"
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
