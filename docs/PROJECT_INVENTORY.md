# Vednix project inventory

## Frontend

- `frontend/app/` — landing, authentication, onboarding, workspace, settings, and profile routes.
- `frontend/components/` — chat, composer, sidebar, Studio, workspace views, onboarding, auth, and shared UI.
- `frontend/hooks/` — browser speech recognition and reusable hooks.
- `frontend/lib/` — API clients, WebSocket client, auth/session handling, theme, TTS, and utilities.
- `frontend/store/` — account and workspace/chat state.
- `frontend/package.json`, `package-lock.json`, `tsconfig.json`, `next.config.ts`, and `Dockerfile` — build/runtime setup.
- `frontend/public/` — static assets served from the web root. It must exist: the Docker image copies it into the standalone server output.
- `frontend/app/icon.svg` — the browser tab icon (the neural-V sigil, matching `components/brand/LogoMark.tsx`).

## Backend

- `backend/api/` — FastAPI REST endpoints and the WebSocket chat transport.
- `backend/ai_engine/` — Gemini/Groq adapters, model capability data, safe provider errors, and chat engine.
- `backend/services/providers.py` — encrypted provider-key management and live model validation.
- `backend/services/resilient_llm.py` — provider/model selection and compatible-provider failover.
- `backend/agents/` — plugins and optional SearXNG research.
- `backend/core/` — encryption, auth, sessions, rate limits, and logging.
- `backend/memory/` — SQLAlchemy models, database initialization, conversations, and memory.
- `backend/services/` — users, onboarding, uploads, knowledge, and provider services.
- `backend/tests/` — unit and integration regressions.
- `backend/requirements*.txt`, `pytest.ini`, `Dockerfile`, and `.env.example` — install, test, deploy, and configuration files.

## Root and local/generated files

- `scripts/launch.py`, `start.bat`, `start.sh`, `docker-compose.yml`, `README.md`, and `docs/` — launch, deployment, and project guidance.
- `.github/workflows/ci.yml` — runs the backend suite and the frontend typecheck/build on pushes and pull requests.
- Never commit credentials, encrypted-key databases, server secret files, logs, `node_modules`, `.next`, virtual environments, or Python cache files.
- `.env.example` files contain placeholders only. Real provider keys are entered in Settings and remain server-side.
