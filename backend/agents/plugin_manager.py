"""
Plugin router.

♻️ PRESERVED routing philosophy from dev_ai/core/plugin_manager.py, fixing:
  - audit B4 first-match-wins: find_handlers() returns ALL claimants sorted by
    priority, so  "CPU और time बताओ"  gets answered by BOTH plugins.
  - audit B9 silent failures: broken can_handle() is logged, not swallowed.
  - Plugins are still an explicit registry (predictable) — now fast enough to
    stay that way past a dozen plugins.
"""

from __future__ import annotations

from core.logging import get_logger
from agents.base import Plugin

logger = get_logger(__name__)


class PluginManager:
    def __init__(self, plugins: list[Plugin] | None = None) -> None:
        self._plugins: list[Plugin] = list(plugins or [])

    def register(self, plugin: Plugin) -> None:
        self._plugins.append(plugin)

    @property
    def plugins(self) -> list[Plugin]:
        return list(self._plugins)

    def find_handlers(self, text: str) -> list[Plugin]:
        """All plugins that claim this input, highest priority first."""
        matches: list[Plugin] = []
        for plugin in self._plugins:
            try:
                if plugin.can_handle(text):
                    matches.append(plugin)
            except Exception:
                # A broken plugin must never take routing down — but we SEE it now.
                logger.exception("plugin %r crashed in can_handle(); skipping", plugin.name)
        matches.sort(key=lambda p: p.priority, reverse=True)
        return matches
