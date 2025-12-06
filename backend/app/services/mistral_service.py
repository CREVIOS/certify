"""Mistral AI service for document extraction using OCR API and structured output.

Mistral AI provides superior document understanding with OCR capabilities,
making it ideal for extracting structured information from PDFs and documents.
"""

from typing import List, Dict, Optional, Any
from pathlib import Path
from loguru import logger
from mistralai import Mistral
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential
import json
import base64

from app.core.config import settings


# Pydantic models for structured extraction
class DocumentSection(BaseModel):
    """Structured section extracted from document."""
    heading: str = Field(description="Section title or heading")
    content: str = Field(description="Section text content")
    start_char: int = Field(default=0, description="Character start position")
    end_char: int = Field(default=0, description="Character end position")
    section_type: str = Field(default="paragraph", description="Type: paragraph|heading|table|list")


class DocumentCitation(BaseModel):
    """Citation extracted from document."""
    text: str = Field(description="Exact citation text")
    reference: str = Field(description="What it references")
    page_number: int = Field(description="Page number where citation appears")
    position: str = Field(default="", description="Position in text")


class DocumentTable(BaseModel):
    """Table extracted from document."""
    title: str = Field(description="Table title")
    data: str = Field(description="Structured table data")
    page_number: int = Field(description="Page number")


class DocumentKeyFact(BaseModel):
    """Key fact extracted from document."""
    fact: str = Field(description="Important fact or figure")
    page_number: int = Field(description="Page number")
    context: str = Field(description="Surrounding context")


class DocumentExtraction(BaseModel):
    """Complete structured extraction from a document page."""
    page_number: int = Field(description="Page number")
    sections: List[DocumentSection] = Field(default_factory=list, description="Document sections")
    citations: List[DocumentCitation] = Field(default_factory=list, description="Citations found")
    tables: List[DocumentTable] = Field(default_factory=list, description="Tables extracted")
    key_facts: List[DocumentKeyFact] = Field(default_factory=list, description="Key facts")


class CitationDetail(BaseModel):
    """Detailed citation with context."""
    cited_text: str = Field(description="Exact text being cited")
    page_number: int = Field(description="Page number")
    reference_type: str = Field(description="financial_data|legal_reference|external_source|internal_cross_reference")
    context_before: str = Field(default="", description="Text before citation")
    context_after: str = Field(default="", description="Text after citation")
    confidence: float = Field(default=0.85, description="Confidence score 0-1")
    notes: str = Field(default="", description="Relevant notes")


class VerificationCitation(BaseModel):
    """Citation for verification result."""
    source_page: str = Field(description="Page number from evidence")
    cited_text: str = Field(description="EXACT quote from source")
    relevance: str = Field(description="How this supports or contradicts the claim")
    similarity_score: float = Field(default=0.85, description="Similarity score 0-1")
    context_before: str = Field(default="", description="Text before quote")
    context_after: str = Field(default="", description="Text after quote")


class VerificationResult(BaseModel):
    """Verification result with citations."""
    validation_result: str = Field(description="VALIDATED|UNCERTAIN|INCORRECT")
    confidence_score: float = Field(description="Confidence score 0-1")
    reasoning: str = Field(description="Detailed explanation")
    citations: List[VerificationCitation] = Field(default_factory=list, description="Supporting citations")
    key_findings: List[str] = Field(default_factory=list, description="Key findings")


class MistralService:
    """Service for PDF extraction using Mistral OCR API and structured outputs."""

    def __init__(self):
        """Initialize Mistral client."""
        self.client = Mistral(api_key=settings.MISTRAL_API_KEY)
        self.model = settings.MISTRAL_MODEL
        self.temperature = settings.MISTRAL_TEMPERATURE
        self.max_tokens = settings.MISTRAL_MAX_TOKENS

    # PROMPT TEMPLATES FOR DOCUMENT EXTRACTION

    EXTRACTION_SYSTEM_PROMPT = """You are an expert document analyst specializing in extracting structured information from financial and legal documents, particularly IPO prospectuses.

Your task is to extract text from PDF pages with PERFECT accuracy while maintaining:
1. **Page-level tracking**: Always note which page each piece of information comes from
2. **Character positions**: Track start and end positions when possible
3. **Structural elements**: Preserve headings, lists, tables, and formatting
4. **Citation context**: Keep surrounding text for context

Return structured data with:
- Extracted text organized by page
- Metadata about each section
- Cross-references and footnotes
- Table data in structured format

Be meticulous about accuracy - this will be used for legal verification."""

    CITATION_EXTRACTION_PROMPT = """You are a citation extraction specialist for legal and financial documents.

Given a document page, extract ALL citations, references, and supporting evidence with EXACT page numbers and positions.

For each citation, provide:
1. **Exact text**: The precise quote being cited
2. **Page number**: Where it appears (critical!)
3. **Context**: Surrounding sentences for clarity
4. **Type**: Reference type (financial data, legal clause, external source, etc.)
5. **Confidence**: How certain you are about this citation

Return structured data format."""

    VERIFICATION_SYSTEM_PROMPT = """You are an expert IPO document verifier with deep knowledge of financial regulations and disclosure requirements.

Your role is to verify claims made in IPO documents against supporting evidence with PRECISION.

For each claim verification:
1. Analyze the claim carefully
2. Review ALL provided supporting evidence
3. Determine validation status with HIGH accuracy
4. Provide SPECIFIC citations with EXACT page numbers
5. Explain your reasoning clearly

Classification rules:
- **VALIDATED**: Claim is fully supported by evidence with exact matches
- **UNCERTAIN**: Partial support or ambiguous evidence
- **INCORRECT**: Contradicts evidence or unsupported

ALWAYS cite exact page numbers and quote the supporting text."""

    async def extract_text_from_pdf_ocr(
        self,
        pdf_path: str
    ) -> Dict[str, Any]:
        """
        Extract text from PDF using Mistral OCR API.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text with page information
        """
        try:
            # Read PDF file and encode to base64
            with open(pdf_path, 'rb') as f:
                pdf_data = f.read()

            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')

            # Use Mistral OCR API
            logger.info(f"Processing PDF with Mistral OCR: {pdf_path}")

            # Call OCR endpoint using client.ocr.process
            ocr_response = self.client.ocr.process(
                file={
                    "data": pdf_base64,
                    "mime_type": "application/pdf"
                }
            )

            logger.info(f"Mistral OCR completed for {pdf_path}")

            # Process OCR response
            pages = []
            full_text = ""

            # Extract text from OCR response
            if hasattr(ocr_response, 'pages'):
                for page_num, page in enumerate(ocr_response.pages, 1):
                    page_text = page.text if hasattr(page, 'text') else ""
                    pages.append({
                        "page_number": page_num,
                        "text": page_text,
                        "char_start": len(full_text),
                        "char_end": len(full_text) + len(page_text)
                    })
                    full_text += page_text + "\n"
            elif hasattr(ocr_response, 'text'):
                # Single text output
                full_text = ocr_response.text
                pages.append({
                    "page_number": 1,
                    "text": full_text,
                    "char_start": 0,
                    "char_end": len(full_text)
                })

            return {
                "full_text": full_text,
                "pages": pages,
                "page_count": len(pages),
                "metadata": {
                    "extraction_method": "mistral_ocr",
                    "file_path": pdf_path
                }
            }

        except Exception as e:
            logger.error(f"Error in Mistral OCR extraction: {e}")
            # Fallback to basic extraction if OCR fails
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def extract_structured_content(
        self,
        page_text: str,
        page_number: int,
        document_metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Extract structured content from a PDF page using Mistral with structured output.

        Args:
            page_text: Text content from the page
            page_number: Page number
            document_metadata: Optional metadata about the document

        Returns:
            Structured extraction with citations and metadata
        """
        try:
            user_prompt = f"""Extract structured information from this IPO document page.

**Page Number**: {page_number}
**Document Context**: {document_metadata.get('title', 'IPO Document') if document_metadata else 'IPO Document'}

**Page Content**:
```
{page_text}
```

Extract all sections, citations, tables, and key facts with precise positions."""

            response = self.client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "document_extraction",
                        "schema": DocumentExtraction.model_json_schema(),
                        "strict": True
                    }
                }
            )

            # Parse structured output
            result = json.loads(response.choices[0].message.content)
            logger.info(f"Extracted structured content from page {page_number}")
            return result

        except Exception as e:
            logger.error(f"Error in structured extraction: {e}")
            return {
                "page_number": page_number,
                "sections": [{"heading": "", "content": page_text, "section_type": "paragraph"}],
                "citations": [],
                "tables": [],
                "key_facts": []
            }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def extract_citations_from_page(
        self,
        page_text: str,
        page_number: int
    ) -> List[Dict[str, Any]]:
        """
        Extract all citations from a page with precise tracking.

        Args:
            page_text: Text from the page
            page_number: Page number

        Returns:
            List of citations with exact positions
        """
        try:
            user_prompt = f"""Extract ALL citations and references from this page with EXACT details.

**Page Number**: {page_number}

**Content**:
```
{page_text}
```

If no citations found, return empty array."""

            response = self.client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.CITATION_EXTRACTION_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "citation_list",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "citations": {
                                    "type": "array",
                                    "items": CitationDetail.model_json_schema()
                                }
                            },
                            "required": ["citations"],
                            "additionalProperties": False
                        },
                        "strict": True
                    }
                }
            )

            result = json.loads(response.choices[0].message.content)
            citations = result.get("citations", [])

            logger.info(f"Extracted {len(citations)} citations from page {page_number}")
            return citations

        except Exception as e:
            logger.error(f"Error extracting citations: {e}")
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def verify_claim_with_citations(
        self,
        claim: str,
        claim_page: Optional[int],
        supporting_evidence: List[Dict[str, Any]],
        background_context: str = ""
    ) -> Dict[str, Any]:
        """
        Verify a claim against supporting evidence with precise citation tracking.

        Args:
            claim: The claim to verify
            claim_page: Page number where claim appears
            supporting_evidence: List of evidence chunks with page numbers
            background_context: Additional context about the document

        Returns:
            Verification result with precise citations
        """
        try:
            # Format evidence with page numbers
            evidence_text = self._format_evidence_with_pages(supporting_evidence)

            user_prompt = f"""Verify this claim from an IPO document with PRECISION.

**Claim** (Page {claim_page if claim_page else 'Unknown'}):
"{claim}"

**Background Context**:
{background_context if background_context else 'IPO document verification'}

**Supporting Evidence from Source Documents**:
{evidence_text}

**Your Task**:
1. Analyze the claim carefully
2. Review ALL evidence provided
3. Determine: VALIDATED, UNCERTAIN, or INCORRECT
4. Provide EXACT citations with page numbers
5. Explain your reasoning

**Critical**: Always include exact page numbers and quotes!"""

            response = self.client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.VERIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "verification_result",
                        "schema": VerificationResult.model_json_schema(),
                        "strict": True
                    }
                }
            )

            result = json.loads(response.choices[0].message.content)

            # Ensure citations have all required fields
            citations = result.get("citations", [])
            for citation in citations:
                citation["page_number"] = citation.get("source_page", "Unknown")
                if "similarity_score" not in citation:
                    citation["similarity_score"] = 0.85  # Default high confidence

            logger.info(
                f"Verified claim with result: {result.get('validation_result')} "
                f"({len(citations)} citations)"
            )

            return result

        except Exception as e:
            logger.error(f"Error in claim verification: {e}")
            return {
                "validation_result": "UNCERTAIN",
                "confidence_score": 0.0,
                "reasoning": f"Error during verification: {str(e)}",
                "citations": [],
                "key_findings": []
            }

    def _format_evidence_with_pages(self, evidence: List[Dict[str, Any]]) -> str:
        """Format evidence chunks with page numbers for the prompt."""
        formatted = []

        for idx, chunk in enumerate(evidence, 1):
            page_num = chunk.get("page_number", "Unknown")
            filename = chunk.get("filename", "Document")
            content = chunk.get("content", "")
            similarity = chunk.get("similarity", 0.0)

            formatted.append(
                f"""**Evidence {idx}** (Similarity: {similarity:.2%})
Source: {filename}
Page: {page_num}

{content}

---"""
            )

        return "\n\n".join(formatted)

    async def analyze_document_structure(
        self,
        full_text: str,
        pages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze overall document structure to identify sections and organization.

        Args:
            full_text: Complete document text
            pages: List of page information

        Returns:
            Document structure analysis
        """
        try:
            user_prompt = f"""Analyze the structure of this IPO document.

**Total Pages**: {len(pages)}

**Document Preview** (first 2000 characters):
{full_text[:2000]}

Identify document type, main sections, key pages, and metadata."""

            response = self.client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=4096,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            logger.info("Analyzed document structure")
            return result

        except Exception as e:
            logger.error(f"Error analyzing document structure: {e}")
            return {
                "document_type": "Unknown",
                "main_sections": [],
                "key_pages": [],
                "metadata": {}
            }


# Singleton instance
mistral_service = MistralService()
