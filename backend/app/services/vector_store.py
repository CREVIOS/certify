"""Weaviate vector store service for semantic search with OpenAI embeddings."""

from typing import List, Dict, Optional
from uuid import UUID
import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.query import MetadataQuery
from loguru import logger
import asyncio

from app.core.config import settings
from app.services.embedding_service import embedding_service


class VectorStoreService:
    """Service for managing vector embeddings in Weaviate using OpenAI."""

    def __init__(self):
        """Initialize Weaviate client."""
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Weaviate client."""
        try:
            # Connect to Weaviate
            if settings.WEAVIATE_API_KEY:
                self.client = weaviate.connect_to_custom(
                    http_host=settings.WEAVIATE_URL.replace('http://', '').replace('https://', ''),
                    http_port=8080,
                    http_secure=False,
                    grpc_host=settings.WEAVIATE_URL.replace('http://', '').replace('https://', ''),
                    grpc_port=50051,
                    grpc_secure=False,
                    auth_credentials=Auth.api_key(settings.WEAVIATE_API_KEY),
                )
            else:
                self.client = weaviate.connect_to_local(
                    host=settings.WEAVIATE_URL.replace('http://', '').replace('https://', ''),
                    port=8080,
                )

            logger.info("Weaviate client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Weaviate client: {e}")
            raise

    def create_schema(self, project_id: UUID):
        """
        Create Weaviate schema for a project.

        Args:
            project_id: Project UUID
        """
        try:
            collection_name = f"Project_{str(project_id).replace('-', '_')}"

            # Check if collection exists
            if self.client.collections.exists(collection_name):
                logger.info(f"Collection {collection_name} already exists")
                return

            # Create collection
            self.client.collections.create(
                name=collection_name,
                properties=[
                    {
                        "name": "content",
                        "dataType": ["text"],
                        "description": "Document chunk content"
                    },
                    {
                        "name": "document_id",
                        "dataType": ["text"],
                        "description": "Source document ID"
                    },
                    {
                        "name": "chunk_id",
                        "dataType": ["text"],
                        "description": "Document chunk ID"
                    },
                    {
                        "name": "page_number",
                        "dataType": ["int"],
                        "description": "Page number"
                    },
                    {
                        "name": "start_char",
                        "dataType": ["int"],
                        "description": "Start character position"
                    },
                    {
                        "name": "end_char",
                        "dataType": ["int"],
                        "description": "End character position"
                    },
                    {
                        "name": "filename",
                        "dataType": ["text"],
                        "description": "Source filename"
                    },
                    {
                        "name": "document_type",
                        "dataType": ["text"],
                        "description": "Document type (main/supporting)"
                    }
                ],
                vectorizer_config=None  # We'll provide vectors manually
            )

            logger.info(f"Created Weaviate collection: {collection_name}")

        except Exception as e:
            logger.error(f"Error creating Weaviate schema: {e}")
            raise

    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for text using OpenAI.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (3072 dimensions for text-embedding-3-large)
        """
        try:
            embedding = await embedding_service.embed_text(text)
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    async def index_chunks(
        self,
        project_id: UUID,
        chunks: List[Dict],
        document_id: UUID,
        filename: str,
        document_type: str
    ) -> List[str]:
        """
        Index document chunks in Weaviate using OpenAI embeddings.

        Args:
            project_id: Project UUID
            chunks: List of chunk dictionaries
            document_id: Document UUID
            filename: Source filename
            document_type: Document type

        Returns:
            List of Weaviate object IDs
        """
        try:
            collection_name = f"Project_{str(project_id).replace('-', '_')}"
            collection = self.client.collections.get(collection_name)

            weaviate_ids = []
            batch_size = settings.WEAVIATE_BATCH_SIZE

            # Process in batches
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]

                # Generate embeddings for entire batch using OpenAI
                texts = [chunk["content"] for chunk in batch]
                vectors = await embedding_service.embed_batch(texts)

                with collection.batch.dynamic() as batch_context:
                    for chunk, vector in zip(batch, vectors):
                        # Prepare properties
                        properties = {
                            "content": chunk["content"],
                            "document_id": str(document_id),
                            "chunk_id": chunk.get("id", ""),
                            "page_number": chunk.get("page_number", 0),
                            "start_char": chunk.get("start_char", 0),
                            "end_char": chunk.get("end_char", 0),
                            "filename": filename,
                            "document_type": document_type
                        }

                        # Add to batch
                        uuid = batch_context.add_object(
                            properties=properties,
                            vector=vector
                        )
                        weaviate_ids.append(str(uuid))

                logger.info(f"Indexed batch {i//batch_size + 1} ({len(batch)} chunks)")

            logger.info(f"Indexed {len(chunks)} chunks for document {document_id}")
            return weaviate_ids

        except Exception as e:
            logger.error(f"Error indexing chunks: {e}")
            raise

    async def search_similar(
        self,
        project_id: UUID,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.7
    ) -> List[Dict]:
        """
        Search for similar chunks using semantic search with OpenAI embeddings.

        Args:
            project_id: Project UUID
            query: Search query
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold

        Returns:
            List of similar chunks with metadata
        """
        try:
            collection_name = f"Project_{str(project_id).replace('-', '_')}"
            collection = self.client.collections.get(collection_name)

            # Generate query embedding using OpenAI
            query_vector = await self.embed_text(query)

            # Perform vector search
            response = collection.query.near_vector(
                near_vector=query_vector,
                limit=limit,
                return_metadata=MetadataQuery(distance=True)
            )

            # Process results
            results = []
            for obj in response.objects:
                # Convert distance to similarity (cosine distance to similarity)
                similarity = 1 - obj.metadata.distance

                if similarity >= min_similarity:
                    results.append({
                        "content": obj.properties["content"],
                        "document_id": obj.properties["document_id"],
                        "chunk_id": obj.properties.get("chunk_id"),
                        "page_number": obj.properties.get("page_number"),
                        "start_char": obj.properties.get("start_char"),
                        "end_char": obj.properties.get("end_char"),
                        "filename": obj.properties.get("filename"),
                        "document_type": obj.properties.get("document_type"),
                        "similarity": similarity
                    })

            logger.info(f"Found {len(results)} similar chunks for query")
            return results

        except Exception as e:
            logger.error(f"Error searching similar chunks: {e}")
            raise

    def delete_document_chunks(self, project_id: UUID, document_id: UUID):
        """
        Delete all chunks for a document.

        Args:
            project_id: Project UUID
            document_id: Document UUID
        """
        try:
            collection_name = f"Project_{str(project_id).replace('-', '_')}"
            collection = self.client.collections.get(collection_name)

            # Delete chunks matching document_id
            collection.data.delete_many(
                where={
                    "path": ["document_id"],
                    "operator": "Equal",
                    "valueText": str(document_id)
                }
            )

            logger.info(f"Deleted chunks for document {document_id}")

        except Exception as e:
            logger.error(f"Error deleting document chunks: {e}")
            raise

    def delete_collection(self, project_id: UUID):
        """
        Delete entire collection for a project.

        Args:
            project_id: Project UUID
        """
        try:
            collection_name = f"Project_{str(project_id).replace('-', '_')}"

            if self.client.collections.exists(collection_name):
                self.client.collections.delete(collection_name)
                logger.info(f"Deleted collection: {collection_name}")

        except Exception as e:
            logger.error(f"Error deleting collection: {e}")
            raise

    def close(self):
        """Close Weaviate client connection."""
        if self.client:
            self.client.close()
            logger.info("Weaviate client connection closed")


# Singleton instance
vector_store = VectorStoreService()
