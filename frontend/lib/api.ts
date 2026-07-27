/**
 * Thin REST client for the Vednix backend (docs/API.md).
 * Every function fails predictably (throws ApiError with status).
 */

import type { Language } from "./ws";
import { API_BASE, WS_URL } from "./config";
import { ApiError, apiFetch } from "./tokenVault";

export { API_BASE, WS_URL };
export { ApiError };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Since Phase 7 every request can meet a locked API: the vault injects the
  // memory-held access token and silently refreshes on a single 401.
  return apiFetch<T>(path, init);
}

export interface ConversationSummary {
  id: string;
  title: string;
  pinned: boolean;
  folder: string | null;
  language: Language;
  model: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApiMessage {
  id: string;
  role: string;
  content: string;
  plugins: string | null;
  attachments?: { id: string; name: string; kind: string; size: number }[] | null;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ApiMessage[];
}

export interface MemoryItem {
  id: number;
  kind: string;
  content: string;
  created_at: string;
}

export interface UploadedFileMeta {
  id: string;
  name: string;
  kind: string;
  mime: string;
  size: number;
  extracted_chars: number;
  created_at: string;
}

export interface KnowledgeDoc {
  id: string;
  title: string;
  chunk_count: number;
  uploaded_file_id: string | null;
  created_at: string;
}

export interface KnowledgeHit {
  document: string;
  chunk_id: number;
  snippet: string; // FTS5 marks hit terms with «…»
  score: number;
}

export const api = {
  health: () => request<{ status: string; provider?: string; ollama_available: boolean; default_model: string }>("/api/health"),
  models: () => request<{ default: string; available: string[] }>("/api/models"),

  listConversations: () => request<ConversationSummary[]>("/api/conversations"),
  getConversation: (id: string) => request<ConversationDetail>(`/api/conversations/${id}`),
  createConversation: (language: Language = "auto") =>
    request<ConversationSummary>("/api/conversations", { method: "POST", body: JSON.stringify({ language }) }),
  patchConversation: (id: string, fields: Partial<Pick<ConversationSummary, "title" | "pinned" | "language" | "model" | "folder">>) =>
    request<ConversationSummary>(`/api/conversations/${id}`, { method: "PATCH", body: JSON.stringify(fields) }),
  deleteConversation: (id: string) => request<void>(`/api/conversations/${id}`, { method: "DELETE" }),

  listMemories: () => request<MemoryItem[]>("/api/memory"),
  createMemory: (content: string, kind = "note") =>
    request<MemoryItem>("/api/memory", { method: "POST", body: JSON.stringify({ content, kind }) }),
  deleteMemory: (id: number) => request<void>(`/api/memory/${id}`, { method: "DELETE" }),

  uploadFiles: async (files: File[]): Promise<UploadedFileMeta[]> => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const resp = await fetch(`${API_BASE}/api/uploads`, { method: "POST", body: form });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new ApiError(resp.status, body.detail ?? "Upload failed");
    }
    return (await resp.json()) as UploadedFileMeta[];
  },

  listKnowledgeDocs: () => request<KnowledgeDoc[]>("/api/knowledge/documents"),
  searchKnowledge: (q: string) =>
    request<{ query: string; hits: KnowledgeHit[] }>(`/api/knowledge/search?q=${encodeURIComponent(q)}`),
  addKnowledgeDoc: (body: { uploaded_file_id?: string; text?: string; title?: string }) =>
    request<KnowledgeDoc>("/api/knowledge/documents", { method: "POST", body: JSON.stringify(body) }),
  deleteKnowledgeDoc: (id: string) => request<void>(`/api/knowledge/documents/${id}`, { method: "DELETE" }),
};
