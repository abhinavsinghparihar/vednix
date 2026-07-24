# Vednix AI — API Reference

Base URL: `http://localhost:8000` · Interactive docs: `/docs` (OpenAPI)

## REST

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | `{status, ollama_available, default_model, assistant}` |
| GET | `/api/models` | `{default, available[]}` — powers the model selector |
| GET | `/api/conversations` | List (pinned first, then recent) |
| POST | `/api/conversations` | Create `{title?, language: auto\|hi\|hinglish\|en}` → 201 |
| GET | `/api/conversations/{id}` | Full chat incl. `messages[]` |
| PATCH | `/api/conversations/{id}` | `{title?, pinned?, folder?, language?, model?}` |
| DELETE | `/api/conversations/{id}` | Cascade-deletes messages → 204 |
| GET | `/api/memory?query=&kind=&limit=` | Search long-term memory |
| POST | `/api/memory` | `{content, kind: note\|preference\|project\|task}` → 201 |
| DELETE | `/api/memory/{id}` | Forget → 204 |
| POST | `/api/uploads` | multipart `files` (≤5/batch, ≤15 MB each) → **201** `[{id, name, kind, mime, size, extracted_chars, created_at}]`. Text-bearing kinds (pdf/docx/xlsx/csv/pptx/txt/code) are extracted eagerly and cached; images are stored for vision routing. |
| GET | `/api/uploads/{id}` | Upload metadata → 404 when unknown |
| POST | `/api/knowledge/documents` | `{title, text}` *or* `{title, uploaded_file_id}` → 201 `{id, title, chunk_count, …}` — chunked (900 chars, 150 overlap) + mirrored into FTS5 |
| GET | `/api/knowledge/documents` | List knowledge documents |
| DELETE | `/api/knowledge/documents/{id}` | Removes doc + chunks + FTS rows → 204 |
| GET | `/api/knowledge/search?q=` | `{query, hits:[{document, chunk_id, snippet («term» marks), score}]}` — FTS5 OR + bm25; LIKE fallback when FTS5 unavailable |

Errors: JSON `{detail}` · 400/404/422 · 429 when the per-IP bucket (120/min) trips.

## WebSocket — `/ws/chat`

### Client → Server
```jsonc
{"type":"user_message","content":"…","conversation_id":null,"model":null,"language":null,
 "temperature":0.7,"attachments":["<upload id>", "…"],"internet":true}
// conversation_id omitted → a new "New chat" is created and announced
// model/language/temperature override the conversation's settings for this message (language persists)
// attachments: ids from POST /api/uploads (≤5). Unknown id → attachment_not_found error, nothing sent.
// Known file kinds inject extracted text into the turn; images route to a vision model automatically
// (notice "🖼 Routed images to …" when auto-switched, clear guidance when no vision model is local).
// internet: runs the LangGraph research agent (plan→search→fetch) over SearXNG and cites the
// results into the streamed answer; orb shows SEARCHING; failures degrade to honest guidance.
// Note: deterministic plugins (time/system/memory) answer before the research/web path — by design.
{"type":"cancel"}    // stop current generation; partial text persists with *(stopped)*
{"type":"ping"}      // → pong
```

### Server → Client
```jsonc
{"type":"conversation_created","conversation_id":"…","title":"New chat"}
{"type":"state_changed","state":"THINKING"}     // IDLE|LISTENING|THINKING|SPEAKING|EXECUTING|SEARCHING|LEARNING|UPDATING — drive the orb
{"type":"message_started","message_id":"…","conversation_id":"…"}
{"type":"token","message_id":"…","content":"…"} // raw LLM/plugin chunks, concatenate
{"type":"message_done","message_id":"…","conversation_id":"…","plugins":["time"],"kb_sources":["Launch Plan"],
 "sources":[{"title":"Vednix Docs","url":"https://…"}],"cancelled":false}
// sources: web citations from an internet turn (empty otherwise)
{"type":"title_updated","conversation_id":"…","title":"…"}  // after first exchange
{"type":"error","code":"busy|rate_limited|too_long|invalid|bad_payload|nothing_to_cancel|attachment_not_found","message":"…"}
{"type":"pong"}
```

### Example (Python)
```python
import asyncio, json, websockets

async def chat(text):
    async with websockets.connect("ws://localhost:8000/ws/chat") as ws:
        await ws.send(json.dumps({"type": "user_message", "content": text}))
        async for raw in ws:
            f = json.loads(raw)
            if f["type"] == "token":
                print(f["content"], end="", flush=True)
            if f["type"] == "message_done":
                break

asyncio.run(chat("नमस्ते! मेरे CPU का हाल बताओ"))   # answers in Hindi, via plugins
```

## Validation & limits

- `content` must be non-empty, ≤ `VEDNIX_MAX_MESSAGE_CHARS` (default 32 000)
- One active generation per connection (`busy` otherwise); ~8 messages / 20 s per connection
- All REST bodies validated by Pydantic schemas (`api/schemas.py`)

## Providers (Phase 5)

`VEDNIX_LLM_PROVIDER=ollama` (default, fully offline) or `openrouter`. Both
providers implement the original dev_ai client interface (`chat`/`chat_stream`/
`is_available`/`list_models`), so everything upstream — engine, vision routing,
model selector — is provider-agnostic. OpenRouter needs
`VEDNIX_OPENROUTER_API_KEY`; `/api/health` reports the active `provider` and the
UI footer labels it.

## Internet research (Phase 5)

`VEDNIX_SEARXNG_URL` points at a SearXNG instance (empty string disables the
feature server-side). Searches run through the LangGraph state machine
(`agents/research/service.py`): plan → parallel search → page fetch → context
build. The final answer is still the single engine streaming pipeline (audit
B3) with citations `[1]…` and a `sources` list on `message_done`.

## Auth (Phase 5)

`VEDNIX_AUTH_TOKEN` set → every `/api/*` and `/ws/chat` requires
`Authorization: Bearer <token>` (WS accepts `?token=` too; `/api/health` stays
open). Empty token = open single-user local mode. `VEDNIX_REDIS_URL` moves
rate-limit state to Redis (falls back to in-process with a warning).
