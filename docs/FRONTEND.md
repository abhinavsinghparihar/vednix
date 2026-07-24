# Vednix AI — Frontend

Next.js 15 (App Router) · TypeScript strict · Tailwind CSS v4 · Zustand · Framer Motion
→ production build: `npm run build` · dev: `npm run dev` (http://localhost:3000)

## Composition

```
app/page.tsx                      workspace shell
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
- **Honesty:** attach/mic/internet/vision toggles are visibly disabled with
  phase badges — no fake features.
