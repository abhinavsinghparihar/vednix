# Vednix API reference

The local API defaults to `http://localhost:8000`; interactive OpenAPI documentation is at `/docs`. Production frontend URLs are configured through `NEXT_PUBLIC_API_BASE` and `NEXT_PUBLIC_WS_BASE`.

## Provider management

All provider management routes are under `/api/providers`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/providers/catalog` | Small static setup metadata for the supported providers; contains no model catalog or credentials. |
| GET | `/api/providers` | Configured-provider status, non-reversible key hint, and priority; never returns saved keys. |
| PUT | `/api/providers/{provider}/key` | Encrypt and save a key or change a selected text model. Response includes status/hint only. |
| DELETE | `/api/providers/{provider}/key` | Remove saved key and model checks. |
| POST | `/api/providers/{provider}/verify` | Validate the key and selected text model with a real provider request. |
| GET | `/api/providers/{provider}/models?task=text&force=false` | Fetch live provider models and return only models validated for `task`. |
| POST | `/api/providers/{provider}/models/validate` | Validate `{ "model_id": "…", "task": "vision" }`. |
| POST | `/api/providers/{provider}/toggle` | Enable/disable a provider after successful verification. |
| PUT | `/api/providers/priority` | Save `{ "order": ["groq", "openai"] }`. |
| POST | `/api/providers/free/enable` | Turn on the keyless free tier. No credential is stored; the response is a live verification result (`connected`, `verification_model`, `detail`). |

Supported task values are `text`, `vision`, `audio_input`, `audio_output`, `image_generation`, `video`, and `tools`. Capabilities are never inferred from model names. Tasks that do not have an implemented, successful provider probe are returned as unavailable. Model validation is cached server-side for a limited period and can be force-refreshed.

`free` is the only provider whose catalog entry has `"needs_key": false` and
`"free": true`. Its endpoint, candidate models and optional operator token come
from `VEDNIX_FREE_USE_*` environment settings; it is last in routing priority and
subject to `VEDNIX_FREE_USE_REQUESTS_PER_HOUR`. It still passes a real completion
and streaming probe before it can answer, exactly like a paid provider.

Every provider is discovered through its official OpenAI-compatible `models` endpoint (for example Groq's `/openai/v1/models`), and chat usability is confirmed with a real chat-completions probe — streaming, vision and tool capabilities each need their own successful check. Candidate catalog entries are not marked usable until the corresponding operation succeeds.

## Core REST routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Service and provider-neutral chat readiness. |
| GET | `/api/models?provider=groq&task=text` | Compatible, validated models for the current provider/task. |
| GET/POST | `/api/conversations` | List or create conversations. |
| GET/PATCH/DELETE | `/api/conversations/{id}` | Read, update, or remove a conversation. |
| POST | `/api/uploads` | Upload files for chat (bounded size/count). |
| GET | `/api/uploads/{id}` | Read upload metadata. |
| GET | `/api/uploads/{id}/text` | Read extracted text for a stored upload. |
| GET/POST/DELETE | `/api/memory` | List, save, and remove memory items. |
| GET/POST/DELETE | `/api/knowledge/documents` | List, add, and remove indexed documents. |
| GET | `/api/knowledge/search?q=…` | Search indexed knowledge. |
| GET | `/api/system/status` | Backend system and usage status. |
| GET | `/api/onboarding/status` | Read setup state. |
| POST | `/api/onboarding/mode` | Save the supported provider-backed workspace mode. |
| POST | `/api/onboarding/complete` | Mark first-run setup complete. |
| POST | `/api/onboarding/wipe-data` | Remove user conversation and memory data. |

Authentication routes are under `/api/auth`; owner administration is under `/api/admin`.

Device sessions use a short-lived (20 minute) access token in the `Authorization`
header plus an httpOnly refresh cookie that rotates on every use. Sessions created
with `remember: true` slide forward and are bounded by `VEDNIX_SESSION_DAYS`
(default 3650 days), so a signed-in device stays signed in until it explicitly
signs out or is revoked.

## WebSocket chat — `/ws/chat`

### Client frame

```json
{
  "type": "user_message",
  "content": "Explain this image",
  "conversation_id": null,
  "provider": "groq",
  "model": null,
  "language": "auto",
  "temperature": 0.7,
  "attachments": ["upload-id"],
  "internet": false,
  "multi_agent": false
}
```

`provider: null` requests automatic priority routing. An explicit provider/model is strict. The existing WebSocket is the sole chat transport; chat messages and attachments remain attached to the selected conversation. Other client frames are `{"type":"cancel"}` and `{"type":"ping"}`.

The server sends `state_changed`, `message_started`, `token`, `agent_step`, `message_done`, `conversation_created`, `title_updated`, `error`, or `pong` frames. Pre-token provider errors may trigger a compatible-provider handoff; after the first token, the response is not silently switched to another provider.

## CORS and errors

CORS is credentialed and allowlisted for exact origins: `https://vednix.vercel.app` and configured localhost development origins. Wildcards and URL paths are rejected. The WebSocket checks the same origin list.

Provider errors are sanitized for the UI. Authentication, quota/rate-limit, unsupported capability, and temporary outage conditions are classified separately. API keys are redacted from error details and are never returned in responses.
