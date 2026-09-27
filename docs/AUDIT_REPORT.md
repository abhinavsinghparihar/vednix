# Product and security notes

This report describes the current Vednix workspace, not historical implementation claims.

## Runtime outline

Vednix consists of a Next.js client and a FastAPI backend. Chat uses the existing WebSocket stream; conversations, accounts, uploaded files, and provider metadata are served by backend APIs. Gemini and Groq are the initially supported inference providers.

## Provider safety

- Provider metadata is a short setup list. Model identifiers are discovered through official provider APIs.
- A model appears usable only after a live operation-specific check. Metadata or a model name alone never establishes text, vision, tool, audio, image-generation, or video capability.
- Provider keys are encrypted at rest on the backend. Keys are not returned by API routes and must not be exposed through frontend variables, browser storage, URLs, or logs.
- Provider errors are sanitized. Automatic failover is restricted to compatible providers and occurs only before the first response token. Explicit selections are strict.
- CORS and WebSocket origins are explicit and credentialed; wildcard origins are rejected.

## Operational limits

A live provider check requires a real account key and a successful request. Tests use injected HTTP mock transports and do not claim an external provider was contacted. Production deployments need persistent database and upload storage if local filesystem state must survive restarts.

## Release checks

Run backend tests from `backend/` with `pytest -q`, and frontend checks from `frontend/` with `npm run typecheck` and `npm run build`. Test chat and Studio behavior at 320, 375, 390, and 430 CSS-pixel widths before release.
