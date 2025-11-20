
import { GoogleGenAI, Type } from "@google/genai";
import { SupportingDocument, VerificationStatus, VerifiedSentence, DocumentChunk } from "../types";

const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

// --- CONSTANTS & CONFIG ---
const EMBEDDING_MODEL = "text-embedding-004";
const VERIFICATION_MODEL = "gemini-2.5-flash";
const CHUNK_SIZE = 800; // Characters
const CHUNK_OVERLAP = 100; // Characters
const RETRIEVAL_TOP_K = 3; // Number of chunks to retrieve per claim

// --- IN-MEMORY VECTOR STORE ---
// In a real backend, this would be Weaviate or Pinecone
let vectorStore: DocumentChunk[] = [];

// --- HELPER: COSINE SIMILARITY ---
const cosineSimilarity = (vecA: number[], vecB: number[]): number => {
  let dotProduct = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < vecA.length; i++) {
    dotProduct += vecA[i] * vecB[i];
    normA += vecA[i] * vecA[i];
    normB += vecB[i] * vecB[i];
  }
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
};

// --- 1. CHUNKING ---
const chunkText = (text: string, docId: string): DocumentChunk[] => {
  const chunks: DocumentChunk[] = [];
  let start = 0;
  
  while (start < text.length) {
    const end = Math.min(start + CHUNK_SIZE, text.length);
    const chunkText = text.slice(start, end);
    
    chunks.push({
      id: `${docId}_${start}`,
      docId: docId,
      text: chunkText,
      vector: [] // To be filled
    });
    
    start += (CHUNK_SIZE - CHUNK_OVERLAP);
  }
  return chunks;
};

// --- 2. SINGLE DOCUMENT INDEXING (Auto-Index on Upload) ---
export const indexSingleDocument = async (
  doc: SupportingDocument
): Promise<SupportingDocument> => {
  // Check if already indexed to prevent duplicates in store
  if (vectorStore.some(chunk => chunk.docId === doc.id)) {
    return { ...doc, isIndexed: true };
  }

  const chunks = chunkText(doc.content, doc.id);
  const docWithCount = { ...doc, chunkCount: chunks.length, isIndexed: false };
  
  const BATCH_SIZE = 5;
  const indexedChunks: DocumentChunk[] = [];

  for (let i = 0; i < chunks.length; i += BATCH_SIZE) {
    const batch = chunks.slice(i, i + BATCH_SIZE);
    
    await Promise.all(batch.map(async (chunk) => {
      try {
        const response = await ai.models.embedContent({
          model: EMBEDDING_MODEL,
          contents: chunk.text
        });
        
        if (response.embeddings?.[0]?.values) {
          chunk.vector = response.embeddings[0].values;
          indexedChunks.push(chunk);
        }
      } catch (err) {
        console.warn(`Failed to embed chunk for doc ${chunk.docId}`, err);
      }
    }));
  }

  // Append to global store
  vectorStore.push(...indexedChunks);
  
  return { ...docWithCount, isIndexed: true };
};

// Keep batch function for backward compatibility if needed, but verify logic calls single index
export const indexDocuments = async (
  documents: SupportingDocument[], 
  onProgress?: (current: number, total: number) => void
): Promise<SupportingDocument[]> => {
  vectorStore = []; // Reset store only on full re-index
  const processedDocs: SupportingDocument[] = [];
  
  for (let i = 0; i < documents.length; i++) {
    const doc = await indexSingleDocument(documents[i]);
    processedDocs.push(doc);
    if (onProgress) onProgress(i + 1, documents.length);
  }

  return processedDocs;
};

// --- 3. RETRIEVAL ---
const retrieveRelevantContext = async (queryText: string): Promise<DocumentChunk[]> => {
  if (vectorStore.length === 0) return [];

  try {
    const response = await ai.models.embedContent({
      model: EMBEDDING_MODEL,
      contents: queryText
    });

    const queryVector = response.embeddings?.[0]?.values;
    if (!queryVector) return [];

    const scoredChunks = vectorStore.map(chunk => ({
      chunk,
      score: cosineSimilarity(queryVector, chunk.vector)
    }));

    scoredChunks.sort((a, b) => b.score - a.score);

    return scoredChunks.slice(0, RETRIEVAL_TOP_K).map(s => s.chunk);

  } catch (error) {
    console.error("Retrieval failed", error);
    return [];
  }
};

// --- 4. VERIFICATION (RAG) ---
export const verifySentenceWithRAG = async (
  sentence: string,
  supportingDocs: SupportingDocument[]
): Promise<Omit<VerifiedSentence, 'id' | 'isParagraphEnd'>> => {
  
  // A. Retrieve Context
  const relevantChunks = await retrieveRelevantContext(sentence);
  
  // Format context for LLM
  const contextString = relevantChunks.map(c => {
    const docName = supportingDocs.find(d => d.id === c.docId)?.name || "Unknown Doc";
    return `Source: [${docName} (ID: ${c.docId})]
Content: "...${c.text}..."`;
  }).join('\n\n');

  if (relevantChunks.length === 0) {
    return {
      text: sentence,
      status: VerificationStatus.UNVERIFIED,
      reasoning: "No relevant content found in the data room embeddings.",
      confidence: 0
    };
  }

  // B. Generate Verification
  const prompt = `
    You are a strict Financial Auditor. Verify the CLAIM based ONLY on the provided CONTEXT.

    CLAIM: "${sentence}"

    RETRIEVED CONTEXT:
    ${contextString}

    INSTRUCTIONS:
    1. Compare the CLAIM against the CONTEXT.
    2. If the context supports the claim, status is VERIFIED.
    3. If the context partially supports it (e.g. different date, close number), status is PARTIAL.
    4. If the context contradicts or doesn't contain the info, status is UNVERIFIED.
    5. EXTRACT the exact text from the context as the citation.
    6. Confidence score (0-100).

    OUTPUT JSON ONLY.
  `;

  try {
    const response = await ai.models.generateContent({
      model: VERIFICATION_MODEL,
      contents: prompt,
      config: {
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            status: { type: Type.STRING, enum: ["VERIFIED", "PARTIAL", "UNVERIFIED"] },
            reasoning: { type: Type.STRING },
            citationSourceId: { type: Type.STRING },
            citationText: { type: Type.STRING },
            confidence: { type: Type.INTEGER }
          }
        }
      }
    });

    const result = JSON.parse(response.text || "{}");
    
    return {
      text: sentence,
      status: result.status as VerificationStatus,
      reasoning: result.reasoning,
      citationSourceId: result.citationSourceId,
      citationText: result.citationText,
      confidence: result.confidence
    };

  } catch (error) {
    console.error("Verification generation failed", error);
    return {
      text: sentence,
      status: VerificationStatus.UNVERIFIED,
      reasoning: "AI processing failed",
      confidence: 0
    };
  }
};

// Wrapper for batch processing the whole document
export const analyzeIPODocumentRAG = async (
  sentences: VerifiedSentence[], 
  supportingDocs: SupportingDocument[],
  onProgress: (count: number) => void
): Promise<VerifiedSentence[]> => {
  
  const results: VerifiedSentence[] = [];
  const BATCH_SIZE = 3;
  
  for (let i = 0; i < sentences.length; i += BATCH_SIZE) {
    const batch = sentences.slice(i, i + BATCH_SIZE);
    
    const batchResults = await Promise.all(batch.map(async (s) => {
      if (s.text.length < 15) return s; // Skip short noise
      
      const verification = await verifySentenceWithRAG(s.text, supportingDocs);
      return { ...s, ...verification };
    }));

    results.push(...batchResults);
    onProgress(results.length);
  }

  return results;
};
