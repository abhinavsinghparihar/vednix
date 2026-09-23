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
# Render cannot reach Ollama on your Windows PC. This loopback URL is
# intentionally local to the Render container and will report Ollama offline.
VEDNIX_OLLAMA_HOST=http://127.0.0.1:11434
VEDNIX_OLLAMA_MODEL=qwen2.5:3b
VEDNIX_GEMINI_MODEL=gemini-3.8-flash
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

Redeploy after saving variables. Replace the placeholders with the real
service/domain values from your Render and Vercel dashboards. Add the exact
Vercel origin (scheme + hostname only, no path and no trailing wildcard) to
`VEDNIX_CORS_ORIGINS`. It is comma-separated for multiple production/preview
origins; credentialed CORS intentionally rejects `*`. The same exact origin
allowlist protects `/ws/chat`, so a browser WebSocket from an unlisted Vercel
origin is rejected rather than silently connecting.

`NEXT_PUBLIC_API_BASE` must be the Render **backend origin**. The WebSocket
base can be omitted because the frontend derives `wss://.../ws/chat` from that
HTTPS API base, or set explicitly as shown. The production frontend no longer
falls back to `127.0.0.1`; if the API URL is missing, it reports a configuration
error instead of calling the visitor's computer.

For Vercel-to-Render authentication, HTTPS refresh cookies use
`SameSite=None; Secure`; the SPA bootstraps the double-submit CSRF nonce from
`/api/auth/csrf` and holds it in memory. Browser privacy settings that block all
cross-site cookies can still prevent refresh-cookie persistence; if that affects
your users, use a same-site API hostname (for example, `api.YOUR-DOMAIN`) or a
same-origin proxy. CORS cannot override a browser's third-party-cookie policy.

Render cannot access Ollama on a developer's Windows PC. Keep the Render Ollama
host at its container-local loopback address and let Vednix show it as
unavailable; a verified cloud provider such as Gemini is then usable. For
local development, the default remains `http://localhost:11434`.

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
