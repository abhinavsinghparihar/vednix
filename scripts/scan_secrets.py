#!/usr/bin/env python3
"""Fail the build if a real-looking provider credential is committed.

This is the guard rail behind the rule in the README: Vednix never stores a
provider key in source. Keys belong in the encrypted vault (Settings → API
Keys, or ``backend/scripts/import_keys.py``), never in a file Git remembers.

Run locally with ``python scripts/scan_secrets.py``; CI runs it on every push.
Exit codes: 0 = clean, 1 = suspected credential found.

Only *candidates* are reported, masked, and limited to patterns that providers
actually issue. Deliberate fakes in fixtures are allowed when they announce
themselves with mock/test/fake/example/placeholder/dummy in the value.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (label, pattern). Kept in sync with backend/core/key_validation.py shapes.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("groq", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("openai-project", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}")),
    ("openrouter", re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}")),
    ("anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("xai", re.compile(r"\bxai-[A-Za-z0-9]{20,}")),
    ("nvidia", re.compile(r"\bnvapi-[A-Za-z0-9_-]{20,}")),
    ("perplexity", re.compile(r"\bpplx-[A-Za-z0-9]{20,}")),
    ("cerebras", re.compile(r"\bcsk-[A-Za-z0-9]{20,}")),
    ("google", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    # Generic legacy OpenAI/DeepSeek shape; 32+ chars keeps prose out.
    ("openai-legacy", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
)

# A value that says out loud it is a fake is a fixture, not a leak.
FIXTURE_MARKERS = ("mock", "test", "fake", "example", "placeholder", "dummy", "sample", "redacted")

SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".mp4", ".db", ".sqlite3",
}
SKIP_PARTS = {"node_modules", ".git", ".next", ".venv", "venv", "dist", "build", "data"}


def tracked_files() -> list[Path]:
    """Files Git knows about — the only ones that can leak from the repo."""
    try:
        output = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
        ).stdout
        files = [ROOT / name for name in output.decode("utf-8", "replace").split("\0") if name]
        return [path for path in files if path.is_file()]
    except (subprocess.CalledProcessError, OSError):
        # Not a git checkout (tarball, CI artifact): walk instead.
        found: list[Path] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
                continue
            found.append(path)
        return found


def _is_fixture(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in FIXTURE_MARKERS)


def scan_text(text: str) -> list[tuple[str, str]]:
    """Return (label, masked value) for every credential-shaped match."""
    findings: list[tuple[str, str]] = []
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if _is_fixture(value):
                continue
            findings.append((label, f"{value[:5]}…{value[-4:]}"))
    return findings


def scan(paths: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        if path.suffix.lower() in SKIP_SUFFIXES or any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, masked in scan_text(line):
                problems.append(f"{path.relative_to(ROOT)}:{line_number}: {label} credential {masked}")
    return problems


def main() -> int:
    problems = scan(tracked_files())
    if problems:
        print("Suspected provider credentials found in tracked files:\n", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nRemove the value, rotate the key at the provider, and import it with "
            "`backend/scripts/import_keys.py` instead.\n",
            file=sys.stderr,
        )
        return 1
    print("Secret scan clean: no provider credentials in tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
