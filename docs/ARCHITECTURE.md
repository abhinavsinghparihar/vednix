# Vednix AI — Architecture

> *"The Next Generation AI Workspace"* — offline-first, multilingual (Hindi / Hinglish / any language), streaming-native.
> Successor to the `dev_ai` desktop prototype (see `docs/AUDIT_REPORT.md` for the forensic audit that shaped this design).

## System overview

```
┌─────────────── Frontend (Phase 2: Next.js) ────────────────┐
│  glass sidebar · streaming chat · controls · AI Orb (WS)   │
└───────────────┬────────────────────────────────────────────┘
                │  REST /api/*  ·  WebSocket /ws/chat
┌───────────────▼─────────────── backend/ (FastAPI, async) ──┐
│ api/           conversations · memories · health/models    │
│     ws_chat.py — receiver/dispatcher loop, cancel-capable  │
│ ai_engine/     engine (ONE async generator) · ollama_client│
│                · events (CoreState pub/sub) · prompts (§8) │
│ agents/        Plugin contract · PluginManager · builtins  │
│ memory/        SQLAlchemy async: Conversation/Message/Item │
│ core/          logging · security (validation) · rate limit│
└───────────────┬────────────────────────────────────────────┘
                │  async httpx (keep-alive)
        ┌───────▼────────┐      ┌──────────────────┐
        │ Ollama (local) │      │ SQLite (WAL)     │
        │ qwen2.5:3b …   │      │ → Postgres-ready │
        └────────────────┘      └──────────────────┘
```

## Design principles (born from the audit)

1. **One pipeline.** `EngineSession.stream_reply()` is the only message path. The
   original had sync + stream copies that disagreed (audit B3/DUP1); there is now
   exactly one — an async generator.
2. **Persistence contract.** User turns always persist; assistant turns persist
   only on success (or partial-on-cancel with a `*(stopped)*` marker); errors
   and offline-notices are streamed to the UI but *never* stored (audit B2).
3. **Per-session state.** `EngineCore` (shared: LLM client, plugins, settings)
   spawns an `EngineSession` per conversation holding its own `StateManager` +
   `EventBus` — two chats can never fight over one global orb state (audit SC5).
4. **Plugin-first routing, all matches.** `PluginManager.find_handlers()` returns
   every claimant by priority; the engine executes all and joins answers
   (audit B4). Plugins are async, fail-soft, and logged (audit B9).
5. **Language contract, explicitly.** `ai_engine/prompts.py` composes persona +
   *CRITICAL LANGUAGE RULE* (mirror the user's language/script) or a forced
   per-conversation directive (`hi` / `hinglish` / `en`), plus remembered facts.
6. **Backpressure + validation at the edge.** Pydantic DTOs, 32k-char cap,
   per-IP REST token bucket, per-connection WS bucket, one active generation per
   connection (audit SEC4, SC6, B5).

## Module map

| Module | Responsibility | From dev_ai |
|---|---|---|
| `ai_engine/events.py` | 8-state CoreState + async bus/state manager | ♻️ ~95% |
| `ai_engine/ollama_client.py` | async httpx Ollama (`chat`/`chat_stream`), error frames raise, health TTL cache | ♻️ interface kept |
| `ai_engine/engine.py` | session pipeline: plugins → LLM, persistence contract, cancellation | 🔧 rewritten |
| `ai_engine/prompts.py` | system prompt: persona, language rule/forced directive, memory facts | 🆕 (audit §8 core fix) |
| `agents/*` | Plugin ABC + manager + time/system_info/memory builtins (Hindi triggers) | ♻️/🆕 |
| `memory/models.py` | Conversation, Message, MemoryItem (WAL, FK, cascade) | 🔧 |
| `memory/service.py` | async CRUD; long-term API `remember/search/all/forget` preserved 1:1 | 🔧 |
| `core/*` | logging, input validation, token-bucket rate limiting | 🆕 (audit: zero logging before) |
| `api/*` | REST DTOs + routers; WS protocol with cancel/title/creation frames | 🆕 |

## Streaming sequence

```
client ─ user_message ─▶ ws_chat ─ validate/rate-limit/resolve-conv
       ◀─ conversation_created (if new)
       ◀─ state_changed THINKING        (or EXECUTING for plugin route)
       ◀─ message_started {message_id}
       ◀─ token × N                     (SPEAKING on first token)
( opt: ─ cancel ─▶ task cancelled ─ partial persisted "*(stopped)*" )
       ◀─ message_done {plugins, cancelled}
       ◀─ state_changed IDLE
       ◀─ title_updated                 (first exchange only, background)
```

## Scaling path (baked in, not bolted on)

`RateLimiter`/`MemoryService` interfaces are process-local today, Redis/Postgres
swappable without caller changes; `OLLAMA_*` and DB URL are env-driven; the LLM
client is a Protocol — OpenRouter provider plugs into the same `chat/chat_stream`
contract (Phase 5) exactly as the original README predicted.
