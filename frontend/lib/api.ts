/**
 * Thin REST client for the Vednix backend (docs/API.md).
 * Every function fails predictably (throws ApiError with status).
 */

import type { Language } from "./ws";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_BASE ?? "ws://localhost:8000/ws/chat";

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

export const api = {
  health: () => request<{ status: string; ollama_available: boolean; default_model: string }>("/api/health"),
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
};
