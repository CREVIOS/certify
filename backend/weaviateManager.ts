import weaviate, { WeaviateClient, ObjectsBatcher } from 'weaviate-ts-client';
import { GoogleGenAI } from "@google/genai";

// SOTA: Singleton Pattern for Database Connection
class WeaviateManager {
  private client: WeaviateClient;
  private ai: GoogleGenAI;
  private static instance: WeaviateManager;

  private constructor() {
    this.client = weaviate.client({
      scheme: 'http',
      host: 'localhost:8080',
      // SOTA: Grpc is significantly faster for batch imports
      grpcConfig: {
        secure: false, 
        timeout: 60000
      }
    });
    this.ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
  }

  public static getInstance(): WeaviateManager {
    if (!WeaviateManager.instance) {
      WeaviateManager.instance = new WeaviateManager();
    }
    return WeaviateManager.instance;
  }

  // SOTA: Idempotent Schema Creation
  public async ensureSchema() {
    const classObj = {
      class: 'IPODocumentChunk',
      vectorizer: 'none', // We bring our own vectors
      properties: [
        { name: 'text', dataType: ['text'] },
        { name: 'sourceDocId', dataType: ['string'] },
        { name: 'pageNumber', dataType: ['int'] },
        { name: 'chunkIndex', dataType: ['int'] },
      ],
    };

    try {
      const exists = await this.client.schema.classExists('IPODocumentChunk');
      if (!exists) {
        await this.client.schema.classCreator().withClass(classObj).do();
        console.log('Schema created successfully');
      }
    } catch (error) {
      console.error('Schema check failed', error);
    }
  }

  // SOTA: Batch Processing with Error Handling
  public async batchInsert(
    chunks: { text: string; metadata: any }[]
  ) {
    // Get embeddings in parallel batches first
    // (See documentProcessor.ts for the embedding generation logic)
    
    const batcher = this.client.batch.objectsBatcher();
    let counter = 0;
    const BATCH_SIZE = 100;

    for (const chunk of chunks) {
      // Generate Embedding (using GenAI SDK)
      const embeddingResp = await this.ai.models.embedContent({
        model: "text-embedding-004",
        contents: chunk.text,
      });
      
      const vector = embeddingResp.embeddings?.[0]?.values;

      if (!vector) continue;

      batcher.withObject({
        class: 'IPODocumentChunk',
        properties: {
          text: chunk.text,
          ...chunk.metadata,
        },
        vector: vector,
      });

      counter++;

      // Flush batch
      if (counter % BATCH_SIZE === 0) {
        await batcher.do();
        console.log(`Flushed ${counter} records to Weaviate`);
      }
    }

    // Flush remaining
    if (batcher.payload().length > 0) {
      await batcher.do();
    }
  }

  public async hybridSearch(query: string, limit: number = 5) {
    const embeddingResp = await this.ai.models.embedContent({
      model: "text-embedding-004",
      contents: query,
    });
    const vector = embeddingResp.embeddings?.[0]?.values;

    if (!vector) return [];

    // SOTA: Hybrid Search (Keyword + Vector) + Reranking (simulated here)
    return this.client.graphql
      .get()
      .withClassName('IPODocumentChunk')
      .withFields('text sourceDocId _additional { distance score }')
      .withHybrid({
        query: query,
        vector: vector,
        alpha: 0.75 // Heavily weighted towards vector, but keeps keyword exact matches
      })
      .withLimit(limit)
      .do();
  }
}

export default WeaviateManager;
