# Free deployment guide (current architecture)

## Important reality

Vednix is local-first: Ollama and SQLite are designed to run on the user's own
machine. A completely free public deployment can host the UI and a demo API,
but it cannot provide reliable public Ollama inference or durable SQLite storage.
Render's free filesystem is ephemeral and free services sleep after 15 minutes,
so do not use its local SQLite/database for important data.

## Recommended $0 split deployment for a demo

### 1. Backend on Render

Create **New → Web Service** from the GitHub repository.

- Root directory: `backend`
- Runtime: Python 3
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Plan: Free

Set environment variables:

```env
VEDNIX_HOST=0.0.0.0
VEDNIX_PORT=10000
VEDNIX_CORS_ORIGINS=https://YOUR-VERCEL-DOMAIN.vercel.app
VEDNIX_SEARXNG_URL=
VEDNIX_OLLAMA_HOST=https://YOUR-OLLAMA-HOST
VEDNIX_DATABASE_URL=postgresql+asyncpg://...
```

For a disposable demo, SQLite can remain, but its data will be lost on restart.
For durable users/providers/conversations, use a PostgreSQL service and add
`asyncpg` to requirements before deployment. Never expose Ollama on an open
public port without authentication.

### 2. Frontend on Vercel

Import the same GitHub repository in Vercel.

- Root directory: `frontend`
- Framework: Next.js
- Build command: `npm run build`
- Output: default Next.js output

Add:

```env
NEXT_PUBLIC_API_BASE=https://YOUR-RENDER-SERVICE.onrender.com
NEXT_PUBLIC_WS_BASE=wss://YOUR-RENDER-SERVICE.onrender.com/ws/chat
```

Redeploy after saving variables. Add the final Vercel URL to the backend
`VEDNIX_CORS_ORIGINS` value.

### 3. Cloud provider

For public AI, configure Gemini/OpenRouter in Vednix's provider settings. Keys
are sent to the backend and encrypted there; do not put them in Vercel
`NEXT_PUBLIC_*` variables.

### 4. Internet/deep search

The current deep-research agent uses SearXNG. Run SearXNG privately or on a
separate service and set `VEDNIX_SEARXNG_URL` to its HTTPS URL. An empty value
intentionally disables search instead of faking results.

## Best production-like option

Keep the backend, Ollama, SQLite, API keys and data on the Windows machine and
use a secure tunnel only when needed. This preserves the local-first promise,
avoids free-host filesystem loss, and keeps Ollama private.
