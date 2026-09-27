# Vednix AI

**A multilingual AI workspace with live-validated Gemini and Groq providers.** Vednix combines WebSocket-streamed chat, conversation history, file uploads, vision routing, memory, knowledge search, and optional web research in one workspace.

Connect Google Gemini or Groq in Settings. Provider keys are stored encrypted by the backend and are never returned to the browser. Models are discovered from official provider APIs and are exposed as usable only after the requested capability passes a live check; there is no large hardcoded model catalog.

## Quick start

Requirements: Python 3.11+ and Node.js 20+.

- Windows: double-click `start.bat`.
- macOS/Linux: run `./start.sh`.

The launcher installs project dependencies and starts the FastAPI backend and Next.js frontend. It does not install a model runtime or handle provider credentials. Open the workspace and connect a provider key during onboarding or from **Settings → API Keys**.

### Manual development

```bash
# Backend
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r requirements-dev.txt
python main.py

# Frontend, in another terminal
cd frontend
npm ci
npm run dev
```

Local browser development uses the backend on port 8000. Run backend tests with:

```bash
cd backend
.venv/bin/pytest -q
```

## Providers and security

- Initially supported providers: **Google Gemini** and **Groq**.
- Model lists and metadata come from official provider APIs; every usable text, vision, or tools model is validated against that operation.
- Automatic routing selects a compatible provider/model by saved priority and fails over only before the first response token. An explicitly selected provider stays strict.
- API keys are encrypted at rest on the server. They are not put in `NEXT_PUBLIC_*`, browser storage, URLs, or API responses.
- CORS uses an exact credentialed allowlist. `https://vednix.vercel.app` and localhost development origins are allowed; wildcards are rejected.
- Chat and attachments remain associated with the existing Vednix account/session and backend. Provider data handling is subject to the provider account's terms.

## Production deployment

Frontend (Vercel) build-time variables:

```text
NEXT_PUBLIC_API_BASE=https://vednix.onrender.com
NEXT_PUBLIC_WS_BASE=wss://vednix.onrender.com/ws/chat
```

Backend (Render) must allow the deployed frontend origin and local development origins explicitly:

```text
VEDNIX_CORS_ORIGINS=https://vednix.vercel.app,http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001
```

Set a persistent production database and upload volume as appropriate for the chosen Render plan. Provider keys are entered in the application, not configured as deployment environment variables. See [deployment notes](docs/DEPLOY_FREE.md) for the full setup.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API reference](docs/API.md)
- [Frontend guide](docs/FRONTEND.md)
- [Docker](docs/DOCKER.md)
- [Deployment](docs/DEPLOY_FREE.md)
- [Project inventory](docs/PROJECT_INVENTORY.md)

Made by Abhinav Singh.
