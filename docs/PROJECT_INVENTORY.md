# Vednix AI project inventory

This is the keep/delete guide. Do not delete folders marked KEEP: they are imported by the running app or required for tests, startup, persistence, security, or deployment.

## KEEP — frontend
- `frontend/app/` — Next.js routes: landing, login, signup, onboarding, chat, settings and profile.
- `frontend/components/` — UI, auth, landing, workspace, chat, controls, onboarding, orb and shared primitives.
- `frontend/hooks/` — speech recognition.
- `frontend/lib/` — REST client, auth/session vault, WebSocket, theme, TTS, branding and utilities.
- `frontend/store/` — Zustand auth and chat state.
- `frontend/types/` — speech TypeScript declarations.
- `frontend/package.json`, `package-lock.json`, `tsconfig.json`, `next.config.ts`, `postcss.config.mjs`, `next-env.d.ts`, `Dockerfile`, `.env.local.example`.

## KEEP — backend
- `backend/api/` — FastAPI routes.
- `backend/ai_engine/` — Ollama, cloud providers, routing, prompts and engine pipeline.
- `backend/agents/` — built-in plugins and SearXNG research graphs.
- `backend/core/` — sessions, encryption, JWT, rate limits and logging.
- `backend/memory/` — SQLAlchemy models, SQLite initialization and persistence.
- `backend/services/` — users, onboarding, providers, knowledge and file storage.
- `backend/scripts/` — password recovery utility.
- `backend/tests/` — regression and integration tests.
- `backend/main.py`, `config.py`, `requirements*.txt`, `pytest.ini`, `Dockerfile`, `.env.example`.
- `backend/data/vednix.db` and `backend/data/secret.key` — local state and encrypted-key material; never delete.

## KEEP — root
- `scripts/launch.py`, `start.bat`, `start.sh`, `README.md`, `docs/`.

## Generated/local files
Do not commit/copy `frontend/node_modules/`, `frontend/.next/`, Python `__pycache__/`, logs, or `backend/data/*.db-wal`/`*.db-shm`; they are runtime/generated.

## Cleanup conclusion
No application folder is safely confirmed unused. Deleting apparently unused files can remove a route, plugin, test fixture, or deployment path. Run `npm run typecheck`, `npm run build`, and `pytest` after future cleanup.
