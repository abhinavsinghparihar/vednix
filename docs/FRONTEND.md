# Vednix AI — Frontend

Next.js 15 (App Router) · TypeScript strict · Tailwind CSS v4 · Zustand · Framer Motion
→ production build: `npm run build` · dev: `npm run dev` (http://localhost:3000)

## Composition

```
app/page.tsx                      landing identity — "The Living Core" (server comp)
 ├─ landing/LandingNav            floating glass pill nav · staggered mobile overlay
 ├─ landing/Hero                  manifesto · ask-capsule (→ /chat prefilled) · stats
 ├─ landing/OrbStage              live 8-state Orb cycle · orbit rings · glass badges
 ├─ landing/Capabilities          6 honest shipped-feature cards (mono engine tags)
 ├─ landing/EnterSection          real 3-command setup card (copy button) · CTA
 └─ landing/LandingFooter         wordmark · promises · ©
app/layout.tsx                    theme bootstrap (blocking <head> script)
 │                                · BootGate wrap (session intro, once/session)
app/chat/page.tsx                 workspace OS — Rail + 4 views (AnimatePresence)
 ├─ brand/BootGate                Orb ignition · wordmark · framed signature
 │                                · hairline progress · curtain lift · skip
 ├─ brand/ThemeToggle             sun⇄moon rotate-fade swap (rail + landing nav)
 ├─ workspace/Rail                62px floating glass-liquid dock · view switch
 │                                · theme toggle · vertical creator signature
 ├─ workspace/DashboardView       bilingual greeting · ask capsule · 4 real
 │                                stat cards · Continue list · live core card
 ├─ workspace/KnowledgeView       KB docs add/search(FTS5 «» snippets)/delete
 ├─ workspace/MemoryView          long-term memory add/list/delete
 ├─ background/NeuralBackground   particle synapse canvas (paused when tab hidden)
 ├─ background/MouseGlow          cursor-trailing gold halo (lerped, rAF)
 ├─ sidebar/Sidebar               brand · search · pin/rename/delete · health footer
 ├─ Topbar                        title inline-rename · CoreState label + mini orb
 ├─ chat/ChatView                 streaming list (useDeferredValue, bottom-pinning)
 ├─ chat/EmptyState               hero orb + bilingual first-impression + chips
 ├─ chat/MessageBubble            user/assistant/system rows · copy · regenerate
 ├─ chat/Markdown                 GFM · tables · hljs gold theme · copy header
 │                                · Mermaid (lazy import — 500KB opt-in only)
 ├─ composer/Composer             autogrow glass input · Enter/Shift+Enter
 │                                · send⇄stop morph · 32k char counter
 └─ controls/ControlPanel         model · temperature · language · voice · agents
```

## Routes

`/` — the landing identity. Its centerpiece is the actual 8-state Vednix Orb
performing live (cycling CoreStates every ~1.9s) instead of a stock video —
the same asset the workspace renders from WebSocket `state_changed` frames.
The "ask" capsule bridges a question into `/chat` via a one-shot
sessionStorage hand-off (consumed by Composer on mount).

`/chat` — the workspace OS. A floating glass **Rail** (left edge) switches
four views with `AnimatePresence mode="wait"` transitions:
**dash** (default — greeting, real stats, ask capsule, continue, live core),
**chat** (sidebar · stage · composer · studio panel), **knowledge** (KB with
FTS5 search), **memory** (long-term store). The dashboard ask capsule reuses
the same sessionStorage hand-off as the landing one. A pending hand-off is
treated as explicit intent to compose: the landing capsule calls
`setView("chat")` before routing (client-side nav keeps the store), and the
`/chat` mount guard forces `view: "chat"` whenever `vednix.ask` is still
unconsumed (hard refresh / direct arrival), so the question always lands in
the Composer.

### Dual theme — Obsidian (dark, default) & Ivory (light)

Tailwind v4 resolves `@theme` token **variables** at runtime, so
`html[data-theme="light"]` simply redefines the palette
(`--color-void: #f4f0e6` paper · `panel: #ffffff` · bronze `gold: #a97e2c` ·
ink `cream: #221b0e` · `muted: #6e6350` · `faint: #9a8d74`) and every glass /
gradient / skeleton utility re-skins with **zero component changes**. Light
overrides live in one block in `globals.css`; code blocks keep a dark
background in both modes (intentional contrast anchor). `lib/theme.ts` +
a blocking inline `<head>` script stamp `data-theme` before first paint
(localStorage `vednix.theme` → `prefers-color-scheme` → dark), so there is
no theme flash. `brand/ThemeToggle.tsx` switches with a sun⇄moon rotate-fade
and sits in the Rail and the landing nav (desktop + mobile).

### Session boot — "the site opens cool"

`brand/BootGate.tsx` wraps the app in `layout.tsx` and plays **once per
session** (`sessionStorage vednix.booted`): the Orb ignites in LISTENING, the
wordmark springs in, the framed creator signature fades, a gold hairline
progress bar sweeps, then the whole curtain slides up (`.75s` EASE_CURVE).
Click anywhere to skip; `prefers-reduced-motion` bypasses it entirely. Probes
and e2e can pre-set the flag via `add_init_script` to skip the intro.

### Creator signature (premium branding)

`lib/brand.ts` is the single source of truth: `BRAND_NAME` (always primary)
+ `CREATOR_NAME` → `CREATOR_SIGNATURE` ("Made by Abhinav Singh").
`components/brand/Signature.tsx` renders it in exactly one style — mono
micro-caps, faint ink, optional gold-hairline `framed` variant — so the
signature never drifts. Placements: global loading splash
(`app/loading.tsx`), session boot curtain, landing hero edge anchor, landing
footer, landing mobile menu, **Rail** (vertical `writing-mode: vertical-rl`),
workspace sidebar footer, EmptyState close, dashboard core card, and the
Studio panel's About block. The backend mirrors it via `GET /api/health`
(`creator`, from `VEDNIX_CREATOR_NAME`). Never larger, never louder.

### Font pipeline (root-caused, do not regress)

`@theme` tokens name concrete families (`--font-display: "Outfit"…`). Do NOT
point them at `var(--font-inter)`: @theme variables live on `:root` while
next/font's variable classes land on `<body>` — `var()` substitutes at the
defining element and silently degrades the entire chain to UA serif.

## Design tokens (app/globals.css)

Dark (Obsidian, default): `--color-void/#050505 · charcoal · panel ·
gold #e3b857 · gold-bright #f4d68a · ember #e8843c · cream #f5f0e6`.
Light (Ivory): see *Dual theme* above — one block redefines the same tokens
under `html[data-theme="light"]`. Shared utilities: `.glass`, `.glass-strong`,
`.glass-liquid` (white-gradient liquid glass, themed per mode), `.gold-border`,
`.text-gold-gradient`, `.skeleton`; `hljs` gold-on-charcoal theme.

## State (store/chat.ts — Zustand)

REST bootstraps (conversations/models/health); one `WSClient` per app with
typed frames (`state_changed / message_started / token / message_done /
conversation_created / title_updated / error`), auto-reconnect with backoff.
View routing is a store concern: `view: WorkspaceView`
(`"dash" | "chat" | "knowledge" | "memory"`, default `"dash"`) via
`setView()`; `newChat()` / `selectConversation()` force `view: "chat"` so
clicking a conversation always lands on the stage. Every right-panel control
is real: model → WS payload, temperature → WS payload
(backend-regression-tested), language → PATCH + system-prompt directive.

## Voice (Phase 3)

- **STT** `hooks/useSpeechRecognition.ts`: WebSpeech wrapper (feature-detected,
  Chrome/Edge recommended). Mic locale follows conversation language — `hi-IN`
  handles हिंदी + Hinglish in one stream. Interim results render live in the
  composer; permission-denied and unsupported states are explicit.
- **TTS** `lib/tts.ts` (singleton over `speechSynthesis`): OS voices, fully
  offline; voice picker prefers neural/natural local voices; per-message speak
  button + "Speak replies" auto-TTS (Studio panel) + speed slider + test voice.
  `lib/speechText.ts` sanitizes markdown (code → "(code snippet)", tables
  flattened) and sniffs Devanagari to pick hi-IN vs en-US per message.
- **Orb arbitration** `store/chat.ts → useDisplayCoreState()`: local
  `voiceState` (listening/speaking) overrides server `CoreState` — LISTENING
  and SPEAKING animations, unreachable since the desktop app, now fire.

## Notable disciplines

- **Bundle:** `lucide-react`/`framer-motion` optimizePackageImports; Mermaid +
  highlight language packs load on demand only.
- **Perf:** canvases share rAF, DPR-capped at 2, hidden-tab pause, particle
  count scaled to viewport; message bubbles are `memo`'d; streaming uses
  `useDeferredValue`.
- **A11y:** reduced-motion respected everywhere; aria labels on every control;
  keyboard-first composer.
- **Honesty:** internet/agents toggles remain visibly disabled with phase
  badges — no fake features.

## Phase 4 — files, vision & knowledge (shipped)

- **Composer attach is real:** `input[type=file]` → immediate `POST /api/uploads`
  → draft chips (name · human size · remove) above the input; send passes the
  uploaded ids in `WSUserMessage.attachments`; sent chips render on the user
  bubble from the persisted `attachments` JSON (survives reload).
- **Drag & drop:** a page-level drop overlay accepts any supported file.
- **Vision honesty:** images attach fine; the backend auto-routes to an
  installed vision model with a `🖼 Routed images to …` notice, or replies with
  an exact `ollama pull …` fix when none is local.
- **Knowledge Base is a first-class view** (Rail → knowledge, promoted out of
  the Studio panel): add document (file picker reuses the upload pipeline:
  pdf/docx/xlsx/csv/pptx/txt/md), list with chunk counts, remove, and
  **FTS5 search** (`GET /api/knowledge/search`) rendering `«»`-marked
  snippets. Hits injected into answers surface as `kb_sources` chips on the
  reply.
- **Memory is a first-class view** (Rail → memory): add/list/delete
  long-term memories; the dashboard stat card shows the live count.
- **Studio → Voice (Phase 3):** speak-replies toggle + speed slider + test.

## Phase 6 — multi-agent mode (shipped)

- **Multi-agent switch is real** in Studio → Capabilities (was the last Phase
  badge — every toggle in the product is now functional). It implies web
  research even when the Internet switch is off; the backend routes
  `multi_agent` to the deep LangGraph loop.
- **Live agent trace:** `agent_step` WS frames stack as step chips (plan →
  search → fetch → critique → refine → build) above the reply; the latest chip
  pulses while the agents work, the full trace stays on the message.
- Sources continue to render as gold citation links under the reply.
