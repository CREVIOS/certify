
export enum VerificationStatus {
  VERIFIED = 'VERIFIED',
  PARTIAL = 'PARTIAL',
  UNVERIFIED = 'UNVERIFIED',
  PENDING = 'PENDING'
}

export interface SupportingDocument {
  id: string;
  name: string;
  type: string;
  content: string;
  uploadDate: string;
  isIndexed?: boolean; // Track if embeddings are generated
  chunkCount?: number;
}

export interface DocumentChunk {
  id: string;
  docId: string;
  text: string;
  vector: number[]; // Embedding vector
}

export interface VerifiedSentence {
  id: number;
  text: string;
  status: VerificationStatus;
  reasoning?: string;
  citationSourceId?: string;
  citationText?: string;
  confidence?: number;
  isParagraphEnd?: boolean;
}

export interface IPODocument {
  id: string;
  title: string;
  content: string;
  sentences: VerifiedSentence[];
  file?: File;
}
