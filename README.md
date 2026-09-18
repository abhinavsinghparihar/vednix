# ⚡ VEDNIX AI

**The Next Generation AI Workspace** — private-first, multilingual, streaming-native.

Evolved from the `dev_ai` desktop prototype ([audit](docs/AUDIT_REPORT.md)) into a
web-native platform. Your data never leaves your machine; the **Vednix Engine**
(built on the open Ollama runtime) does the thinking; Vednix answers in
**your language** — Hindi, Hinglish, English, anything.

**Made by Abhinav Singh.**

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Repo foundations, audit, git hygiene | ✅ |
| 1 | **Backend**: FastAPI · async engine · WS streaming · plugins · memory | ✅ **53/53 tests** |
| 2 | **Frontend**: Next.js premium UI · AI Orb · glass studio | ✅ **built + visually verified** |
| 3 | **Voice**: dictation (hi-IN aware) · TTS replies · LISTENING/SPEAKING orb | ✅ built + verified |
| 4 | **Files · vision · knowledge**: uploads (7 kinds) → LLM context, image→vision-model routing, FTS5 knowledge base cited into answers | ✅ **79/79 tests · browser-verified** |
| 5 | **Agents · providers · infra**: LangGraph research agent (SearXNG, cited answers), OpenRouter behind the ♻️ LLM interface, Redis rate-limiting, bearer auth, Docker | ✅ **98/98 tests · browser-verified** |
| 6 | **Multi-agent orchestration**: planner + researcher + critic, live agent-step trace in the UI | ✅ **109/109 tests · browser-verified** |
| 7 | **Accounts & onboarding**: owner/member accounts, JWT sessions, encrypted provider keys, guided setup ceremony | ✅ **131/131 tests · browser-verified** |
| 8 | **NO SIGNUP, NO ENTRY + brand + one-click**: guest/demo retired, owner Admin console, "Vednix Engine" rebrand, Neural-V logo, `start.bat` zero-knowledge launcher | ✅ **132/132 tests · browser-verified** |

## Quick start — the one-click way (recommended)

> Kisi ko Ollama/pip/npm janna **zaroori nahi**. Program khud sab set karta hai.

| OS | Kya karna hai |
|---|---|
| **Windows** | `start.bat` pe **double-click** |
| **macOS / Linux** | `./start.sh` |

One-time prerequisites (sirf ek baar): **Python 3.11+** aur **Node.js 20+** installed ho.
Baaki sab launcher khud karta hai — step by step, batata hua:

```
Step 1/8  Python check              — purana version ho to batayega
Step 2/8  Backend venv + deps       — brain taiyaar (pip, apne aap)
Step 3/8  Node check                — interface ke liye
Step 4/8  Frontend install + build  — pehli baar me thoda time
Step 5/8  Vednix Engine check       — na mile to khud install (winget/brew/script)
Step 6/8  Engine start + model      — qwen2.5:3b (~2GB, ek baar, progress dikhta hai)
Step 7/8  Backend :8000 + Frontend :3000 start
Step 8/8  Heartbeat wait → browser khud khul jata hai
```

Phir browser me — sab kuch bas 3 kadam:

1. **Setup ceremony** → card choose karo: `Free · Private · Unlimited`
   (ya `Cloud` agar apni API key use karni hai).
2. **Owner account banao** — *NO SIGNUP, NO ENTRY*: account ke bina workspace
   khulta hi nahi. Pehla account = **owner** (baaki sab control usi ke paas:
   Settings → **Admin** tab).
3. **Chat shuru.** Engine aapki machine pe, data aapki machine pe — hamesha.

Launcher ko rokna ho to usi window me **Ctrl+C** — sab servers band. Logs:
`logs/backend.log` · `logs/frontend.log` · `logs/engine.log`.

## Manual / developer start

```bash
# 1. Vednix Engine (the brain — runs on your machine)
ollama serve
ollama pull qwen2.5:3b

# 2. Backend terminal
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py                                         # http://127.0.0.1:8000 (docs at /docs)

# 3. Frontend terminal
cd frontend
npm install
npm run build && npm start                             # → http://localhost:3000 ✨
#  (dev ke liye: npm run dev)
```

> Running dev alongside a served production build? Use
> `NEXT_DIST_DIR=.next-dev npm run dev` — otherwise `next dev` rewrites the
> `.next` directory the production server is reading from.

Optional add-ons (all off by default):

```bash
# Internet research agent — self-hosted SearXNG + the Studio "Internet search" toggle
docker run -d -p 8080:8080 searxng/searxng

# Cloud provider alongside the engine (or set it up in Settings → API Keys)
export VEDNIX_LLM_PROVIDER=openrouter VEDNIX_OPENROUTER_API_KEY=sk-or-…

# Protect the API when serving beyond your own machine
export VEDNIX_AUTH_TOKEN=change-me

# One-command full stack in containers
docker compose up --build            # see docs/DOCKER.md
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
cd backend && pip install -r requirements-dev.txt && pytest     # 132 green
```

## What's inside

```
vednix/
├── start.bat / start.sh   one-click launchers (double-click → everything automatic)
├── scripts/
│   ├── launch.py          the 8-step auto-setup brain (stdlib-only Python)
│   └── reset_password.py  machine-local password recovery (no SMTP by design)
├── backend/               FastAPI backend (see docs/ARCHITECTURE.md)
│   ├── ai_engine/         async engine client · single-generator streaming · multilingual prompts
│   ├── agents/            plugin framework + builtins (time, system, memory) — Hindi-aware
│   ├── memory/            async SQLAlchemy: conversations, messages, long-term memory
│   ├── services/          onboarding · providers (failover) · users · admin
│   ├── api/               REST + WebSocket streaming protocol (docs/API.md)
│   └── tests/             132 tests incl. audit-regression proofs
├── frontend/              Next.js workspace (docs/FRONTEND.md)
│   └── components/brand/  Neural-V logo (animated) · tricolor signature
└── docs/                  AUDIT_REPORT · ARCHITECTURE · API · FRONTEND · DOCKER
```

## Docs

- **[docs/AUDIT_REPORT.md](docs/AUDIT_REPORT.md)** — the forensic audit of the original project
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — how Vednix works + design principles
- **[docs/API.md](docs/API.md)** — REST + WebSocket protocol reference
- **[docs/FRONTEND.md](docs/FRONTEND.md)** — the workspace UI, routing law, run modes

## Secure email OTP login

Vednix supports optional email OTP login through an SMTP relay. For Gmail, enable
2-Step Verification, create a Gmail App Password, then copy the SMTP settings
from `backend/.env.example` into `backend/.env`. Vednix stores only a digest of
the OTP, expires codes after ten minutes, limits attempts, and never logs the
code. Google OAuth is not faked: it requires real OAuth credentials and remains
an explicit future configuration step.
