"""
Memory plugin — user-controlled long-term recall.

🆕 Revives the original project's dead LongTermMemory (audit D1: 112 lines,
zero callers) as a real, user-facing capability:
    "remember that I prefer chrom chai"      → stores a durable fact
    "याद रखो कि मेरी मीटिंग सोमवार को है"        → same, in Hindi
    "what do you remember about me?"          → recalls
    "forget 3"                                → deletes item #3
Stored facts are also auto-injected into the system prompt (see engine.py).
"""

from __future__ import annotations

import re

from agents.base import Plugin, PluginContext

REMEMBER_RE = re.compile(
    r"^(?:please\s+)?(?:remember(?:\s+that)?|note(?:\s+this)?[.:]?|याद\s+रखो(?:\s+कि)?|ध्यान\s+रखना(?:\s+कि)?)\s+",
    re.IGNORECASE,
)
RECALL_TRIGGERS = (
    "what do you remember", "what did i ask you to remember", "recall", "show memories",
    "kya yaad hai", "tumhe kya yaad", "क्या याद है", "तुम्हें क्या याद",
)
FORGET_RE = re.compile(r"^(?:forget|भूल\s*जाओ)\s*#?(\d+)", re.IGNORECASE)


class MemoryPlugin(Plugin):
    name = "memory"
    description = "Stores and recalls durable facts the user asks to remember."
    priority = 20  # outrank generic triggers

    def can_handle(self, text: str) -> bool:
        lowered = text.lower()
        return bool(REMEMBER_RE.match(text)) or any(t in lowered for t in RECALL_TRIGGERS) or bool(FORGET_RE.match(text))

    async def execute(self, text: str, ctx: PluginContext) -> str:
        if ctx.memory is None:
            return "Long-term memory isn't enabled on this server."

        if match := FORGET_RE.match(text):
            item_id = int(match.group(1))
            forgotten = await ctx.memory.forget(item_id)
            return f"Forgotten memory #{item_id}." if forgotten else f"I don't have a memory #{item_id}."

        if match := REMEMBER_RE.match(text):
            fact = text[match.end():].strip()
            if not fact:
                return "What should I remember? (e.g. *remember that I prefer concise answers*)"
            item_id = await ctx.memory.remember(fact, kind="note")
            if re.search(r"[ऀ-ॿ]", text):
                return f"ठीक है, याद रख लिया (#{item_id}): \"{fact}\""
            return f"Noted — I'll remember that (#{item_id}): \"{fact}\""

        # recall
        items = await ctx.memory.all(limit=20)
        if not items:
            return "I don't have any stored memories yet. Say *remember that …* to teach me something."
        lines = ["Here's what I remember:"]
        lines += [f"{i}. ({item.kind}) {item.content}" for i, item in enumerate(items, 1)]
        lines.append("_Say `forget <number or id>` to delete one._")
        return "\n".join(lines)
