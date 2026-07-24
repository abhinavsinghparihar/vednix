"""
Engine regression tests — each maps to a verified audit finding:

  B2  error text must NEVER be stored as an assistant turn (memory pollution)
  B4  multiple plugins claiming one input ALL answer (was: first-match-wins)
  B3  there is exactly ONE pipeline — stream_reply — no divergent paths
  B5  cancellation persists the partial reply the user already saw
  §8  the system prompt carries the language-mirroring contract
  D1  long-term memory facts actually reach the model's system prompt
"""

from __future__ import annotations

import asyncio

import pytest

from ai_engine.events import CoreState
from ai_engine.prompts import LANGUAGE_MIRRORING_RULE
from tests.conftest import FakeLLM


async def collect(agen) -> str:
    return "".join([chunk async for chunk in agen])


async def test_llm_stream_path_persists_both_turns(core, memory):
    conv = await memory.create_conversation()
    session = core(FakeLLM()).create_session(memory, conv.id)

    reply = await collect(session.stream_reply("hello there"))

    assert reply == "Hello from Vednix!"
    history = await memory.recent_history(conv.id, max_turns=10)
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["content"] == "Hello from Vednix!"


async def test_llm_error_is_NOT_persisted_B2(core, memory):
    conv = await memory.create_conversation()
    session = core(FakeLLM(fail_chat=True)).create_session(memory, conv.id)

    reply = await collect(session.stream_reply("hello"))

    assert "⚠️" in reply  # user is told
    history = await memory.recent_history(conv.id, max_turns=10)
    # Only the user turn — the old app poisoned memory with the error string.
    assert [m["role"] for m in history] == ["user"]


async def test_ollama_offline_message_not_persisted_and_helpful(core, memory):
    conv = await memory.create_conversation()
    session = core(FakeLLM(offline=True)).create_session(memory, conv.id)

    reply = await collect(session.stream_reply("kuch bhi"))

    assert "ollama serve" in reply
    assert await memory.message_count(conv.id) == 1  # user turn only


async def test_multi_plugin_input_is_answered_by_ALL_B4(core, memory):
    conv = await memory.create_conversation()
    llm = FakeLLM()
    session = core(llm).create_session(memory, conv.id)

    reply = await collect(session.stream_reply("what time is it and what's my cpu usage?"))

    assert "%" in reply  # system_info numbers present
    assert "**" in reply  # time plugin markdown present
    assert set(session.last_plugins) == {"system_info", "time"}  # audit B4: BOTH answered
    assert llm.calls == []  # plugins handled it — zero LLM round trips
    history = await memory.recent_history(conv.id, max_turns=10)
    assert history[-1]["role"] == "assistant"


async def test_plugin_path_never_calls_llm(core, memory):
    conv = await memory.create_conversation()
    llm = FakeLLM()
    session = core(llm).create_session(memory, conv.id)
    await collect(session.stream_reply("what time is it"))
    assert llm.calls == []


async def test_cancel_persists_partial_B5(core, memory):
    conv = await memory.create_conversation()
    session = core(FakeLLM()).create_session(memory, conv.id)
    await session.persist_partial("User saw this much *(st")
    history = await memory.recent_history(conv.id, max_turns=10)
    assert history[-1]["content"].endswith("*(stopped)*")


async def test_state_transitions_reach_speaking(core, memory):
    conv = await memory.create_conversation()
    session = core(FakeLLM()).create_session(memory, conv.id)
    seen: list[CoreState] = []
    session.bus.subscribe("state_changed", lambda s: seen.append(s))
    await collect(session.stream_reply("hello"))
    assert CoreState.THINKING in seen
    assert CoreState.SPEAKING in seen
    assert seen[-1] == CoreState.IDLE


async def test_system_prompt_carries_language_rule_and_memory_facts(core, memory):
    conv = await memory.create_conversation()
    await memory.remember("User's name is Abhinav", kind="preference")
    llm = FakeLLM()
    session = core(llm).create_session(memory, conv.id, language="hi")
    await collect(session.stream_reply("namaste"))
    system_msg = llm.calls[0][0]["content"]
    assert "FORCE LANGUAGE" in system_msg
    assert "Abhinav" in system_msg  # audit D1: long-term memory finally reaches the model
    assert llm.calls[0][1]["role"] == "user"


async def test_auto_language_uses_mirroring_rule(core, memory):
    conv = await memory.create_conversation()
    llm = FakeLLM()
    session = core(llm).create_session(memory, conv.id, language="auto")
    await collect(session.stream_reply("hola"))
    assert "CRITICAL LANGUAGE RULE" in llm.calls[0][0]["content"]  # §8 language contract


async def test_empty_plugin_failure_surfaces_politely(core, memory, monkeypatch):
    """A crashing plugin must not crash the chat (orig. app silently swallowed)."""

    class Exploding:
        name = "exploding"
        description = ""
        priority = 99

        def can_handle(self, text):
            return True

        async def execute(self, text, ctx):
            raise RuntimeError("boom")

    engine_core = core(FakeLLM())
    engine_core.plugins.register(Exploding())
    conv = await memory.create_conversation()
    session = engine_core.create_session(memory, conv.id)
    reply = await collect(session.stream_reply("trigger"))
    assert "exploding" in reply
    assert "⚠️" in reply
