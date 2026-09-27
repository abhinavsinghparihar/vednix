# Vednix architecture

Vednix is a web workspace backed by FastAPI. The browser retains the current Zustand chat state and connects over the existing WebSocket; the backend owns authentication, conversation persistence, encrypted provider credentials, live model validation, file storage, and provider routing.

```text
Next.js workspace (Vercel or local)
  ├─ REST: auth, conversation history, files, settings, live model checks
  └─ WebSocket /ws/chat: one existing token-streaming chat transport
        │
FastAPI backend (Render or local)
  ├─ auth/session + explicit credentialed CORS
  ├─ EngineCore → ResilientLLM
  │    ├─ Gemini adapter → official models.list + compatible chat generation
  │    └─ Groq adapter   → official /models + compatible chat completions
  ├─ task-specific capability probes, model cache, pre-token failover
  ├─ SQLAlchemy: conversations, users, provider keys, validated model metadata
  ├─ encrypted key vault + filesystem upload store
  └─ optional LangGraph research backed by configured SearXNG
```

## Provider boundary

`backend/ai_engine/cloud_client.py` holds provider adapters and their HTTP handling. `model_catalog.py` normalizes model capabilities; `provider_error.py` converts upstream failures to safe, classified errors. `services/providers.py` is the boundary for provider metadata, encrypted keys, official model discovery, task probes, and cached validation. `services/resilient_llm.py` selects only verified and enabled providers.

Provider setup metadata is a small fixed list containing only Gemini and Groq endpoints/labels. Model identifiers are fetched live. Candidate listings are not equivalent to verification: text, vision, and tool capability flags require successful operation-specific checks. Unsupported tasks remain unavailable unless a real check is implemented. Model data and API keys stay server-side.

Automatic chat selects a compatible verified model from the saved priority list. It may fail over to another compatible provider only before any response token is emitted. User-selected provider/model requests remain strict. The router does not fan a request out to every configured model.

## Chat and state

`EngineCore` enriches turns with stored history, selected attachments, memory, and optional knowledge/research context. `api/ws_chat.py` is the single streaming transport. The frontend's Zustand store owns the active conversation/messages, pending attachments, provider/model choices, and WebSocket status. Opening or dismissing the mobile Studio drawer does not reset the chat store.

## Persistence and security

The default database is SQLite; deployment can set a supported SQLAlchemy async database URL. Uploaded files are stored under the configured upload directory. Provider API keys are encrypted at rest with a backend-held secret; public provider responses expose only a key hint and verification/status information. CORS and WebSocket origins use exact allowlists, including the production frontend and local development origins. Do not place provider secrets in frontend configuration or browser storage.

## Main code areas

- `frontend/app/` — landing, authentication, onboarding, workspace, settings, and profile routes.
- `frontend/components/` — workspace, chat, composer, Studio, onboarding, and design system.
- `frontend/store/chat.ts` — conversation/chat state and provider/model selection.
- `backend/api/` — REST routes and the WebSocket endpoint.
- `backend/ai_engine/` — adapters, model capabilities, errors, and engine.
- `backend/services/providers.py` — encrypted provider setup and model validation.
- `backend/services/resilient_llm.py` — provider/model routing and failover.
- `backend/memory/` — persistence models and services.
