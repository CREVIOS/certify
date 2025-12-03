import { RecursiveCharacterTextSplitter } from "@langchain/textsplitters";
import WeaviateManager from "./weaviateManager";

// Configuration
const CHUNK_SIZE = 1000;
const CHUNK_OVERLAP = 200;
// Note: CONCURRENCY_LIMIT reserved for future parallel processing implementation
// const CONCURRENCY_LIMIT = 10; // Max concurrent embedding requests to avoid 429 errors

export interface ProcessingJobData {
  jobId: string;
  filePath: string;
  rawText: string;
  metadata: {
    docId: string;
    docName: string;
  };
}

export const processDocument = async (data: ProcessingJobData) => {
  console.log(`Starting processing for job: ${data.jobId}`);
  
  const weaviateManager = WeaviateManager.getInstance();
  await weaviateManager.ensureSchema();

  // 1. SOTA Chunking with LangChain
  // Recursive splitters preserve semantic meaning better than fixed-size splitters
  const splitter = new RecursiveCharacterTextSplitter({
    chunkSize: CHUNK_SIZE,
    chunkOverlap: CHUNK_OVERLAP,
    separators: ["\n\n", "\n", ". ", " ", ""], // Priority splitting
  });

  const output = await splitter.createDocuments([data.rawText], [{
    sourceDocId: data.metadata.docId,
    sourceName: data.metadata.docName
  }]);

  console.log(`Generated ${output.length} chunks for ${data.metadata.docName}`);

  // 2. Parallel Processing with Rate Limiting (The SOTA part)
  // We don't want to send 1000 chunks to Weaviate/Gemini at once.
  // Future: We can map the chunks to an array of promises, controlled by p-limit.
  
  // We create a data structure ready for the Weaviate Manager
  // In a real SOTA system, we might decouple Embedding generation from DB Insertion
  // for even higher throughput, but here we bundle them for atomic batching.
  
  const chunksToIngest = output.map((chunk, index) => ({
    text: chunk.pageContent,
    metadata: {
      ...chunk.metadata,
      chunkIndex: index
    }
  }));

  // 3. Batch Ingestion
  // Weaviate Manager handles the specific batching logic (e.g. groups of 100)
  // This call is awaited to ensure data consistency before marking job as done.
  await weaviateManager.batchInsert(chunksToIngest);

  console.log(`Job ${data.jobId} completed successfully.`);
  return { chunksProcessed: output.length };
};
