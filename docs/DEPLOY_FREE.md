# Vercel + Render deployment

This guide uses the production origins reserved for Vednix:

- Frontend: `https://vednix.vercel.app`
- Backend API: `https://vednix.onrender.com`
- Backend WebSocket: `wss://vednix.onrender.com/ws/chat`

## Vercel

Set these frontend build-time environment variables for Production (and Preview only if the preview backend is intentionally configured for that origin):

```text
NEXT_PUBLIC_API_BASE=https://vednix.onrender.com
NEXT_PUBLIC_WS_BASE=wss://vednix.onrender.com/ws/chat
```

The Next.js client reads these at build time. Redeploy after changing them. Never place Gemini/Groq keys, backend auth secrets, or any other credential in `NEXT_PUBLIC_*`.

## Render backend

Create a Python web service using `backend/` as its root directory.

- Build command: `pip install -r requirements.txt`
- Start command: `python -m uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/api/health`

Set an explicit credentialed CORS allowlist. Origins contain scheme and host only—no wildcard and no path:

```text
VEDNIX_CORS_ORIGINS=https://vednix.vercel.app,http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001
```

The application adds those local origins and the production Vercel origin to its validated allowlist. If the frontend domain changes, update the backend configuration and redeploy. WebSocket origins are checked against the same list.

Use persistent storage for the database, upload directory, and server secret. The current backend dependencies include SQLite support by default; a Render-managed PostgreSQL database also requires installing the matching async SQLAlchemy driver before setting `VEDNIX_DATABASE_URL`. The default SQLite database and local upload directory are suitable for development or a persistent disk; ephemeral filesystem deployments can lose local files between restarts. Set `VEDNIX_UPLOAD_DIR` to a persistent mount when uploads must survive restarts.

Optional backend settings include `VEDNIX_REDIS_URL` for shared rate limiting, `VEDNIX_AUTH_TOKEN` for an additional bearer-token gate, SearXNG settings for research, and SMTP settings for email login. Use Render's secret environment variable facility for credentials. Gemini and Groq keys are deliberately entered in the authenticated Vednix Settings UI and encrypted by the backend; do not add them to Vercel variables or commit them.

## Verify after deployment

1. Open `https://vednix.onrender.com/api/health` and confirm the service is healthy.
2. In the browser Network panel, confirm API and WebSocket requests target the configured Render origins—not `localhost`.
3. Sign in, add a Gemini or Groq key in **Settings → API Keys**, and require a successful provider check before enabling it.
4. Refresh **Settings → AI Models** to discover current models and run the task-specific validation.
5. Test a text reply, then image routing only with a validated vision-capable model.

No live provider verification can be claimed until a real user key passes the provider's check.
