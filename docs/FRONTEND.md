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
app/chat/page.tsx                 workspace shell
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
 └─ controls/ControlPanel         model · temperature · language · memory · phases
```

## Routes

`/` — the landing identity. Its centerpiece is the actual 8-state Vednix Orb
performing live (cycling CoreStates every ~1.9s) instead of a stock video —
the same asset the workspace renders from WebSocket `state_changed` frames.
The "ask" capsule bridges a question into `/chat` via a one-shot
sessionStorage hand-off (consumed by Composer on mount).

`/chat` — the workspace shell (sidebar · chat stage · composer · studio panel).

### Font pipeline (root-caused, do not regress)

`@theme` tokens name concrete families (`--font-display: "Outfit"…`). Do NOT
point them at `var(--font-inter)`: @theme variables live on `:root` while
next/font's variable classes land on `<body>` — `var()` substitutes at the
defining element and silently degrades the entire chain to UA serif.

## Design tokens (app/globals.css)

`--color-void/#050505 · charcoal · panel · gold #e3b857 · gold-bright #f4d68a ·
ember #e8843c · cream #f5f0e6` + `.glass`, `.glass-strong`, `.gold-border`,
`.text-gold-gradient`, `.skeleton` utilities; `hljs` gold-on-charcoal theme.

## State (store/chat.ts — Zustand)

REST bootstraps (conversations/models/health); one `WSClient` per app with
typed frames (`state_changed / message_started / token / message_done /
conversation_created / title_updated / error`), auto-reconnect with backoff.
Every right-panel control is real: model → WS payload, temperature → WS payload
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
- **Studio → Knowledge Base:** add document (file picker reuses the upload
  pipeline: pdf/docx/xlsx/csv/pptx/txt/md), list with chunk counts, remove.
  Hits injected into answers surface as `kb_sources` chips on the reply.
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
