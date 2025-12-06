"""
Document processing service for PDF and DOCX files with Mistral OCR support.

Uses LangChain's RecursiveCharacterTextSplitter for optimal chunking with:
- Smart text splitting at natural boundaries (paragraphs, sentences, words)
- Configurable chunk size and overlap
- Sentence-level extraction for verification tasks
- Page number tracking for citations
"""

import os
import re
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from loguru import logger

import PyPDF2
import pdfplumber
from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from nltk.tokenize import sent_tokenize
import nltk

from app.core.config import settings

# Download NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')


class DocumentProcessor:
    """Service for processing documents (PDF, DOCX) and extracting text."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        use_mistral_ocr: bool = True
    ):
        """
        Initialize document processor with LangChain best practices.

        Args:
            chunk_size: Size of text chunks (default 1000 - optimal for most use cases)
            chunk_overlap: Overlap between chunks (default 200 - 20% overlap recommended)
            use_mistral_ocr: Whether to use Mistral OCR for PDF extraction

        LangChain Best Practices:
        - Chunk size: 1000-1500 characters for balanced performance
        - Overlap: 10-20% of chunk size to maintain context
        - Separators: Prioritize paragraph > sentence > word boundaries
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_mistral_ocr = use_mistral_ocr

        # Use LangChain's RecursiveCharacterTextSplitter with optimal separators
        # This splits at natural boundaries in order: paragraphs -> sentences -> words
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=[
                "\n\n",    # Double newline (paragraphs)
                "\n",      # Single newline (lines)
                ". ",      # Sentence boundaries
                "! ",      # Exclamation sentences
                "? ",      # Question sentences
                "; ",      # Semicolons
                ": ",      # Colons
                ", ",      # Commas
                " ",       # Words
                "",        # Characters (fallback)
            ],
            keep_separator=True,
            is_separator_regex=False,
        )

        # Import Mistral service only if needed
        if self.use_mistral_ocr:
            try:
                from app.services.mistral_service import mistral_service
                self.mistral_service = mistral_service
                logger.info("Mistral OCR enabled for document processing")
            except Exception as e:
                logger.warning(f"Failed to load Mistral service: {e}. Falling back to pdfplumber.")
                self.use_mistral_ocr = False
                self.mistral_service = None
        else:
            self.mistral_service = None

    async def extract_text_from_pdf(self, file_path: str) -> Dict[str, any]:
        """
        Extract text from PDF file with page information.
        Uses Mistral OCR if enabled, otherwise falls back to pdfplumber.

        Args:
            file_path: Path to PDF file

        Returns:
            Dict containing full text, pages, and metadata
        """
        try:
            # Try Mistral OCR first if enabled
            if self.use_mistral_ocr and self.mistral_service:
                try:
                    logger.info(f"Using Mistral OCR for PDF extraction: {file_path}")
                    result = await self.mistral_service.extract_text_from_pdf_ocr(file_path)
                    logger.info(f"Mistral OCR extracted {result['page_count']} pages from: {file_path}")
                    return result
                except Exception as ocr_error:
                    logger.warning(f"Mistral OCR failed: {ocr_error}. Falling back to pdfplumber.")

            # Fallback to pdfplumber
            logger.info(f"Using pdfplumber for PDF extraction: {file_path}")
            pages = []
            full_text = ""

            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    pages.append({
                        "page_number": page_num,
                        "text": text,
                        "char_start": len(full_text),
                        "char_end": len(full_text) + len(text)
                    })
                    full_text += text + "\n"

                metadata = {
                    "page_count": len(pdf.pages),
                    "metadata": pdf.metadata or {},
                    "extraction_method": "pdfplumber"
                }

            logger.info(f"Extracted {len(pages)} pages from PDF: {file_path}")

            return {
                "full_text": full_text,
                "pages": pages,
                "page_count": len(pages),
                "metadata": metadata
            }

        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {e}")
            raise

    async def extract_text_from_docx(self, file_path: str) -> Dict[str, any]:
        """
        Extract text from DOCX file.

        Args:
            file_path: Path to DOCX file

        Returns:
            Dict containing full text and metadata
        """
        try:
            doc = DocxDocument(file_path)
            paragraphs = []
            full_text = ""

            for para in doc.paragraphs:
                text = para.text
                if text.strip():
                    paragraphs.append({
                        "text": text,
                        "char_start": len(full_text),
                        "char_end": len(full_text) + len(text)
                    })
                    full_text += text + "\n"

            metadata = {
                "paragraph_count": len(paragraphs),
                "core_properties": {
                    "author": doc.core_properties.author,
                    "created": str(doc.core_properties.created),
                    "modified": str(doc.core_properties.modified),
                    "title": doc.core_properties.title,
                }
            }

            logger.info(f"Extracted {len(paragraphs)} paragraphs from DOCX: {file_path}")

            return {
                "full_text": full_text,
                "paragraphs": paragraphs,
                "paragraph_count": len(paragraphs),
                "metadata": metadata,
                "pages": []  # DOCX doesn't have pages
            }

        except Exception as e:
            logger.error(f"Error extracting text from DOCX {file_path}: {e}")
            raise

    async def extract_text(self, file_path: str) -> Dict[str, any]:
        """
        Extract text from document (auto-detect format).

        Args:
            file_path: Path to document

        Returns:
            Dict containing extracted text and metadata
        """
        ext = Path(file_path).suffix.lower()

        if ext == '.pdf':
            return await self.extract_text_from_pdf(file_path)
        elif ext in ['.docx', '.doc']:
            return await self.extract_text_from_docx(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def create_chunks(self, text: str, metadata: Dict = None) -> List[Dict]:
        """
        Split text into chunks for embedding.

        Args:
            text: Text to split
            metadata: Additional metadata for chunks

        Returns:
            List of chunk dictionaries
        """
        chunks = self.text_splitter.split_text(text)
        chunk_dicts = []

        current_pos = 0
        for idx, chunk in enumerate(chunks):
            chunk_dict = {
                "index": idx,
                "content": chunk,
                "start_char": current_pos,
                "end_char": current_pos + len(chunk),
                "metadata": metadata or {}
            }
            chunk_dicts.append(chunk_dict)
            current_pos += len(chunk)

        logger.info(f"Created {len(chunk_dicts)} chunks from text")
        return chunk_dicts

    def extract_sentences(self, text: str) -> List[Dict]:
        """
        Extract sentences from text with position information.

        Args:
            text: Text to extract sentences from

        Returns:
            List of sentence dictionaries with positions
        """
        sentences = []
        current_pos = 0

        # Use NLTK for better sentence tokenization
        sent_list = sent_tokenize(text)

        for idx, sentence in enumerate(sent_list):
            # Find the position in the original text
            start_pos = text.find(sentence, current_pos)
            if start_pos == -1:
                start_pos = current_pos

            end_pos = start_pos + len(sentence)

            sentences.append({
                "index": idx,
                "content": sentence.strip(),
                "start_char": start_pos,
                "end_char": end_pos
            })

            current_pos = end_pos

        logger.info(f"Extracted {len(sentences)} sentences from text")
        return sentences

    def map_sentences_to_pages(self, sentences: List[Dict], pages: List[Dict]) -> List[Dict]:
        """
        Map sentences to their corresponding page numbers.

        Args:
            sentences: List of sentence dictionaries
            pages: List of page dictionaries with char positions

        Returns:
            Updated sentences with page numbers
        """
        for sentence in sentences:
            for page in pages:
                if page["char_start"] <= sentence["start_char"] < page["char_end"]:
                    sentence["page_number"] = page["page_number"]
                    break
            else:
                sentence["page_number"] = None

        return sentences

    async def process_document_for_indexing(self, file_path: str) -> Dict:
        """
        Process document for indexing (chunking and embedding).

        Args:
            file_path: Path to document

        Returns:
            Dict with chunks ready for indexing
        """
        # Extract text
        extraction_result = await self.extract_text(file_path)

        # Create chunks
        chunks = self.create_chunks(
            extraction_result["full_text"],
            metadata=extraction_result.get("metadata", {})
        )

        # Add page information if available
        if extraction_result.get("pages"):
            for chunk in chunks:
                for page in extraction_result["pages"]:
                    if page["char_start"] <= chunk["start_char"] < page["char_end"]:
                        chunk["page_number"] = page["page_number"]
                        break

        return {
            "chunks": chunks,
            "full_text": extraction_result["full_text"],
            "pages": extraction_result.get("pages", []),
            "metadata": extraction_result.get("metadata", {})
        }

    async def process_document_for_verification(self, file_path: str) -> Dict:
        """
        Process main document for verification (sentence extraction).

        Args:
            file_path: Path to main document

        Returns:
            Dict with sentences ready for verification
        """
        # Extract text
        extraction_result = await self.extract_text(file_path)

        # Extract sentences
        sentences = self.extract_sentences(extraction_result["full_text"])

        # Map sentences to pages
        if extraction_result.get("pages"):
            sentences = self.map_sentences_to_pages(
                sentences,
                extraction_result["pages"]
            )

        return {
            "sentences": sentences,
            "full_text": extraction_result["full_text"],
            "pages": extraction_result.get("pages", []),
            "metadata": extraction_result.get("metadata", {})
        }
