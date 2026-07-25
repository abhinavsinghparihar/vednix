# Vednix AI — Maintenance & Redesign Report

_Date: 2026-07-25 · Scope: full-repo audit → cleanup → refactor → 4-prompt
workspace redesign → backend hardening → verification._

Commits: `f5f1ea6` (cleanup/refactor) · `2874291` (workspace UI) · final
(dev/prod distDir guard + this report).

---

## 1. Audit method

- **Frontend reachability**: every file under `app/ components/ lib/ hooks/
  store/` traced through the import graph (scripted grep, 33 files) — all
  reachable. CSS utility/theme-token usage counted per token. Package deps
  traced to imports. Cross-component exports traced to consumers.
- **Backend reachability**: all 41 modules probed for prod and test imports —
  all reachable. `requirements.txt` traced to imports (`redis` is imported
  lazily by design). Grep sweep for commented-out code — none found.
- **New compiler gate**: enabled `noUnusedLocals` + `noUnusedParameters` in
  `tsconfig.json` — it immediately surfaced 5 real dead-code items the grep
  pass had reasoned about but could not prove.
- **Health**: no broken imports (tsc + 109 pytest), no circular deps, no
  oversized files (largest: `store/chat.ts` 471 lines, cohesive).

## 2. Files deleted

None — the tree had no orphan files (previous phases kept it lean).

## 3. Dead code removed

| Item | File | Why dead |
|---|---|---|
| `RoadmapSwitch` component | `components/controls/ControlPanel.tsx` | badge-era leftover, never rendered |
| `useId` import | `components/chat/Markdown.tsx` | unused |
| `cn`, `Badge` imports | `components/controls/ControlPanel.tsx` | unused after RoadmapSwitch removal |
| `api` import | `components/sidebar/Sidebar.tsx` | unused |
| `activeId` destructure | `store/chat.ts` (`handleFrame`) | unused |
| `--animate-spin-slow` token | `app/globals.css` | 0 references |
| `highlight.js` direct dep | `package.json` | only `rehype-highlight` is imported; highlight.js still arrives transitively via lowlight |

## 4. Files created

| File | Purpose |
|---|---|
| `components/chat/attachments.tsx` | shared `formatBytes` / `kindIcon` / `AttachmentChipView` — extracted from Composer |
| `docs/MAINTENANCE_REPORT.md` | this report |

## 5. Files modified (key ones)

- `app/globals.css` — removed dead token; added `.glass-liquid` surface
- `app/chat/page.tsx` — cinematic staggered shell entrance
- `components/Topbar.tsx` — floating liquid-glass pill; display-font title
- `components/composer/Composer.tsx` — liquid-glass capsule; imports shared attachments module
- `components/chat/MessageBubble.tsx` — imports attachments from the new shared module
- `components/sidebar/Sidebar.tsx` — floating panel; official Wordmark brand block
- `components/controls/ControlPanel.tsx` — floating panel; dead code removed
- `components/chat/EmptyState.tsx` — chip hover lift
- `lib/utils.ts` — shared `EASE_CURVE` (landing + workspace use one curve)
- `components/landing/shared.tsx` — reuses `EASE_CURVE`
- `tsconfig.json` — `noUnusedLocals` + `noUnusedParameters`
- `next.config.ts` — `distDir` overridable via `NEXT_DIST_DIR` (hardening)
- `package.json` — dependency pruned
- `backend/main.py` — production-default server start; GZip middleware
- `backend/config.py` — `dev_reload` setting
- `.gitignore`, `README.md` — follow-ups for the above

## 6. Architecture improvements

1. **Shared chat-domain module** — MessageBubble no longer imports the
   Composer to render attachment chips (cross-component dependency removed).
2. **Strict dead-code gate at compile time** — future dead code fails CI
   instead of accumulating; already earning its keep (5 finds).
3. **One motion law** — `EASE_CURVE` in `lib/utils` used by landing and
   workspace; no divergent easings.

## 7. Performance improvements

1. **Backend default is now production-grade**: uvicorn no longer spawns the
   file-watch supervisor on every start (old `reload=True` cost forked
   processes, higher RAM, ignore-exit zombies — observed live this session).
   Dev reload is opt-in: `VEDNIX_DEV_RELOAD=1`.
2. **GZipMiddleware** (≥512 B) compresses REST payloads — conversation lists
   and KB snippets transfer smaller; WS frames bypass HTTP middleware already.
3. **Bundle unchanged-or-smaller**: highlight.js no longer a direct chunk
   candidate; lazy Mermaid policy intact.
4. No re-render regressions: ChatView keeps `useDeferredValue` bottom-pinning;
   orb/background canvases pause when tab hidden; backdrop-blur count
   unchanged (4 panels).

## 8. UI improvements (the 4 reference prompts — now applied app-wide)

| Prompt motif | Landing (already) | **Workspace (NEW this round)** |
|---|---|---|
| P4 liquid glass + floating panels | floating nav pill | sidebar / topbar / studio / composer are all floating `.glass-liquid` panels with margins |
| P2 cinematic stagger + mobile overlay | hero entrances, menu | whole shell enters in one staggered glide (topbar → stage → composer) |
| P1 micro-typography, tracked labels | indicators, wordmark | display-font conversation title; mono core-state readout |
| P3 capsule + edge anchors | ask-capsule | composer upgraded to liquid-glass capsule; hint line as bottom anchor |

Mobile behavior preserved: drawers go edge-to-edge under `md`/`lg`.

## 9. Bugs fixed

1. **Dev-server clobbers production build** — running `next dev` in the same
   directory as a live prod server silently corrupts `.next` (font utilities
   vanished mid-session; caught by the computed-font regression gate in the
   e2e harness). Root fix in-repo: `NEXT_DIST_DIR` override + README note.
2. **Backend always ran dev-mode reload** — process zombies; now opt-in.

## 10. Verification evidence

| Gate | Result |
|---|---|
| `pytest` | **109/109 passing** |
| `tsc --noEmit` (now with unused-locals gate) | clean |
| `npm run build` | ✓ 5/5 static; `/` 10.4 kB / `/chat` 106 kB |
| `npm run dev` | ✓ Ready in ~1.5 s (verified twice, incl. `NEXT_DIST_DIR` co-existence with prod) |
| `python main.py` | ✓ health 200, no reload watcher (grep-verified log) |
| Redesigned UI visible | `shot_ws_shell.png` (floating shell), `shot_ws_streaming.png` |
| WS streaming | live Hindi round trip; core state cycles …→ SPEAKING → IDLE |
| Ollama integration | `/api/health` → `ollama_available: true` (stub-backed e2e) |
| Landing regression | fonts (Outfit/JetBrains Mono) + ask-capsule prefill — all green |
| Unused files | none remaining (reachability scans + strict tsc) |

## 11. Remaining recommendations

1. **Ollama-only posture**: `llm_provider` defaults to Ollama and nothing else
   is active unless `VEDNIX_LLM_PROVIDER=openrouter` + a key are explicitly
   set. The dormant OpenRouter client (Phase 5) can be deleted outright if you
   want a strictly-Ollama codebase — say the word and I'll remove it with its
   tests.
2. Workspace mobile polish pass (drawer gestures, composer safe-area) is the
   next UX-level win.
3. `npm run lint` isn't wired (ESLint not installed) — the strict tsc gates
   cover dead code today; add eslint-config-next when you want style rules.
4. Auth is middleware-gated by token (`VEDNIX_AUTH_TOKEN`); a login screen UI
   is a natural future phase.
