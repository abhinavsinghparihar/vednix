/**
 * Thin REST client for the Vednix backend (docs/API.md).
 * Every function fails predictably (throws ApiError with status).
 */

import type { Language } from "./ws";

// 127.0.0.1 over bare "localhost": on IPv6-first systems "localhost" resolves
// to ::1 while the backend binds 127.0.0.1 — fetch() then fails hard instead of
// falling back (observed live). Still overridable via NEXT_PUBLIC_API_BASE.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_BASE ?? "ws://127.0.0.1:8000/ws/chat";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    let message = resp.statusText;
    try {
      const body = await resp.json();
      message = body.detail ?? message;
    } catch { /* non-JSON error body */ }
    throw new ApiError(resp.status, message);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
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
  addKnowledgeDoc: (body: { uploaded_file_id?: string; text?: string; title?: string }) =>
    request<KnowledgeDoc>("/api/knowledge/documents", { method: "POST", body: JSON.stringify(body) }),
  deleteKnowledgeDoc: (id: string) => request<void>(`/api/knowledge/documents/${id}`, { method: "DELETE" }),
};
