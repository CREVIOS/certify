import { VerificationStatus, VerifiedSentence, SupportingDocument, Section } from "../types";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

type Project = {
  id: string;
  name: string;
  description?: string;
  background_context?: string;
};

type DocumentResponse = {
  id: string;
  project_id: string;
  original_filename: string;
  filename: string;
  document_type: "main" | "supporting";
  indexed: boolean;
  page_count?: number;
  metadata?: Record<string, any>;
};

type VerificationJob = {
  id: string;
  status: string;
  progress: number;
  total_sentences: number;
  validated_count: number;
  uncertain_count: number;
  incorrect_count: number;
  error_message?: string;
  sentences?: any[];
};

const jsonHeaders = { "Content-Type": "application/json" };

const handle = async (resPromise: Promise<Response>) => {
  try {
    const res = await resPromise;
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    return res.json();
  } catch (err) {
    // Handle network errors (CORS, connection refused, etc.)
    if (err instanceof TypeError) {
      throw new Error('Cannot connect to backend API. Please ensure the backend server is running at ' + API_BASE);
    }
    throw err;
  }
};

export const ensureProject = async (name: string): Promise<Project> => {
  const projects: Project[] = await handle(fetch(`${API_BASE}/projects`));
  if (projects.length > 0) return projects[0];

  return handle(
    fetch(`${API_BASE}/projects`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ name }),
    })
  );
};

export const uploadDocument = async (
  file: File,
  projectId: string,
  documentType: "main" | "supporting"
) => {
  const form = new FormData();
  form.append("file", file);
  form.append("project_id", projectId);
  form.append("document_type", documentType);

  return handle(
    fetch(`${API_BASE}/documents/upload`, {
      method: "POST",
      body: form,
    })
  );
};

export const indexDocument = async (documentId: string) => {
  return handle(
    fetch(`${API_BASE}/documents/${documentId}/index`, {
      method: "POST",
    })
  );
};

export const getDocument = async (documentId: string): Promise<DocumentResponse> => {
  return handle(fetch(`${API_BASE}/documents/${documentId}`));
};

export const pollDocumentIndexed = async (
  documentId: string,
  timeoutMs = 5 * 60 * 1000,
  intervalMs = 2500
): Promise<DocumentResponse> => {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const doc = await getDocument(documentId);
    if (doc.indexed) return doc;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("Document indexing timed out");
};

export const createVerificationJob = async (projectId: string, mainDocumentId: string) =>
  handle(
    fetch(`${API_BASE}/verification/jobs`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ project_id: projectId, main_document_id: mainDocumentId }),
    })
  );

export const startVerificationJob = async (jobId: string) =>
  handle(fetch(`${API_BASE}/verification/jobs/${jobId}/start`, { method: "POST" }));

export const getVerificationJob = async (jobId: string, includeSentences = true): Promise<VerificationJob> =>
  handle(fetch(`${API_BASE}/verification/jobs/${jobId}?include_sentences=${includeSentences}`));

export const pollVerificationJob = async (
  jobId: string,
  onProgress?: (progress: number) => void,
  intervalMs = 4000,
  timeoutMs = 20 * 60 * 1000
): Promise<VerificationJob> => {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const job = await getVerificationJob(jobId, true);
    if (onProgress) onProgress(job.progress || 0);
    if (job.status === "completed" || job.status === "failed" || job.status === "COMPLETED") {
      return job;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("Verification timed out");
};

export const reviewSentence = async (
  sentenceId: string,
  validationResult: "validated" | "uncertain" | "incorrect",
  reviewerNotes?: string
) =>
  handle(
    fetch(`${API_BASE}/verification/sentences/${sentenceId}/review`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify({ validation_result: validationResult, reviewer_notes: reviewerNotes }),
    })
  );

export const suggestSections = async (documentId: string): Promise<{ sections: Section[] }> =>
  handle(fetch(`${API_BASE}/documents/${documentId}/sections/suggest`, { method: "POST" }));

export const updateDocument = async (documentId: string, payload: Record<string, any>) =>
  handle(
    fetch(`${API_BASE}/documents/${documentId}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    })
  );
