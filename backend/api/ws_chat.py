"""
WebSocket chat transport — true token-level streaming, bidirectional.

Protocol (client → server):
    {"type":"user_message","content":"...","conversation_id":null,"model":null,"language":"auto"}
    {"type":"cancel"}
    {"type":"ping"}

Protocol (server → client):
    {"type":"state_changed","state":"THINKING"}          # drives the UI orb — every CoreState now reachable
    {"type":"message_started","message_id","conversation_id"}
    {"type":"token","message_id","content"}
    {"type":"message_done","message_id","conversation_id","plugins":[],"cancelled":false}
    {"type":"conversation_created","conversation_id","title"}
    {"type":"title_updated","conversation_id","title"}
    {"type":"error","code":"...","message":"..."}
    {"type":"pong"}

Design notes:
  - Receiver + dispatcher loop → 'cancel' is honored mid-stream (async 'stop' button).
  - One active generation per connection (the async fix for audit B5's unbounded threads).
  - Per-connection token bucket (audit SC6 backpressure).
  - Sessions keyed by conversation; language/model overridable per message.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ai_engine.engine import AttachmentRef, EngineCore, EngineSession
from api.schemas import WSUserMessage
from core.logging import get_logger
from core.rate_limit import TokenBucket
from core.security import InputTooLong, validate_user_text
from memory.service import DEFAULT_TITLE, MemoryService

logger = get_logger(__name__)
router = APIRouter(tags=["chat"])


class WSSender:
    """Serializes sends so a background title task can't interleave frames."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws
        self._lock = asyncio.Lock()

    async def send(self, payload: dict) -> None:
        async with self._lock:
            await self._ws.send_json(payload)


async def _receiver(ws: WebSocket, queue: asyncio.Queue) -> None:
    try:
        while True:
            await queue.put(await ws.receive_text())
    except WebSocketDisconnect:
        await queue.put(None)  # sentinel: client gone
    except Exception:
        logger.exception("ws receiver crashed")
        await queue.put(None)


TITLE_PROMPT = (
    "Generate a very short conversation title (3-6 words, no quotes, no punctuation "
    "at the end, same language as the user's message) for a chat that starts with "
    "the user message below. Reply with ONLY the title.\n\nUser message: "
)


async def _autotitle(
    core: EngineCore, memory: MemoryService, sender: WSSender, conversation_id: str, first_user_text: str
) -> None:
    """Best-effort title generation after the first exchange; never blocks chat."""
    try:
        title = (await core.llm.chat(
            [{"role": "user", "content": TITLE_PROMPT + first_user_text[:400]}], temperature=0.3
        )).strip().strip("\"'").split("\n")[0][:80]
        if title:
            await memory.update_conversation(conversation_id, title=title)
            await sender.send({"type": "title_updated", "conversation_id": conversation_id, "title": title})
    except Exception:
        logger.warning("auto-title failed (conv=%s)", conversation_id)


async def _stream_reply(
    session: EngineSession,
    sender: WSSender,
    message_id: str,
    text: str,
    model: str | None,
    temperature: float | None,
    attachments: list[AttachmentRef],
    internet: bool = False,
    multi_agent: bool = False,
) -> None:
    async def forward_state(state) -> None:
        await sender.send({"type": "state_changed", "state": state.name})

    async def forward_step(entry) -> None:
        await sender.send({"type": "agent_step", **entry})

    session.bus.subscribe("state_changed", forward_state)
    session.bus.subscribe("agent_step", forward_step)
    partial: list[str] = []
    try:
        await sender.send(
            {"type": "message_started", "message_id": message_id, "conversation_id": session.conversation_id}
        )
        async for chunk in session.stream_reply(
            text, model=model, temperature=temperature, attachments=attachments,
            internet=internet, multi_agent=multi_agent,
        ):
            partial.append(chunk)
            await sender.send({"type": "token", "message_id": message_id, "content": chunk})
    except asyncio.CancelledError:
        await session.persist_partial("".join(partial))
        await sender.send(
            {"type": "message_done", "message_id": message_id,
             "conversation_id": session.conversation_id, "plugins": [], "cancelled": True}
        )
        raise
    finally:
        session.bus.unsubscribe("state_changed", forward_state)
        session.bus.unsubscribe("agent_step", forward_step)

    await sender.send(
        {
            "type": "message_done",
            "message_id": message_id,
            "conversation_id": session.conversation_id,
            "plugins": session.last_plugins,
            "kb_sources": session.last_kb_sources,
            "sources": session.last_sources,
            "steps": session.last_steps,
            "cancelled": False,
        }
    )


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()
    core: EngineCore = ws.app.state.core
    memory: MemoryService = ws.app.state.memory

    sender = WSSender(ws)
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    receiver = asyncio.create_task(_receiver(ws, queue))
    bucket = TokenBucket(rate=8, per_seconds=20.0)  # audit SC6: connection-level backpressure
    sessions: dict[str, EngineSession] = {}
    stream_task: asyncio.Task | None = None

    try:
        while True:
            raw = await queue.get()
            if raw is None:
                break
            try:
                payload = WSUserMessage.model_validate_json(raw)
            except Exception:
                # cheap frame-type sniffing for ping/cancel without full union errors
                if '"ping"' in raw:
                    await sender.send({"type": "pong"})
                elif '"cancel"' in raw:
                    if stream_task and not stream_task.done():
                        stream_task.cancel()
                    else:
                        await sender.send({"type": "error", "code": "nothing_to_cancel", "message": "No active generation."})
                else:
                    await sender.send({"type": "error", "code": "bad_payload", "message": "Invalid message frame."})
                continue

            if payload.type == "user_message":
                if stream_task and not stream_task.done():
                    await sender.send(
                        {"type": "error", "code": "busy", "message": "Still generating — wait, or send 'cancel'."}
                    )
                    continue
                if not await bucket.allow():
                    await sender.send(
                        {"type": "error", "code": "rate_limited", "message": "Too many messages — slow down a moment."}
                    )
                    continue
                try:
                    text = validate_user_text(payload.content)
                except InputTooLong as exc:
                    await sender.send({"type": "error", "code": "too_long", "message": str(exc)})
                    continue
                except ValueError as exc:
                    await sender.send({"type": "error", "code": "invalid", "message": str(exc)})
                    continue

                # Resolve attachments (uploaded earlier via POST /api/uploads).
                attachment_refs: list[AttachmentRef] = []
                if payload.attachments:
                    files_store = getattr(ws.app.state, "files", None)
                    missing = False
                    for file_id in payload.attachments[:5]:
                        record = await files_store.get(file_id) if files_store else None
                        if record is None:
                            await sender.send(
                                {"type": "error", "code": "attachment_not_found",
                                 "message": f"An attachment ({file_id[:8]}…) no longer exists — re-upload it."}
                            )
                            missing = True
                            break
                        attachment_refs.append(
                            AttachmentRef(id=record.id, name=record.name, kind=record.kind, size=record.size)
                        )
                    if missing:
                        continue

                # Resolve or create the conversation.
                conv = await memory.get_conversation(payload.conversation_id) if payload.conversation_id else None
                if conv is None:
                    conv = await memory.create_conversation()
                    await sender.send(
                        {"type": "conversation_created", "conversation_id": conv.id, "title": conv.title}
                    )
                if payload.language and payload.language != conv.language:
                    conv = await memory.update_conversation(conv.id, language=payload.language) or conv

                session = sessions.get(conv.id)
                if session is None:
                    session = core.create_session(memory, conv.id, language=conv.language)
                    sessions[conv.id] = session
                else:
                    session.language = conv.language

                message_id = uuid.uuid4().hex
                first_exchange = (await memory.message_count(conv.id)) == 0
                stream_task = asyncio.create_task(
                    _stream_reply(
                        session, sender, message_id, text,
                        payload.model or conv.model, payload.temperature, attachment_refs,
                        payload.internet, payload.multi_agent,
                    )
                )
                if first_exchange:
                    stream_task.add_done_callback(
                        lambda *_args, cid=conv.id, t=text: asyncio.create_task(
                            _autotitle(core, memory, sender, cid, t)
                        )
                    )
    finally:
        receiver.cancel()
        if stream_task and not stream_task.done():
            stream_task.cancel()
        try:
            await ws.close()
        except Exception:
            pass
