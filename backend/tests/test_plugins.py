"""Plugin tests — incl. audit B6: Hindi/Hinglish triggers must route and answer in-register."""

from __future__ import annotations

import re

import pytest

from agents import build_plugins
from agents.base import PluginContext
from agents.builtin.memory_plugin import MemoryPlugin
from agents.builtin.system_info import SystemInfoPlugin
from agents.builtin.time_plugin import TimePlugin
from agents.plugin_manager import PluginManager


@pytest.fixture
def ctx(settings, memory):
    return PluginContext(settings=settings, memory=memory)


def routing_manager() -> PluginManager:
    return PluginManager(build_plugins())


# --- TimePlugin ---------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "what time is it",
    "what's the date",
    "what’s the date",            # smart quote (audit B6)
    "time kya hai",               # Hinglish
    "kitne baje hain",
    "अभी समय क्या है",            # Devanagari
    "aaj ki date batao",
])
def test_time_plugin_routes_localized(text):
    assert TimePlugin().can_handle(text) is True


def test_time_plugin_ignores_unrelated():
    assert TimePlugin().can_handle("tell me a joke") is False


async def test_time_plugin_answers_in_users_register(ctx):
    hindi = await TimePlugin().execute("अभी समय क्या है", ctx)
    assert re.search(r"बजे", hindi)
    english = await TimePlugin().execute("what time is it", ctx)
    assert "It's" in english


# --- SystemInfoPlugin -----------------------------------------------------------

@pytest.mark.parametrize("text", ["cpu usage", "battery kitni hai", "सिस्टम का हाल बताओ", "ram?"])
def test_system_info_routes_localized(text):
    assert SystemInfoPlugin().can_handle(text) is True


async def test_system_info_reports_stats(ctx):
    pytest.importorskip("psutil")
    result = await SystemInfoPlugin().execute("cpu usage", ctx)
    assert "CPU" in result and "%" in result


# --- MemoryPlugin (revives audit D1) -------------------------------------------

@pytest.mark.parametrize("text", [
    "remember that I like tea",
    "याद रखो कि मेरी मीटिंग कल है",
    "what do you remember about me",
    "क्या याद है तुम्हें",
    "forget 2",
])
def test_memory_plugin_routes(text):
    assert MemoryPlugin().can_handle(text) is True


async def test_memory_roundtrip(ctx, memory):
    plugin = MemoryPlugin()
    out = await plugin.execute("remember that the deploy day is Friday", ctx)
    assert "#1" in out
    items = await memory.all()
    assert len(items) == 1 and "Friday" in items[0].content

    recall = await plugin.execute("what do you remember about me", ctx)
    assert "Friday" in recall

    gone = await plugin.execute("forget 1", ctx)
    assert "Forgotten" in gone
    assert await memory.all() == []


async def test_memory_plugin_hindi_answer(ctx):
    out = await MemoryPlugin().execute("याद रखो कि मुझे चाय पसंद है", ctx)
    assert "याद रख लिया" in out


# --- Manager -------------------------------------------------------------------

def test_manager_returns_all_claimants_sorted():
    pm = routing_manager()
    names = [p.name for p in pm.find_handlers("what time is it and check cpu")]
    assert {"time", "system_info"} <= set(names)


def test_manager_survives_broken_plugin():
    class Broken:
        name = "broken"
        description = ""
        priority = 0

        def can_handle(self, text):
            raise RuntimeError("nope")

        async def execute(self, text, ctx):  # pragma: no cover
            return ""

    pm = PluginManager([Broken(), TimePlugin()])
    assert [p.name for p in pm.find_handlers("what time")] == ["time"]
