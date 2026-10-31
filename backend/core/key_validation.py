"""Provider-key format validation and placeholder detection.

Used by the offline import tool (``scripts/import_keys.py``) and by tests. It is
deliberately *not* wired into the live "paste a key" endpoint: providers do
change their formats, and a paying user must never be blocked by a stale regex.
The import tool, by contrast, is exactly where a fake or leaked key should be
caught before it is written into the encrypted vault.

Nothing here logs, returns, or stores the secret itself — callers only ever hold
the value transiently and show ``KeyVault.fingerprint`` to humans.
"""

from __future__ import annotations

import math
import re
from collections import Counter

# Public, documented credential shapes (prefix + length only).
PROVIDER_PATTERNS: dict[str, re.Pattern[str]] = {
    "groq": re.compile(r"^gsk_[A-Za-z0-9]{20,}$"),
    "openai": re.compile(r"^sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}$"),
    "openrouter": re.compile(r"^sk-or-v1-[A-Za-z0-9]{20,}$"),
    "anthropic": re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,}$"),
    "deepseek": re.compile(r"^sk-[A-Za-z0-9]{20,}$"),
    "mistral": re.compile(r"^[A-Za-z0-9]{24,64}$"),
    "together": re.compile(r"^[0-9a-f]{40,64}$"),
    "xai": re.compile(r"^xai-[A-Za-z0-9]{20,}$"),
    "nvidia": re.compile(r"^nvapi-[A-Za-z0-9_-]{20,}$"),
    "perplexity": re.compile(r"^pplx-[A-Za-z0-9]{20,}$"),
    "cerebras": re.compile(r"^csk-[A-Za-z0-9]{20,}$"),
    "sambanova": re.compile(r"^(?!sk-)[A-Za-z0-9][A-Za-z0-9_-]{23,}$"),
}

# Providers whose prefix identifies them unambiguously. When one of these
# matches, the loose catch-all shapes above must not claim the same value.
_STRONG_PROVIDERS = {
    "groq", "openai", "openrouter", "anthropic", "deepseek", "xai",
    "nvidia", "perplexity", "cerebras", "together",
}

_REPEATED_UNIT = re.compile(r"(.{6,24}?)\1{1,}")
_HEX_ALPHABET = set("0123456789abcdef")

# Words that only ever appear in documentation, never in a real credential.
_PLACEHOLDER_WORDS = (
    "your", "replace", "example", "sample", "dummy", "placeholder", "changeme",
    "insert", "paste", "xxxx", "todo", "secret-key-here", "api-key", "apikey",
)
# Token blocks that indicate a hand-typed example rather than random material.
_EXAMPLE_BLOCK = re.compile(
    r"^(?:[a-d]{4}|[e-h]{4}|[i-l]{4}|[m-p]{4}|[q-t]{4}|[u-x]{4}|[1-4]{4}|[5-8]{4}|\d{4}|abcd|1234|\w{1,2})$"
)


def _entropy_per_char(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _is_periodic(body: str) -> bool:
    """`abcd1234abcd1234…` — a repeated block, never a real generated key."""
    length = len(body)
    for period in range(1, length // 2 + 1):
        if length % period == 0 and body == body[:period] * (length // period):
            return True
    return False


def _has_repeated_unit(body: str) -> bool:
    """`abcdef1234567890abcdef1234567890…` — a block pasted more than once."""
    return any(len(match.group(0)) >= 12 for match in _REPEATED_UNIT.finditer(body))


def _is_example_alphabet(body: str) -> bool:
    """True when the key is built only from abcd/efgh/…/1234/5678 style blocks."""
    blocks = re.findall(r"[a-z]{4}|\d{4}|[a-z0-9]{1,3}", body.lower())
    return bool(blocks) and all(_EXAMPLE_BLOCK.match(block) for block in blocks)


def detect_placeholder(api_key: str) -> str | None:
    """Return a human reason when a value is obviously not a real credential."""
    value = api_key.strip()
    if not value:
        return "The value is empty."
    if any(word in value.lower() for word in _PLACEHOLDER_WORDS):
        return "The value contains documentation placeholders (for example 'your-key')."
    body = re.sub(r"^[A-Za-z]{2,6}-(?:v1-)?", "", value)
    body = body.replace("-", "").replace("_", "")
    if len(body) < 20:
        return f"The random part is only {len(body)} characters; real keys are longer."
    if _is_periodic(body):
        return "The value repeats one short block — it is a typed example, not random key material."
    if _has_repeated_unit(body):
        return "The value pastes the same block more than once — it is a typed example."
    if _is_example_alphabet(body):
        return "The value is built from abc/123 pattern blocks, which providers never issue."
    if len(set(value)) < 8:
        return "The value uses fewer than eight distinct characters."
    if not set(body.lower()) <= _HEX_ALPHABET and len(set(body)) * 2 < len(body):
        # Legitimate hex credentials are naturally low-diversity; alphanumeric
        # keys recycle a tiny alphabet only when a human typed them.
        return "The value reuses a tiny alphabet — it looks like a typed example."
    if _entropy_per_char(value) < 3.2:
        return (
            f"The character entropy is {_entropy_per_char(value):.2f} bits/char; "
            "issued credentials score well above 3.2."
        )
    return None


def provider_for_key(api_key: str) -> list[str]:
    """Registry provider ids whose documented format matches this value."""
    value = api_key.strip()
    matches = [name for name, pattern in PROVIDER_PATTERNS.items() if pattern.match(value)]
    strong = [name for name in matches if name in _STRONG_PROVIDERS]
    if strong:
        matches = strong
    # `sk-` alone is claimed by OpenAI, DeepSeek, OpenRouter and Anthropic; the
    # more specific prefixes have to win, so drop the losers explicitly.
    if value.startswith("sk-or-v1-"):
        matches = [name for name in matches if name not in {"openai", "deepseek", "anthropic"}]
    elif value.startswith("sk-ant-"):
        matches = [name for name in matches if name not in {"openai", "deepseek"}]
    elif value.startswith("sk-proj-") or value.startswith("sk-svcacct-"):
        matches = [name for name in matches if name == "openai"]
    return matches


def validate_for_provider(provider: str, api_key: str) -> list[str]:
    """Return every problem with this (provider, key) pair; empty means OK."""
    problems: list[str] = []
    placeholder = detect_placeholder(api_key)
    if placeholder:
        problems.append(placeholder)
    pattern = PROVIDER_PATTERNS.get(provider)
    if pattern is None:
        problems.append(
            f"No documented key format is known for '{provider}'. Import it manually "
            "from Settings → API Keys if you trust it."
        )
    elif not pattern.match(api_key.strip()):
        problems.append(f"The value does not match the documented {provider} key format.")
    return problems
