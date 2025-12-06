
export enum VerificationStatus {
  VERIFIED = 'VERIFIED',
  PARTIAL = 'PARTIAL',
  UNVERIFIED = 'UNVERIFIED',
  PENDING = 'PENDING'
}

export interface Section {
  title: string;
  start_page: number;
  end_page: number;
  summary?: string;
}

export interface SupportingDocument {
  id: string;
  name: string;
  type: string;
  content: string;
  uploadDate: string;
  isIndexed?: boolean; // Track if embeddings are generated
  chunkCount?: number;
  backendId?: string;
}

export interface DocumentChunk {
  id: string;
  docId: string;
  text: string;
  vector: number[]; // Embedding vector
}

export interface VerifiedSentence {
  id: number;
  backendId?: string;
  text: string;
  status: VerificationStatus;
  reasoning?: string;
  citationSourceId?: string;
  citationText?: string;
  confidence?: number;
  isParagraphEnd?: boolean;
  pageNumber?: number;
}

export interface IPODocument {
  id: string;
  title: string;
  content: string;
  sentences: VerifiedSentence[];
  file?: File;
  sections?: Section[];
}
