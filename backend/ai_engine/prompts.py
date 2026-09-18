"""
System-prompt construction — the multilingual core of Vednix AI.

Closes the audit's biggest product gap (§8): the original system prompt was
English-only with no language instruction, so Hindi/Hinglish answers were left
to model luck. Here it is a first-class, explicit, overridable contract.
"""

from __future__ import annotations

from typing import Iterable

from config import Settings

#: The single rule that makes Vednix answer in Hindi / Hinglish / any language.
LANGUAGE_MIRRORING_RULE = (
    "CRITICAL LANGUAGE RULE: Always reply in the exact same language and script "
    "that the user used in their latest message. If they write in Hindi "
    "(Devanagari), reply fully in Hindi (Devanagari). If they write in Hinglish "
    "(Roman-script Hindi), reply in natural Hinglish. If they write in English, "
    "reply in English. For any other language, mirror it exactly. Match the "
    "user's tone and formality. Never switch language or script unless the user "
    "explicitly asks you to. You may use Markdown, tables, and code blocks in "
    "any language; keep code identifiers in English. For Hinglish specifically: "
    "write natural conversational Roman Hindi as a fluent Indian assistant, not "
    "word-for-word translation. Do not use Devanagari in Hinglish mode. Keep "
    "technical terms such as API, backend, deploy and model in English, explain "
    "them briefly in simple Roman Hindi, use respectful 'aap', and avoid awkward "
    "literal phrases. Give a direct answer first, then concise steps or examples."
)

#: Forced-language overrides (per-conversation setting, WS/REST adjustable).
FORCED_LANGUAGE_DIRECTIVES: dict[str, str] = {
    "hi": (
        "FORCE LANGUAGE: Regardless of the user's language, always answer in "
        "Hindi written in Devanagari script. Technical terms may stay in English "
        "where natural (जैसे: API, function, server)."
    ),
    "hinglish": (
        "FORCE LANGUAGE: Regardless of the user's language, always answer in "
        "Hinglish — Hindi written in Roman script mixed naturally with English "
        "words (jaise: 'Main aapke liye ye code bana deta hoon')."
    ),
    "en": "FORCE LANGUAGE: Regardless of the user's language, always answer in English.",
}

SUPPORTED_LANGUAGES = ("auto", "hi", "hinglish", "en")


def build_system_prompt(
    settings: Settings,
    *,
    language: str = "auto",
    memory_facts: Iterable[str] = (),
) -> str:
    """Compose the full system prompt: persona + language contract + remembered facts."""
    parts: list[str] = [settings.default_system_prompt]

    directive = FORCED_LANGUAGE_DIRECTIVES.get(language.lower()) if language != "auto" else None
    parts.append(directive or LANGUAGE_MIRRORING_RULE)

    facts = [f.strip() for f in memory_facts if f and f.strip()]
    if facts:
        block = "\n".join(f"- {fact}" for fact in facts[: settings.memory_context_items])
        parts.append(
            "You remember these facts from previous conversations. Use them naturally "
            "when relevant, never recite them unprompted:\n" + block
        )
    return "\n\n".join(parts)
