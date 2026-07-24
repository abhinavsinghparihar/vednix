"""
Plugin contract.

♻️ PRESERVED from dev_ai/plugins/base.py — subclass Plugin, implement
can_handle() + execute(); engine needs no changes to gain capabilities.
Changes: execute() is async, and plugins receive a PluginContext (settings,
long-term memory, logger) so they can do real work without global imports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid import cycles at runtime
    from config import Settings
    from memory.service import MemoryService


@dataclass
class PluginContext:
    settings: "Settings"
    memory: "MemoryService | None" = None


class Plugin(ABC):
    """Every capability (time, system info, recall, files, vision...) is a Plugin.
    The engine never special-cases a capability by name."""

    #: short unique name, e.g. "system_info"
    name: str = "base"
    #: one-line description shown to the user about what this does
    description: str = ""
    #: higher priority wins when several plugins claim the same input
    priority: int = 0

    @abstractmethod
    def can_handle(self, text: str) -> bool:
        """Return True if this plugin should handle the given input.
        Keep it narrow and cheap — it runs for every message."""

    @abstractmethod
    async def execute(self, text: str, ctx: PluginContext) -> str:
        """Handle the input and return a Markdown/plain-text result."""
