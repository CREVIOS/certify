"""Weaviate vector store service for semantic search with OpenAI embeddings."""

from typing import List, Dict, Optional
from uuid import UUID
import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.query import MetadataQuery
from weaviate.classes.config import Property, DataType, Configure
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
            # Parse the Weaviate URL to extract host and port
            from urllib.parse import urlparse
            parsed_url = urlparse(settings.WEAVIATE_URL)
            host = parsed_url.hostname or 'localhost'
            port = parsed_url.port or 8080

            # Connect to Weaviate
            if settings.WEAVIATE_API_KEY:
                self.client = weaviate.connect_to_custom(
                    http_host=host,
                    http_port=port,
                    http_secure=False,
                    grpc_host=host,
                    grpc_port=50051,
                    grpc_secure=False,
                    auth_credentials=Auth.api_key(settings.WEAVIATE_API_KEY),
                )
            else:
                self.client = weaviate.connect_to_local(
                    host=host,
                    port=port,
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
                    Property(
                        name="content",
                        data_type=DataType.TEXT,
                        description="Document chunk content",
                    ),
                    Property(
                        name="document_id",
                        data_type=DataType.TEXT,
                        description="Source document ID",
                    ),
                    Property(
                        name="chunk_id",
                        data_type=DataType.TEXT,
                        description="Document chunk ID",
                    ),
                    Property(
                        name="page_number",
                        data_type=DataType.INT,
                        description="Page number",
                    ),
                    Property(
                        name="start_char",
                        data_type=DataType.INT,
                        description="Start character position",
                    ),
                    Property(
                        name="end_char",
                        data_type=DataType.INT,
                        description="End character position",
                    ),
                    Property(
                        name="filename",
                        data_type=DataType.TEXT,
                        description="Source filename",
                    ),
                    Property(
                        name="document_type",
                        data_type=DataType.TEXT,
                        description="Document type (main/supporting)",
                    ),
                ],
                # We provide vectors manually via embedding_service, so disable built-in vectorizer
                vectorizer_config=Configure.Vectorizer.none(),
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

            # Embed and send sequentially to avoid any batching issues
            with collection.batch.dynamic() as batch_context:
                for idx, chunk in enumerate(chunks):
                    logger.info(
                        f"[weaviate] Embedding chunk {idx + 1}/{len(chunks)} "
                        f"(len={len(chunk['content'])})"
                    )

                    vector = await embedding_service.embed_text(chunk["content"])

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

                    uuid = batch_context.add_object(
                        properties=properties,
                        vector=vector
                    )
                    weaviate_ids.append(str(uuid))
                    logger.info(f"[weaviate] Added chunk {idx + 1}/{len(chunks)} to batch")

            logger.info(f"Indexed {len(chunks)} chunks for document {document_id}")
            return weaviate_ids

        except Exception as e:
            logger.error(f"Error indexing chunks: {e}")
            raise

    async def search_similar(
        self,
        project_id: UUID,
        query: str,
        limit: int = None,
        min_similarity: float = None
    ) -> List[Dict]:
        """
        Semantic search using embeddings (top-k up to 20-30 as requested).
        """
        try:
            limit = limit or settings.SEMANTIC_TOP_K
            min_similarity = min_similarity or settings.MIN_SIMILARITY_THRESHOLD

            collection_name = f"Project_{str(project_id).replace('-', '_')}"
            collection = self.client.collections.get(collection_name)

            query_vector = await self.embed_text(query)

            response = collection.query.near_vector(
                near_vector=query_vector,
                limit=limit,
                return_metadata=MetadataQuery(distance=True)
            )

            results = []
            missing_distance = 0
            for obj in response.objects:
                distance = obj.metadata.distance
                if distance is None:
                    missing_distance += 1
                    continue  # semantic results require a distance

                similarity = 1 - distance
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
                        "similarity": similarity,
                        "source": "semantic"
                    })

            if missing_distance:
                logger.warning(f"Semantic search skipped {missing_distance} results with missing distance")

            logger.info(f"Found {len(results)} semantic chunks for query")
            return results

        except Exception as e:
            logger.error(f"Error searching similar chunks: {e}")
            raise

    async def search_hybrid(
        self,
        project_id: UUID,
        query: str,
        limit: int = None,
        alpha: float = None
    ) -> List[Dict]:
        """
        Hybrid keyword + semantic search. Uses Weaviate hybrid search to capture exact
        keyword matches after retrieving semantic top-k.
        """
        try:
            limit = limit or settings.KEYWORD_TOP_K
            alpha = alpha or settings.HYBRID_ALPHA

            collection_name = f"Project_{str(project_id).replace('-', '_')}"
            collection = self.client.collections.get(collection_name)

            query_vector = await self.embed_text(query)

            response = collection.query.hybrid(
                query=query,
                vector=query_vector,
                alpha=alpha,
                limit=limit,
                return_metadata=MetadataQuery(distance=True)
            )

            hybrid_results = []
            missing_distance = 0
            for obj in response.objects:
                distance = obj.metadata.distance
                if distance is None:
                    # Keep keyword-only hits but flag them and set minimal similarity
                    similarity = 0.0
                    missing_distance += 1
                    source = "hybrid_keyword_only"
                else:
                    similarity = 1 - distance
                    source = "hybrid"

                hybrid_results.append({
                    "content": obj.properties["content"],
                    "document_id": obj.properties["document_id"],
                    "chunk_id": obj.properties.get("chunk_id"),
                    "page_number": obj.properties.get("page_number"),
                    "start_char": obj.properties.get("start_char"),
                    "end_char": obj.properties.get("end_char"),
                    "filename": obj.properties.get("filename"),
                    "document_type": obj.properties.get("document_type"),
                    "similarity": similarity,
                    "source": source
                })

            if missing_distance:
                logger.warning(f"Hybrid search had {missing_distance} keyword-only results without distance")

            logger.info(f"Found {len(hybrid_results)} hybrid chunks for query")
            return hybrid_results
        except Exception as e:
            logger.error(f"Error running hybrid search: {e}")
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
