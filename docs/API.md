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

Errors: JSON `{detail}` · 400/404/422 · 429 when the per-IP bucket (120/min) trips.

## WebSocket — `/ws/chat`

### Client → Server
```jsonc
{"type":"user_message","content":"…","conversation_id":null,"model":null,"language":null}
// conversation_id omitted → a new "New chat" is created and announced
// model/language override the conversation's settings for this message (language persists)
{"type":"cancel"}    // stop current generation; partial text persists with *(stopped)*
{"type":"ping"}      // → pong
```

### Server → Client
```jsonc
{"type":"conversation_created","conversation_id":"…","title":"New chat"}
{"type":"state_changed","state":"THINKING"}     // IDLE|LISTENING|THINKING|SPEAKING|EXECUTING|SEARCHING|LEARNING|UPDATING — drive the orb
{"type":"message_started","message_id":"…","conversation_id":"…"}
{"type":"token","message_id":"…","content":"…"} // raw LLM/plugin chunks, concatenate
{"type":"message_done","message_id":"…","conversation_id":"…","plugins":["time"],"cancelled":false}
{"type":"title_updated","conversation_id":"…","title":"…"}  // after first exchange
{"type":"error","code":"busy|rate_limited|too_long|invalid|bad_payload|nothing_to_cancel","message":"…"}
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
