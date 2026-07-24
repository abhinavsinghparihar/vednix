"""
Explicit plugin registry — add new plugins here.

♻️ PRESERVED from dev_ai/plugins/__init__.py (explicit > magic directory scans).
Plugins are CLASSES now (not import-time instances — audit C6); the engine
core instantiates them once at startup.
"""

from agents.builtin.memory_plugin import MemoryPlugin
from agents.builtin.system_info import SystemInfoPlugin
from agents.builtin.time_plugin import TimePlugin

ALL_PLUGIN_CLASSES = [
    MemoryPlugin,
    SystemInfoPlugin,
    TimePlugin,
]


def build_plugins():
    return [cls() for cls in ALL_PLUGIN_CLASSES]
