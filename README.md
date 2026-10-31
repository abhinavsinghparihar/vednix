# Vednix AI

**A multilingual AI workspace with live-validated multi-provider inference.** Vednix combines WebSocket-streamed chat, conversation history, file uploads, vision routing, memory, knowledge search, and optional web research in one workspace.

Connect a provider — Groq, OpenAI, Mistral, DeepSeek, OpenRouter, Together, xAI, Cerebras, SambaNova, NVIDIA NIM or Perplexity — in Settings, or start with **Free use** next to the API-key field and skip keys entirely. Provider keys are stored encrypted by the backend and are never returned to the browser. Models are discovered from official provider APIs and are exposed as usable only after the requested capability passes a live check; there is no large hardcoded model catalog.

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

Local browser development uses the backend on port 8000. Run the checks with:

```bash
# Backend
cd backend
.venv/bin/pytest -q

# Frontend, in another terminal
cd frontend
npm run typecheck
npm run build
```

Every push and pull request runs the same backend suite and frontend typecheck/build through GitHub Actions (`.github/workflows/ci.yml`). No provider credentials are needed for CI; the provider boundary is exercised with an injected test transport.

## Providers and security

- Supported providers: **Groq**, **OpenAI**, **Mistral**, **DeepSeek**, **OpenRouter**, **Together**, **xAI**, **Cerebras**, **SambaNova**, **NVIDIA NIM** and **Perplexity** — all through their official OpenAI-compatible APIs, with keys encrypted server-side.
- Model lists and metadata come from official provider APIs; every usable text, vision, or tools model is validated against that operation.
- Automatic routing selects a compatible provider/model by saved priority and fails over only before the first response token. An explicitly selected provider stays strict.
- API keys are encrypted at rest on the server. They are not put in `NEXT_PUBLIC_*`, browser storage, URLs, or API responses.
- **No credential in source:** batch imports go through `backend/scripts/import_keys.py` (validated, encrypted, never echoed), and `scripts/scan_secrets.py` fails CI if a key-shaped string ever lands in a tracked file. See [secret handling](docs/SECRETS.md).
- **Free use** is keyless: a shared, best-effort tier configured by `VEDNIX_FREE_USE_*`, live-verified before it can answer, budgeted per hour, and always last in routing priority behind your own keys.
- **Stay signed in:** a device that signs in once keeps a sliding, httpOnly session (`VEDNIX_SESSION_DAYS`, default ten years) until it explicitly signs out or is revoked. Transient network failures never sign a device out.
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

- [Secret handling](docs/SECRETS.md)
- [API key audit](docs/API_KEY_AUDIT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API reference](docs/API.md)
- [Frontend guide](docs/FRONTEND.md)
- [Docker](docs/DOCKER.md)
- [Deployment](docs/DEPLOY_FREE.md)
- [Project inventory](docs/PROJECT_INVENTORY.md)

Made by Abhinav Singh.
