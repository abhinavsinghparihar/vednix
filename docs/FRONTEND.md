# Frontend guide

The frontend is a Next.js App Router application using TypeScript, React, Tailwind CSS, Framer Motion, and Zustand. The existing `/ws/chat` WebSocket is the single streaming chat transport.

## Main routes

- `/` — product landing page and workspace entry.
- `/login`, `/signup` — account authentication.
- `/onboarding` — initial workspace setup and Gemini/Groq provider connection.
- `/chat` — workspace shell, conversation sidebar, chat stage, composer, and Studio controls.
- `/settings` — provider keys, live model discovery, task checks, priorities, memory/privacy and account settings.
- `/profile` — account and session management.

## State and provider selection

`store/chat.ts` owns the active conversation, messages, draft attachments, WebSocket lifecycle, selected provider, current model options, and model-per-provider preferences. Switching provider/model does not clear the conversation or attachments. Provider model catalogs are fetched from the backend; API keys are never stored in frontend state, browser storage, or public environment variables.

`lib/api.ts` handles workspace REST APIs; `lib/authApi.ts` handles account/provider APIs; `lib/ws.ts` implements the single chat WebSocket protocol. `lib/config.ts` selects localhost for loopback development and the configured API/WS base for deployment.

## Mobile workspace

The chat stage uses `min-w-0` sizing and a full-width composer on narrow viewports. The conversation sidebar defaults closed on phone widths and opens as a dismissible drawer. The Studio defaults closed on compact viewports and opens as a dismissible bottom sheet with a close button, backdrop, and Escape handling. Both controls remain in the Zustand store so opening/closing overlays preserves the active chat.

Check mobile layouts at 320, 375, 390, and 430 CSS pixels; the composer controls remain available, messages can wrap, and horizontal overflow is avoided.

## Development checks

```bash
npm ci
npm run typecheck
npm run build
```

Do not expose server provider keys through `NEXT_PUBLIC_*`. The browser receives only validated model identifiers, provider status, safe error details, and non-reversible key hints.
