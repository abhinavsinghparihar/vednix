# Vednix API reference

The local API defaults to `http://localhost:8000`; interactive OpenAPI documentation is at `/docs`. Production frontend URLs are configured through `NEXT_PUBLIC_API_BASE` and `NEXT_PUBLIC_WS_BASE`.

## Provider management

All provider management routes are under `/api/providers`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/providers/catalog` | Small static setup metadata for Gemini and Groq; contains no model catalog or credentials. |
| GET | `/api/providers` | Configured-provider status, non-reversible key hint, and priority; never returns saved keys. |
| PUT | `/api/providers/{provider}/key` | Encrypt and save a key or change a selected text model. Response includes status/hint only. |
| DELETE | `/api/providers/{provider}/key` | Remove saved key and model checks. |
| POST | `/api/providers/{provider}/verify` | Validate the key and selected text model with a real provider request. |
| GET | `/api/providers/{provider}/models?task=text&force=false` | Fetch live provider models and return only models validated for `task`. |
| POST | `/api/providers/{provider}/models/validate` | Validate `{ "model_id": "…", "task": "vision" }`. |
| POST | `/api/providers/{provider}/toggle` | Enable/disable a provider after successful verification. |
| PUT | `/api/providers/priority` | Save `{ "order": ["gemini", "groq"] }`. |

Supported task values are `text`, `vision`, `audio_input`, `audio_output`, `image_generation`, `video`, and `tools`. Capabilities are never inferred from model names. Tasks that do not have an implemented, successful provider probe are returned as unavailable. Model validation is cached server-side for a limited period and can be force-refreshed.

Gemini discovery uses Google's official paginated `models.list` endpoint and its supported-generation-method metadata. Generation is sent through Gemini's OpenAI-compatible chat endpoint. Groq discovery uses its official `/openai/v1/models` endpoint; chat usability is checked through chat completions. Candidate catalog entries are not marked usable until an operation succeeds.

## Core REST routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Service and provider-neutral chat readiness. |
| GET | `/api/models?provider=gemini&task=text` | Compatible, validated models for the current provider/task. |
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

## WebSocket chat — `/ws/chat`

### Client frame

```json
{
  "type": "user_message",
  "content": "Explain this image",
  "conversation_id": null,
  "provider": "gemini",
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
