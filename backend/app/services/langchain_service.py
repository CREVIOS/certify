"""
LangChain Service for IPO Document Verification
Uses GPT-4.1 and Gemini 2.5 Pro (2025 best models) for state-of-the-art verification
"""

from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain.chains import LLMChain
from pydantic import BaseModel, Field
import json

from app.core.config import settings


class CitationModel(BaseModel):
    """Citation extracted from supporting documents"""
    document_id: str = Field(description="ID of the source document")
    document_name: str = Field(description="Name of the source document")
    page_number: int = Field(description="Page number in the source document")
    cited_text: str = Field(description="Exact text excerpt from the source")
    relevance_score: float = Field(description="Relevance score 0.0-1.0")
    context_before: Optional[str] = Field(None, description="Text before the citation")
    context_after: Optional[str] = Field(None, description="Text after the citation")


class VerificationResult(BaseModel):
    """Result of claim verification"""
    validation_result: str = Field(description="validated, uncertain, or incorrect")
    confidence_score: float = Field(description="Confidence score 0.0-1.0")
    reasoning: str = Field(description="Detailed explanation of the verification")
    citations: List[CitationModel] = Field(default_factory=list, description="Supporting citations")


class LangChainVerificationService:
    """
    Service for document verification using LangChain with GPT-4.1 and Gemini 2.5 Pro (2025 best models)
    """

    def __init__(self):
        # Initialize GPT-4.1 (primary model for verification - 2025 best model)
        self.gpt4 = ChatOpenAI(
            model=settings.OPENAI_CHAT_MODEL,  # GPT-4.1 - 1M token context
            temperature=settings.OPENAI_TEMPERATURE,
            max_tokens=settings.OPENAI_MAX_TOKENS,
            openai_api_key=settings.OPENAI_API_KEY
        )

        # Initialize Gemini 2.5 Pro (secondary model for cross-validation - 2025 best model)
        self.gemini = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,  # Gemini 2.5 Pro - Google's most intelligent model
            temperature=settings.GEMINI_TEMPERATURE,
            google_api_key=settings.GEMINI_API_KEY
        )

        # Output parser for structured responses
        self.output_parser = PydanticOutputParser(pydantic_object=VerificationResult)

    def _create_verification_prompt(self) -> ChatPromptTemplate:
        """
        Create verification prompt template
        """
        system_template = """You are an expert IPO document analyst with deep expertise in financial regulations, GAAP/IFRS standards, and legal compliance.

Your task is to verify claims made in IPO prospectuses against supporting documentation with the highest accuracy.

For each claim:
1. Analyze the claim carefully
2. Review all supporting evidence from reference documents
3. Determine if the claim is:
   - VALIDATED: Fully supported by evidence with high confidence
   - UNCERTAIN: Partially supported or ambiguous, needs human review
   - INCORRECT: Contradicts evidence or unsupported

4. Provide precise citations with exact page numbers and text excerpts
5. Explain your reasoning in detail

Focus on:
- Numerical accuracy (revenue, metrics, counts)
- Temporal accuracy (dates, periods)
- Factual accuracy (names, locations, events)
- Legal compliance (regulations, requirements)

{format_instructions}

Be extremely precise with page numbers and citations."""

        human_template = """**CLAIM TO VERIFY:**
"{claim}"

**CLAIM PAGE:** {claim_page}

**SUPPORTING EVIDENCE:**
{evidence}

**BACKGROUND CONTEXT:**
{background_context}

Verify this claim and provide structured output with citations."""

        system_message = SystemMessagePromptTemplate.from_template(system_template)
        human_message = HumanMessagePromptTemplate.from_template(human_template)

        return ChatPromptTemplate.from_messages([system_message, human_message])

    async def verify_claim(
        self,
        claim: str,
        claim_page: Optional[int],
        supporting_evidence: List[Dict[str, Any]],
        background_context: str = "",
        use_cross_validation: bool = True
    ) -> VerificationResult:
        """
        Verify a claim using GPT-4 with optional Gemini cross-validation

        Args:
            claim: The claim to verify
            claim_page: Page number where claim appears
            supporting_evidence: List of evidence chunks with metadata
            background_context: Additional context about the IPO
            use_cross_validation: Whether to cross-validate with Gemini

        Returns:
            VerificationResult with validation status and citations
        """
        # Format evidence for prompt
        evidence_text = self._format_evidence(supporting_evidence)

        # Create prompt
        prompt = self._create_verification_prompt()

        # Create chain with GPT-4
        chain = LLMChain(llm=self.gpt4, prompt=prompt)

        # Get format instructions
        format_instructions = self.output_parser.get_format_instructions()

        # Run verification with GPT-4
        result = await chain.arun(
            claim=claim,
            claim_page=claim_page or "Unknown",
            evidence=evidence_text,
            background_context=background_context or "No additional context provided",
            format_instructions=format_instructions
        )

        # Parse result
        try:
            verification = self.output_parser.parse(result)
        except Exception as e:
            # Fallback parsing if structured output fails
            verification = self._fallback_parse(result, supporting_evidence)

        # Cross-validate with Gemini if requested
        if use_cross_validation and verification.confidence_score < 0.9:
            gemini_result = await self._cross_validate_with_gemini(
                claim, claim_page, evidence_text, background_context, verification
            )
            # Merge results if discrepancy
            verification = self._merge_verifications(verification, gemini_result)

        return verification

    async def _cross_validate_with_gemini(
        self,
        claim: str,
        claim_page: Optional[int],
        evidence_text: str,
        background_context: str,
        gpt4_result: VerificationResult
    ) -> VerificationResult:
        """
        Cross-validate GPT-4 result with Gemini 2.5 Pro
        """
        prompt = self._create_verification_prompt()
        chain = LLMChain(llm=self.gemini, prompt=prompt)
        format_instructions = self.output_parser.get_format_instructions()

        result = await chain.arun(
            claim=claim,
            claim_page=claim_page or "Unknown",
            evidence=evidence_text,
            background_context=background_context or "No additional context",
            format_instructions=format_instructions
        )

        try:
            return self.output_parser.parse(result)
        except:
            return gpt4_result  # Fallback to GPT-4 result

    def _merge_verifications(
        self,
        gpt4_result: VerificationResult,
        gemini_result: VerificationResult
    ) -> VerificationResult:
        """
        Merge GPT-4 and Gemini results when they disagree
        """
        # If both agree, return GPT-4 result with higher confidence
        if gpt4_result.validation_result == gemini_result.validation_result:
            gpt4_result.confidence_score = min(
                1.0,
                (gpt4_result.confidence_score + gemini_result.confidence_score) / 2 + 0.1
            )
            return gpt4_result

        # If they disagree, mark as uncertain and combine reasoning
        return VerificationResult(
            validation_result="uncertain",
            confidence_score=0.5,
            reasoning=f"**GPT-4 Analysis:** {gpt4_result.reasoning}\n\n**Gemini Analysis:** {gemini_result.reasoning}\n\n**Note:** Models disagree - manual review recommended.",
            citations=gpt4_result.citations + gemini_result.citations
        )

    def _format_evidence(self, evidence: List[Dict[str, Any]]) -> str:
        """
        Format evidence chunks for prompt
        """
        formatted = []
        for i, chunk in enumerate(evidence, 1):
            formatted.append(
                f"**Evidence {i}:**\n"
                f"Document: {chunk.get('document_name', 'Unknown')}\n"
                f"Page: {chunk.get('page_number', 'Unknown')}\n"
                f"Content: {chunk.get('content', '')}\n"
            )
        return "\n\n".join(formatted)

    def _fallback_parse(
        self,
        raw_result: str,
        supporting_evidence: List[Dict[str, Any]]
    ) -> VerificationResult:
        """
        Fallback parsing if structured output fails
        """
        # Try to extract validation result
        raw_lower = raw_result.lower()
        if "validated" in raw_lower and "incorrect" not in raw_lower:
            validation_result = "validated"
            confidence = 0.85
        elif "incorrect" in raw_lower or "contradicts" in raw_lower:
            validation_result = "incorrect"
            confidence = 0.8
        else:
            validation_result = "uncertain"
            confidence = 0.6

        # Extract citations from evidence
        citations = []
        for evidence in supporting_evidence[:3]:  # Top 3 most relevant
            citations.append(CitationModel(
                document_id=evidence.get('document_id', ''),
                document_name=evidence.get('document_name', 'Unknown'),
                page_number=evidence.get('page_number', 0),
                cited_text=evidence.get('content', '')[:200],
                relevance_score=evidence.get('similarity_score', 0.5),
                context_before=None,
                context_after=None
            ))

        return VerificationResult(
            validation_result=validation_result,
            confidence_score=confidence,
            reasoning=raw_result,
            citations=citations
        )

    async def extract_structured_content(
        self,
        document_text: str,
        page_number: int
    ) -> Dict[str, Any]:
        """
        Extract structured content from a document page using GPT-4
        """
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                """You are a document analysis expert. Extract structured information from IPO documents.

For each page, identify:
1. All factual claims (financial figures, dates, metrics, assertions)
2. Sentences that require verification
3. Page structure and metadata

Return as JSON."""
            ),
            HumanMessagePromptTemplate.from_template(
                """**PAGE {page_number}:**

{text}

Extract all verifiable claims as a JSON array with format:
{{
  "claims": [
    {{
      "sentence": "exact sentence text",
      "type": "financial|temporal|factual|legal",
      "requires_verification": true/false
    }}
  ]
}}"""
            )
        ])

        chain = LLMChain(llm=self.gpt4, prompt=prompt)
        result = await chain.arun(page_number=page_number, text=document_text)

        try:
            return json.loads(result)
        except:
            return {"claims": [], "raw": result}

    async def batch_verify_claims(
        self,
        claims: List[Dict[str, Any]],
        evidence_store: Dict[str, List[Dict[str, Any]]],
        background_context: str = ""
    ) -> List[VerificationResult]:
        """
        Batch verify multiple claims efficiently
        """
        results = []
        for claim_data in claims:
            claim_text = claim_data.get("sentence", "")
            claim_page = claim_data.get("page", None)

            # Get relevant evidence for this claim
            evidence = evidence_store.get(claim_text, [])

            # Verify claim
            result = await self.verify_claim(
                claim=claim_text,
                claim_page=claim_page,
                supporting_evidence=evidence,
                background_context=background_context
            )
            results.append(result)

        return results
