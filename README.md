# ⚡ VEDNIX AI

**The Next Generation AI Workspace** — offline-first, multilingual, streaming-native.

Evolved from the `dev_ai` desktop prototype ([audit](docs/AUDIT_REPORT.md)) into a
web-native platform. Your data never leaves your machine; Ollama does the thinking;
Vednix answers in **your language** — Hindi, Hinglish, English, anything.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Repo foundations, audit, git hygiene | ✅ |
| 1 | **Backend**: FastAPI · async Ollama · WS streaming · plugins · memory | ✅ **53/53 tests** |
| 2 | **Frontend**: Next.js premium UI · AI Orb · glass studio | ✅ **built + visually verified** |
| 3 | **Voice**: dictation (hi-IN aware) · TTS replies · LISTENING/SPEAKING orb | ✅ built + verified |
| 4 | **Files · vision · knowledge**: uploads (7 kinds) → LLM context, image→vision-model routing, FTS5 knowledge base cited into answers | ✅ **79/79 tests · browser-verified** |
| 5 | Agents, OpenRouter, Postgres, Redis, Docker | planned |

## Quick start

```bash
# 1. Ollama (the brain — fully local)
ollama serve
ollama pull qwen2.5:3b

# 2. Backend terminal
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # optional; defaults just work
python main.py                                         # http://127.0.0.1:8000 (docs at /docs)

# 3. Frontend terminal
cd frontend
npm install
cp .env.local.example .env.local                       # optional; defaults just work
npm run dev                                            # → http://localhost:3000 ✨
```

Try it (Hindi works out of the box):
```bash
cd backend && python - <<'EOF'
import asyncio, json, websockets
async def go():
    async with websockets.connect("ws://localhost:8000/ws/chat") as ws:
        await ws.send(json.dumps({"type":"user_message","content":"अभी समय क्या है?"}))
        async for raw in ws:
            f = json.loads(raw)
            if f["type"]=="token": print(f["content"], end="")
            if f["type"]=="message_done": break
asyncio.run(go())
EOF
```

Run the tests:
```bash
cd backend && pip install -r requirements-dev.txt && pytest
```

## What's inside

```
vednix/
├── backend/          FastAPI backend (see docs/ARCHITECTURE.md)
│   ├── ai_engine/    async Ollama client · single-generator engine · multilingual prompts
│   ├── agents/       plugin framework + builtins (time, system, memory) — Hindi-aware
│   ├── memory/       async SQLAlchemy: conversations, messages, long-term memory
│   ├── api/          REST + WebSocket streaming protocol (docs/API.md)
│   └── tests/        52 tests incl. audit-regression proofs
├── docs/             AUDIT_REPORT · ARCHITECTURE · API
└── (frontend/)       Next.js workspace — Phase 2 (next)
```

## Docs

- **[docs/AUDIT_REPORT.md](docs/AUDIT_REPORT.md)** — the forensic audit of the original project
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — how Vednix works + design principles
- **[docs/API.md](docs/API.md)** — REST + WebSocket protocol reference
