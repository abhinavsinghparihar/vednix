"""
Core state machine + pub/sub bus.

♻️ PRESERVED from dev_ai/core/events.py (~95% identical) — the design was right.
Changes:
  - publish() is now async: in the old Tk app, callbacks had to be marshalled
    onto the UI thread; here everything already runs on one event loop.
  - Added "error" to the state vocabulary mapping handled at the WS layer.
  - CoreState list kept verbatim — every state is now actually reachable
    (audit U6/D5: 6 of 8 states could never trigger in the desktop app).
"""

from __future__ import annotations

import inspect
from enum import Enum, auto
from typing import Any, Awaitable, Callable

from core.logging import get_logger

logger = get_logger(__name__)


class CoreState(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    EXECUTING = auto()
    SEARCHING = auto()
    LEARNING = auto()
    UPDATING = auto()


Subscriber = Callable[..., Any | Awaitable[Any]]


class EventBus:
    """Async pub/sub scoped to ONE chat connection. Sync or async callbacks both
    accepted; a broken subscriber is logged, never fatal (audit B9: the old bus
    died or silently swallowed, now failures are visible)."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = {}

    def subscribe(self, event: str, callback: Subscriber) -> None:
        self._subscribers.setdefault(event, []).append(callback)

    def unsubscribe(self, event: str, callback: Subscriber) -> None:
        subs = self._subscribers.get(event)
        if subs and callback in subs:
            subs.remove(callback)

    async def publish(self, event: str, *args: Any, **kwargs: Any) -> None:
        for callback in list(self._subscribers.get(event, [])):
            try:
                result = callback(*args, **kwargs)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("event subscriber failed (event=%s)", event)


class StateManager:
    """Tracks the assistant CoreState for one session and broadcasts changes
    (event: 'state_changed'). One StateManager per connection — the original's
    single global state was audit SC5 (two requests would fight over one state)."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._state = CoreState.IDLE

    @property
    def state(self) -> CoreState:
        return self._state

    async def set(self, new_state: CoreState) -> None:
        if new_state == self._state:
            return
        self._state = new_state
        await self._bus.publish("state_changed", new_state)
