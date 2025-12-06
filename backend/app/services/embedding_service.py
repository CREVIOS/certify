"""OpenAI embedding service using text-embedding-3-large."""

from typing import List, Union
from loguru import logger
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
import asyncio

from app.core.config import settings


class EmbeddingService:
    """Service for generating embeddings using OpenAI text-embedding-3-large."""

    def __init__(self):
        """Initialize OpenAI client."""
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_EMBEDDING_MODEL
        self.dimension = settings.OPENAI_EMBEDDING_DIMENSION
        self.batch_size = settings.OPENAI_EMBEDDING_BATCH_SIZE

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (3072 dimensions)
        """
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimension
            )

            embedding = response.data[0].embedding
            logger.debug(f"Generated embedding for text (length: {len(text)})")
            return embedding

        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        try:
            # Process in batches to respect API limits
            all_embeddings = []

            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]

                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimension
                )

                # Extract embeddings in order
                embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(embeddings)

                logger.info(f"Generated embeddings for batch {i//self.batch_size + 1} ({len(batch)} texts)")

            return all_embeddings

        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            raise

    async def embed_documents(
        self,
        documents: List[str],
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        Embed multiple documents with progress tracking.

        Args:
            documents: List of document texts
            show_progress: Whether to log progress

        Returns:
            List of embeddings
        """
        embeddings = []
        total_batches = (len(documents) + self.batch_size - 1) // self.batch_size

        for i in range(0, len(documents), self.batch_size):
            batch = documents[i:i + self.batch_size]
            batch_embeddings = await self.embed_batch(batch)
            embeddings.extend(batch_embeddings)

            if show_progress:
                current_batch = i // self.batch_size + 1
                logger.info(f"Progress: {current_batch}/{total_batches} batches completed")

        return embeddings

    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings."""
        return self.dimension

    async def compute_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0-1)
        """
        import numpy as np

        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        # Cosine similarity
        similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

        return float(similarity)


# Singleton instance
embedding_service = EmbeddingService()
