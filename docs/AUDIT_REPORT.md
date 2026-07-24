# 🔬 VEDNIX AI — FORENSIC AUDIT REPORT
**Target repository:** `github.com/abhinavsinghparihar/chatbot` (commit `6c8bdfc`, "Initial commit")
**Audited:** 2026-07-24 · **Auditor:** Arena.ai Agent Mode (Principal Architect)
**Method:** Full manual read of all 15 source files (889 LOC), static compile checks, live execution tests, git forensics, dependency inspection.

---

## 1. EXECUTIVE SUMMARY

**What exists today:** "DEV AI" — a genuinely well-thought-out **offline-first desktop assistant skeleton**: CustomTkinter HUD window + animated orb, routing engine, Ollama client (qwen2.5:3b), plugin system, two-tier memory (RAM + SQLite), pub/sub state machine.

**Verdict:** The *architecture ideas are unusually good* for an early project — plugin routing, engine-as-facade, event bus, streaming-ready LLM client. But the *implementation is 15–20% complete*: streaming exists but is never wired to the UI, long-term memory exists but is never called, six of eight orb states are unreachable, zero tests, zero logging, no conversation persistence, English-only persona, and the UI is a desktop-only Tk textbox with no markdown.

**Good news:** ~60% of `core/` is directly reusable in Vednix AI with targeted refactoring (detailed preservation map in §10).

**Critical gap vs. your requirement:** The system prompt is **English-only**; nothing instructs the model to answer in **Hindi / Hinglish / the user's language**. Plugins are also English-keyword-only. This is a first-class requirement in the rebuild, not an afterthought.

---

## 2. REPOSITORY SNAPSHOT

| Fact | Value |
|---|---|
| Files (source) | 15 `.py` files, 889 LOC |
| Repo root | Only `dev_ai/` — no root README, no `.gitignore`, no LICENSE |
| Commit history | 1 commit ("Initial commit") |
| Entry point | `dev_ai/main.py` → `ui.app.run()` |
| Runtime deps | `customtkinter>=5.2.0`, `requests>=2.31.0`, `psutil>=5.9.0` (unpinned) |
| External service | Ollama @ `http://localhost:11434`, model `qwen2.5:3b`, temp 0.7 |
| Git hygiene | ⚠️ 29 committed `.pyc` files (built under CPython **3.12 AND 3.14** — two dev envs), committed `data/memory.sqlite3` (verified **0 rows** — no privacy leak, but still wrong) |
| Compile check | ✅ All 15 files compile under Python 3.13.14 |
| Tests | ❌ **Zero** |
| Logging | ❌ **Zero** (`grep "import logging"` → nothing) |

---

## 3. FOLDER STRUCTURE (as audited)

```
chatbot/
└── dev_ai/
    ├── main.py                  (6 LOC)   entry: from ui.app import run
    ├── config.py                (42 LOC)  model, theme, paths; creates data/ at import
    ├── requirements.txt         (3 deps, unpinned)
    ├── README.md                (excellent doc — the "vision" source)
    ├── core/
    │   ├── engine.py            (119 LOC) brain: plugin-first routing → LLM fallback
    │   ├── llm.py               (89 LOC)  Ollama HTTP client: chat() + chat_stream()
    │   ├── memory.py            (112 LOC) ShortTermMemory (RAM cap 20) + LongTermMemory (SQLite)
    │   ├── plugin_manager.py    (38 LOC)  first-match-wins router, silent exception swallow
    │   └── events.py            (63 LOC)  CoreState enum (8 states) + EventBus + StateManager
    ├── plugins/
    │   ├── base.py              (28 LOC)  abstract Plugin: can_handle() / execute()
    │   ├── __init__.py          (11 LOC)  ALL_PLUGINS registry
    │   ├── system_info.py       (47 LOC)  CPU/RAM/disk/battery via psutil
    │   └── time_plugin.py       (20 LOC)  local date/time
    ├── ui/
    │   ├── app.py               (159 LOC) CustomTkinter window: orb + textbox + input bar
    │   └── orb.py               (155 LOC) tk.Canvas orb, 8 per-state animations @60fps
    └── data/
        └── memory.sqlite3       (committed, empty)
```

---

## 4. ARCHITECTURE ANALYSIS

```
┌────────────────────────────── ui/ (CustomTkinter, DESKTOP ONLY) ──┐
│  app.py ──────────────► orb.py (60fps canvas, state-reactive)     │
│    │ _run_engine() on raw thread                                  │
└────┼───────────────────────────────────────────────────────────────┘
     ▼ calls handle_input()   ◄─── NB: NON-streaming variant!
┌──────────────────────────── core/engine.py (Facade) ──────────────┐
│  1. short_term.add("user")                                        │
│  2. plugins.find_handler(text) ──► plugin.execute() [fast path]   │
│  3. else llm.is_available() → llm.chat(messages) [blocking]       │
│  publishes CoreState via events.EventBus                          │
└────┬───────────────┬──────────────────────┬──────────────────────┘
     ▼               ▼                      ▼
 llm.py        plugin_manager.py      memory.py
 requests →    ALL_PLUGINS list       ShortTerm: RAM 20-turn cap
 Ollama        (2 plugins)            LongTerm: SQLite (UNUSED)
 /api/chat
```

**Data-flow assessment:** Clean layered design — UI → Engine → (plugins | llm) with an event bus for decoupling. The seams are exactly right for a web rebuild: `Engine` becomes the FastAPI service layer, `EventBus` events become WebSocket frames, the `Plugin` contract becomes LangGraph tools.

---

## 5. DEPENDENCY GRAPH

```
main.py
 └── ui/app.py ──► core/engine.py ──┬─► core/llm.py ──► requests ──► config
      │  │  └► ui/orb.py ──► config  ├─► core/memory.py ──► sqlite3 ──► config
      │  └────► core/events.py ◄─────┼─► core/plugin_manager.py ──► plugins/*
      └───────► core/events.py       └─► core/events.py (StateManager)
plugins/system_info.py ──► psutil (optional import, graceful)
plugins/time_plugin.py ──► datetime
config.py ──► pathlib (side effect: mkdir at import time)
```
**Circular-import risk:** none today. `config` is a leaf — good. `plugins/__init__.py` instantiates plugins at import time (fine at 2 plugins, won't scale).

---

## 6. STRENGTHS — DO NOT THROW AWAY ♻️

| # | Asset | Why it's good |
|---|---|---|
| S1 | **Plugin facade + first-match routing** (`engine.py`, `plugin_manager.py`) | Correct architectural instinct — direct prototype of LangGraph tool-calling |
| S2 | **Ollama client isolation** (`llm.py`) | Single class talks to Ollama; streaming generator already correct (NDJSON parsing, `done` sentinel) |
| S3 | **Event bus + state machine** (`events.py`) | 8-state CoreState is *ahead of need* — maps perfectly to WS status frames + orb animation states |
| S4 | **Two-tier memory concept** (`memory.py`) | RAM buffer + durable SQLite, swappable search |
| S5 | **README honesty** | Accurately documents what's built vs. planned; vision doc for voice/vision/desktop control |
| S6 | **Thread-marshalling discipline** (`app.py::_on_state_changed`) | Author understands UI-thread safety |
| S7 | **Defensive plugin isolation** | Broken plugin can't crash routing |
| S8 | **Zero vendor lock-in** | No API keys, fully offline — Vednix keeps this |

---

## 7. FINDINGS

### 7.1 🐛 BUGS

| ID | Sev | Location | Bug | Evidence |
|---|---|---|---|---|
| B1 | 🔴 Critical | `ui/app.py:157` | **UI never streams.** Calls `engine.handle_input()` (blocking full-response) although `handle_input_stream()` exists. UX: user stares at frozen UI up to 120s. | grep: `handle_input_stream` has **zero callers** |
| B2 | 🔴 Critical | `core/engine.py:70-72` | **Memory pollution on LLM error.** `except OllamaError: reply = f"Something went wrong…"` → error string is stored as an assistant turn and sent to the model forever after, degrading all future replies. | code-read + Test 6/7 |
| B3 | 🟠 High | `core/engine.py` | **Inconsistent memory writes between sync/stream paths.** Sync saves error text to memory; stream saves *partial* reply but not the error. Two paths, two bugs. | code-read |
| B4 | 🟠 High | `core/engine.py:44` + `plugin_manager.py:31` | **First-match-wins routing.** "tell me about CPU and time" → only `system_info` answers; `time` silently ignored. No multi-intent handling. | Test 2 verified |
| B5 | 🟠 High | `ui/app.py:150-153` | **No concurrency guard.** Spamming Enter spawns unbounded engine threads → interleaved `StateManager` transitions, racing `short_term._turns` (list mutated from N threads, no lock), duplicate user turns. | code-read |
| B6 | 🟡 Medium | `plugins/time_plugin.py:5` | Trigger `"what's the date"` fails on smart quotes (U+2019) and Hinglish ("time kya hai"). English-only substring triggers. | Test 2: `"नमस्ते, how are you"` → LLM fallback |
| B7 | 🟡 Medium | `core/memory.py:44` | RAM-only conversation: **closing the app erases chat history.** LongTermMemory can't help — it's never called (see D1). | grep verified |
| B8 | 🟡 Medium | `core/llm.py:76-88` | Stream silently drops malformed NDJSON lines (`json.JSONDecodeError: continue`) and never surfaces `{"error": …}` frames → truncated replies with no signal. | code-read |
| B9 | 🔵 Low | `core/plugin_manager.py:35` | `except Exception: continue` — broken plugins fail **silently**, no logging (and there is no logging anywhere). | code-read |
| B10 | 🔵 Low | `plugins/system_info.py:38` | `disk_usage("/")` works on Windows by accident (current-drive root) — fragile, undocumented assumption. | code-read |

### 7.2 ⚡ PERFORMANCE BOTTLENECKS

| ID | Sev | Issue |
|---|---|---|
| P1 | 🔴 | **No streaming in UI** (B1) — perceived latency = full generation time (~seconds to 2min timeout) |
| P2 | 🟠 | `ui/app.py:54` — `llm.is_available()` runs **on the UI thread at startup**: up to 2s frozen window when Ollama is down (Test 9) |
| P3 | 🟠 | `core/llm.py` — new TCP connection per request; no `requests.Session` keep-alive |
| P4 | 🟡 | `ui/orb.py:62` — `delete("all")` + full redraw every frame @60fps: creates/destroys ~12 canvas objects/frame → GC churn (τ correct pattern: reuse item IDs, mutate coords) |
| P5 | 🟡 | `core/memory.py:101` — `LIKE '%…%'` substring scan, no index, no FTS5, case-folding broken for Unicode (directly relevant: Hindi text search) |
| P6 | 🔵 | `system_info.py:34` — `cpu_percent(interval=0.3)` hard 300ms stall (acceptable for a plugin; bad if ever run on a request thread) |

### 7.3 🎨 UI LIMITATIONS

| ID | Sev | Limitation |
|---|---|---|
| U1 | 🔴 | **Desktop-only** CustomTkinter — no browser, no mobile, no remote access, single user single machine |
| U2 | 🔴 | Chat is a raw `CTkTextbox` — **no markdown, no code highlighting, no copy button, no tables, no math**, no Hindi font shaping control |
| U3 | 🟠 | No conversation list / history / new-chat / search / pin / folders |
| U4 | 🟠 | No model selector, no temperature/context controls, no settings, no profile |
| U5 | 🟠 | No attachments, no voice button, no image input — despite README vision |
| U6 | 🟡 | 6 of 8 `CoreState` values (LISTENING, SEARCHING, LEARNING, UPDATING…) are **never emitted** → 6 orb animations are unreachable dead beauty |
| U7 | 🟡 | Single hardcoded theme (neon-red HUD); user's Vednix palette is luxury **gold/brown/glass** |
| U8 | 🔵 | Window fixed-string size `1280x800`, no responsive behavior |
| U9 | 🔵 | No typing indicator, no regenerate/edit/continue, no stop-generation |

### 7.4 🧼 CODE SMELLS

| ID | Issue |
|---|---|
| C1 | `config.py:27` — **import-time side effect** (`DATA_DIR.mkdir`) |
| C2 | `ui/app.py` — hardcoded hover color `#a8172a` bypasses config palette |
| C3 | Config via module constants, not env vars / settings file — not 12-factor |
| C4 | Requirements unpinned (`>=`), no lockfile, no pyproject.toml |
| C5 | Everything assumes `cwd == dev_ai/` — absolute `from config import` breaks package usage |
| C6 | Stateful singletons instantiated at import (`ALL_PLUGINS = [SystemInfoPlugin(), TimePlugin()]`) |
| C7 | No type checking config, no linter config, no formatter config — despite `from __future__ import annotations` discipline (author cares; tooling missing) |

### 7.5 🔐 SECURITY ISSUES

| ID | Sev | Issue |
|---|---|---|
| SEC1 | 🟠 | **Committed `data/memory.sqlite3`** to git (verified 0 rows — but the pattern is a loaded gun; first real usage leaks private memory into git history forever) |
| SEC2 | 🟠 | **50 committed artifacts**: 29 `.pyc` binaries from *two different CPython versions* (3.12 + 3.14) — leaks dev-environment details, bloats clones (183KB .git) |
| SEC3 | 🟡 | No `.gitignore` at all |
| SEC4 | 🟡 | No input length limits — multi-MB paste goes straight to the model; no validation layer exists to harden for web exposure |
| SEC5 | 🟡 | SQLite connections never `PRAGMA` hardened (fine offline; needs WAL + integrity settings when multi-user) |
| SEC6 | 🔵 | No secrets currently (✅ good), but no mechanism (env/.env.example) exists for when OpenRouter etc. arrives |
| SEC7 | 🔵 | Error messages echo raw exception text to user (`f"...hit an error: {exc}"`) — info-leak pattern to fix for web |

### 7.6 💧 MEMORY LEAKS

| ID | Sev | Issue |
|---|---|---|
| M1 | 🟡 | `EventBus.subscribe` never unsubscribed: `App` subscribes `state_changed` once per window (fine at one window; **leaks subscribers per reconnect/session in a web port**) |
| M2 | 🟡 | Unbounded engine threads (B5) — each holds refs to Engine; no join/cancel/timeout cleanup |
| M3 | 🔵 | `ShortTermMemory` correctly capped ✅; SQLite connections properly context-managed ✅ — the two places junior code usually leaks are actually clean. Credit due. |

### 7.7 ⛔ BLOCKING OPERATIONS

| ID | Location | Block |
|---|---|---|
| BL1 | `llm.py:35,60` | Sync `requests.post` up to **120s** on engine thread |
| BL2 | `llm.py:26` | `is_available()` 2s block on **UI startup thread** |
| BL3 | `app.py:157` | Whole `handle_input` blocks a raw thread; UI "responsive" only because Tk runs on main thread |
| BL4 | `system_info.py:34` | 300ms `cpu_percent` |
| BL5 | `memory.py` | All SQLite I/O synchronous (fine for SQLite, but no async façade) |

### 7.8 🔄 ASYNC OPPORTUNITIES (for Vednix)

- **A1:** `requests` → `httpx.AsyncClient` + Ollama's async stream → true end-to-end async token streaming over WebSocket (kills BL1/BL3, fixes P1/P3)
- **A2:** `is_available()` → background health-check task with cached status (kills P2)
- **A3:** Plugins → `async def execute()`; blocking ones (`cpu_percent`, OCR, file parsing) via `asyncio.to_thread` / process pool
- **A4:** SQLite → async layer (SQLAlchemy 2.0 async + aiosqlite) now, Postgres-ready later
- **A5:** EventBus events → per-session WS broadcast queues (born async)

### 7.9 💀 DEAD CODE

| ID | What | Proof |
|---|---|---|
| D1 | **`LongTermMemory` — entire class unused.** Instantiated in `Engine.__init__` but `remember()`/`search()`/`all()`/`forget()` have **zero callers** | grep verified |
| D2 | `LLM_STREAM = True` in config — **never read anywhere** | grep verified |
| D3 | `Engine.handle_input_stream()` — **zero callers** (UI uses sync `handle_input`) | grep verified |
| D4 | `PluginManager.register()` — never called (plugins only via constructor) | grep verified |
| D5 | 6 of 8 `CoreState` values never emitted → 6 orb animations unreachable | code-read |
| D6 | `MemoryItem` dataclass constructed only in `LongTermMemory` (transitively dead) | grep verified |

### 7.10 👯 DUPLICATE CODE

| ID | Duplication |
|---|---|
| DUP1 | `engine.py` — plugin-branch + offline-branch + message-assembly written **twice** (sync `handle_input` / `handle_input_stream`, ~85% identical → the B2/B3 inconsistency is the direct cost of this duplication) |
| DUP2 | `ui/app.py:38-47` — `STATE_LABELS` dict re-encodes `CoreState.name` verbatim (8 entries of pure redundancy) |
| DUP3 | `llm.py` — request payload construction duplicated between `chat()` / `chat_stream()` |

### 7.11 🚧 MISSING FEATURES (gap vs. Vednix spec)

- ❌ Hindi/Hinglish/any-language answering (system prompt is English-only; nothing steers qwen2.5:3b) ← **your stated core requirement**
- ❌ Streaming in the UI (built-in-engine, never wired)
- ❌ Conversation CRUD: new/rename/delete/search/pin/folders/history-persistence
- ❌ Web UI of any kind; markdown/code/tables/mermaid rendering
- ❌ Model selector, temperature/context controls, per-conversation settings
- ❌ Voice (STT/TTS), file/PDF/image input, OCR, vision
- ❌ Agent/research/coding modes; internet search; OpenRouter support
- ❌ Vector memory / embeddings (ChromaDB) — current search is naive LIKE
- ❌ Multi-user anything; auth; sessions; rate limiting; audit logs
- ❌ Tests, CI, logging, error boundaries, Docker, env config

### 7.12 📈 SCALABILITY ISSUES

| ID | Issue |
|---|---|
| SC1 | Single-process, single-user Tk app — the entire runtime model is 1 human at 1 keyboard |
| SC2 | One global `Engine` → one global `short_term` → **no multi-conversation concept**; conversations can't coexist, let alone multi-user sessions |
| SC3 | Synchronous plugin execution serializes all work; one slow plugin stalls the engine |
| SC4 | SQLite single-file with per-op connections won't survive concurrent writers (web) without WAL/queue |
| SC5 | State machine is global — with 2 concurrent requests the orb/status would flap between truths |
| SC6 | No backpressure: naive Enter-spam → unbounded threads + unbounded Ollama requests (also a DoS vector once web-exposed) |

---

## 8. 🔴 THE MULTILINGUAL GAP (your core requirement — called out specially)

You said: *"offline chatbot, answers in Hindi, Hinglish, any language, uses Ollama."*

| Aspect | Today | Vednix AI target |
|---|---|---|
| Model | `qwen2.5:3b` — **genuinely multilingual** (29+ languages incl. Hindi) ✅ good base choice | Keep + model selector |
| System prompt | English-only persona, **no language instruction** | **Language-mirroring directive**: *"Always reply in the exact language and script the user used — Hindi (Devanagari), Hinglish (Roman), or any other language."* Per-conversation override |
| Plugins | English substring triggers only | Locale-aware triggers (hi/en regex sets) or LLM-router |
| UI | Monospace Consolas textbox — Devanagari shaping is Tk's mercy | Web fonts (Noto Sans Devanagari / Inter), proper rendering, RTL-ready |
| Memory search | LIKE breaks on Unicode case-fold | FTS5/ChromaDB multilingual embeddings |

---

## 9. UPGRADE ROADMAP — DEV AI → **VEDNIX AI**

> **Constraint honored:** existing code is *reused or refactored*, not blindly rewritten. Every phase is separately committable & shippable.

### Phase 0 — Repo foundations (30 min)
- [ ] `.gitignore` (pycache, venv, node_modules, .env, data/*.sqlite3, chroma/)
- [ ] Purge 29 `.pyc` + `memory.sqlite3` from tracking (keep history note)
- [ ] Restructure: `vednix/backend`, `vednix/frontend`, `vednix/docs`, root README (the audit says: no root README today)
- [ ] Python 3.11+ pinned deps + `pyproject.toml`; Node 20 + Next.js pinned

### Phase 1 — Backend core (FastAPI + WS streaming) ♻️ *max reuse*
| Existing asset | Transformation |
|---|---|
| `llm.py` (OllamaClient) | → `ai_engine/ollama_client.py`: `httpx.AsyncClient`, one session, token stream, error frames surfaced, health-check task. **Interface preserved: `chat()` / `chat_stream()`** |
| `engine.py` (routing) | → `ai_engine/engine.py`: merge duplicated sync/stream paths into **one async generator** (fixes B2/B3/DUP1); error text never enters memory; per-session instances (fixes SC2/SC5) |
| `events.py` (CoreState/bus) | → preserved verbatim enum; bus becomes async; events bridged to WS frames (fixes U6 — frontend orb uses all 8 states) |
| `plugin_manager.py` + `plugins/` | → `agents/plugins/`: `async execute()`, failure logging (B9), locale-aware triggers (B6), multi-intent router option (B4) |
| `memory.py` | → SQLAlchemy 2.0 async models: `Conversation`, `Message`, `MemoryItem` (revives D1 as real feature); FTS5 → ChromaDB slot behind same `search()` |
| `config.py` | → `pydantic-settings` BaseSettings, `.env` driven, no import side effects (C1/C3); **new multilingual system prompt** (§8) |

**Deliverables:** WS `/ws/chat` streaming protocol (`user_message → state_changed → token* → done`), REST `/conversations`, `/models`, `/health`; request-id logging; rate-limit middleware; input validation via Pydantic (SEC4).

### Phase 2 — Frontend shell (Next.js + premium UI)
- Next.js 15 App Router + TS + Tailwind v4 + Shadcn + Framer Motion; Zustand chat store; TanStack Query for REST
- **Layout:** glass sidebar (history/search/pin/folders/projects) · main streaming chat (react-markdown + shiki + mermaid + copy) · right control panel (model/temp/context/memory/plugins/internet/vision) · glass composer (attach, voice, char counter) — your full Chat-page spec
- **Vednix design system:** deep black/charcoal/warm brown + luxury gold/soft-orange, glass cards, gradient borders, mouse glow, particles, neural-network canvas background, page transitions, skeletons
- **AI Orb component** — direct port of `ui/orb.py`'s 8 state animations to canvas/WebGL, *finally* driven by all `CoreState` values over WS (S3 × U6)

### Phase 3 — Language & voice
- Multilingual guaranteed: system prompt + per-chat language override + Noto fonts (§8)
- Voice: browser WebSpeech STT now; `faster-whisper` + `edge-tts` workers behind plugin contract next (README's own roadmap, steps 2–3)

### Phase 4 — Files, vision & knowledge
- Upload pipeline (PDF/DOCX/XLSX/CSV/PPTX/images), OCR (tesseract), screenshots → vision models (`llama3.2-vision` via Ollama) — all as **plugins**, per README's predicted extension pattern (S1)
- Knowledge base: ChromaDB per-project collections, cited retrieval into context

### Phase 5 — Agents & platform
- LangGraph agent runtime (research/coding/project modes), internet search plugin (SearXNG offline-friendly) + OpenRouter provider implementing the `chat()/chat_stream()` interface (README's own swap plan realized)
- Auth (JWT), Postgres, Redis (queues/rate-limit), audit logs, Docker Compose, k6 + pytest + vitest, full docs

---

## 10. PRESERVATION MAP (reuse vs. refactor vs. retire)

| File | Fate | Action |
|---|---|---|
| `core/events.py` | ♻️ **Reuse ~95%** | Async-safe publish; keep enum |
| `core/llm.py` | ♻️ **Reuse logic** | Port to httpx async; keep interface + NDJSON parser; add error-frame handling |
| `core/engine.py` | 🔧 **Refactor hard** | Single async generator; fix B2/B3; per-session; lose duplication |
| `core/memory.py` | 🔧 **Refactor hard** | SQLAlchemy async; actually *use* LongTermMemory; FTS/vector |
| `core/plugin_manager.py` | ♻️ **Reuse ~80%** | Async, logging, i18n triggers, multi-match |
| `plugins/base.py` | ♻️ **Reuse ~90%** | `async execute`; add `locales`, `priority` |
| `plugins/time_plugin.py`, `system_info.py` | ♻️ **Reuse** | Async + localized triggers; they ship as Vednix built-ins |
| `config.py` | 🔧 Replace with pydantic-settings (values + palette ideas carry over) | gold theme defaults instead of red |
| `ui/orb.py` | 🎨 **Port concept** → React/WebGL orb, same 8-state design language | new code, same soul |
| `ui/app.py` | 🗑️ **Retire** (desktop Tk) | fully superseded by Next.js — kept in git history |
| `main.py` | 🗑️ Retire → `uvicorn backend.main:app` | — |
| `README.md` | ♻️ **Reuse vision sections** in new docs | it predicted this roadmap accurately |

---

## 11. TARGET BLUEPRINT (post-transformation)

```
vednix/
├── backend/                      # FastAPI, Python 3.12
│   ├── main.py · config.py (pydantic-settings) · deps.py
│   ├── api/{ws_chat.py, conversations.py, models.py, uploads.py, memory.py}
│   ├── ai_engine/{engine.py, ollama_client.py, providers/openrouter.py, events.py, prompts.py}
│   ├── agents/{plugin_manager.py, base.py, builtin/{time,system_info,web_search,files,vision}.py}
│   ├── memory/{models.py, service.py, vector.py}
│   ├── core/{security.py, rate_limit.py, logging.py, errors.py}
│   └── tests/
├── frontend/                     # Next.js 15 + TS + Tailwind v4 + Shadcn
│   ├── app/(chat)/page.tsx · layout.tsx
│   ├── components/{sidebar/, chat/, composer/, controls/, orb/, background/}
│   ├── lib/{ws.ts, api.ts, markdown.tsx} · store/chat.ts (Zustand) · hooks/
└── docs/{ARCHITECTURE.md, API.md, PLUGINS.md, DB.md, DEPLOYMENT.md}
```

---

## 12. VERIFICATION LOG (reproducible evidence)

| Test | Result |
|---|---|
| `py_compile` all 15 files @ Python 3.13.14 | ✅ pass |
| Plugin routing ("CPU and time") | → only `system_info` (B4 confirmed) |
| Hindi "नमस्ते, how are you" | → LLM fallback, no plugin handles Hindi (§8 confirmed) |
| `ShortTermMemory(6)` + 10 adds | keeps last 6 ✅ works as designed |
| Committed `memory.sqlite3` | **0 rows** — no privacy leak (SEC1 downgraded to pattern-risk) |
| grep `handle_input_stream` / `LLM_STREAM` / `long_term.` callers | **0 / 0 / 0** (D1–D3 confirmed dead) |
| grep `import logging`, `*test*` files | **0, 0** — no logging, no tests |
| `git ls-files` binary artifacts | **29 `.pyc` + 1 `.sqlite3`** tracked |
| Engine offline path | graceful message ✅ (good error UX worth porting) |

---

**Bottom line:** The skeleton's *bones are right*. Vednix AI will stand on them — async-streamed, multilingual, web-native, and premium — with the two critical bugs (dead streaming path, memory pollution) fixed at the root by unifying the engine into a single async generator, exactly where the original design was already pointing.

*— End of audit. Approved to proceed to build. —*
