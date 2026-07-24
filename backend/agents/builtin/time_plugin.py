"""
Time / date plugin.

♻️ PRESERVED from dev_ai/plugins/time_plugin.py.
Fixes: async, localized triggers (audit B6 — English-only substrings missed
Hinglish "time kya hai" and Devanagari "समय"), smart-quote safe, IST-clear label.
"""

from __future__ import annotations

import re
from datetime import datetime

from agents.base import Plugin, PluginContext

# English / Hinglish / Hindi triggers — substring matched on a normalized string.
TRIGGERS = (
    "what time", "current time", "time now", "what's the time", "whats the time",
    "what's the date", "whats the date", "what is the date", "today's date", "todays date",
    "what day is it", "which day", "time kya", "samay kya", "kya samay", "kitne baje",
    "kitna baj", "baj raha", "baj rahi",
    "kya time", "aaj kaun sa din", "aaj ki date", "aaj ka din",
    "समय", "टाइम", "तारीख", "तिथि", "कितने बजे", "बज रहा", "बज रही", "बज गए", "आज कौन सा दिन",
)

_NORMALIZE_RE = re.compile(r"[\u2018\u2019\u201c\u201d]")


class TimePlugin(Plugin):
    name = "time"
    description = "Reports the current local date and time (EN / हिंदी / Hinglish)."
    priority = 10

    def can_handle(self, text: str) -> bool:
        normalized = _NORMALIZE_RE.sub("'", text.lower())
        return any(trigger in normalized for trigger in TRIGGERS)

    async def execute(self, text: str, ctx: PluginContext) -> str:
        now = datetime.now().astimezone()
        if re.search(r"[ऀ-ॿ]", text) or "kya" in text.lower() or "samay" in text.lower():
            # Answer in the user's register — this is the Vednix language contract,
            # applied even to local plugins.
            return now.strftime("अभी **%I:%M %p** बजे हैं — %A, %d %B %Y (%Z).")
        return now.strftime("It's **%I:%M %p** on %A, %d %B %Y (%Z).")
