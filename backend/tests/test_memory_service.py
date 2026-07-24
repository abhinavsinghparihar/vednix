"""Persistence-layer tests (audit B7: history now survives restarts — real DB)."""

from __future__ import annotations

import pytest


async def test_conversation_crud(memory):
    conv = await memory.create_conversation(title="Test", language="hi")
    assert conv.title == "Test" and conv.language == "hi"

    listed = await memory.list_conversations()
    assert [c.id for c in listed] == [conv.id]

    updated = await memory.update_conversation(conv.id, title="Renamed", pinned=True)
    assert updated.title == "Renamed" and updated.pinned is True

    assert await memory.delete_conversation(conv.id) is True
    assert await memory.get_conversation(conv.id) is None


async def test_history_order_limit_and_cascade(memory):
    conv = await memory.create_conversation()
    for i in range(6):
        await memory.add_message(conv.id, "user" if i % 2 == 0 else "assistant", f"m{i}")

    recent = await memory.recent_history(conv.id, max_turns=4)
    assert [m["content"] for m in recent] == ["m2", "m3", "m4", "m5"]  # chronological tail

    assert await memory.message_count(conv.id) == 6
    await memory.delete_conversation(conv.id)
    assert await memory.list_messages(conv.id) == []  # cascade delete


async def test_longterm_memory_full_cycle(memory):
    note_id = await memory.remember("User prefers dark mode", kind="preference")
    await memory.remember("Random note", kind="note")

    found = await memory.search("dark mode")
    assert [i.id for i in found] == [note_id]

    by_kind = await memory.all(kind="preference")
    assert len(by_kind) == 1

    assert await memory.forget(note_id) is True
    assert await memory.search("dark mode") == []


async def test_pinned_conversations_sort_first(memory):
    a = await memory.create_conversation(title="A")
    b = await memory.create_conversation(title="B")
    await memory.update_conversation(a.id, pinned=True)
    listed = await memory.list_conversations()
    assert listed[0].id == a.id
