#!/usr/bin/env python
"""Import provider API keys into Vednix\'s encrypted vault — never into source.

Why this exists
---------------
A key pasted into a Python/TypeScript file, a README, an issue, or a chat is a
leaked key: anyone with repository read access (or a stale fork) has it. Vednix
therefore reads keys from the environment at run time and keeps them encrypted
at rest. This tool is the one supported way to move a batch of keys from a
throwaway local file into that encrypted store.

Usage (from ``backend/``)::

    python scripts/import_keys.py --file ~/vednix-keys.txt
    python scripts/import_keys.py --stdin          # paste, Ctrl-D to finish
    python scripts/import_keys.py --file keys.txt --verify --dry-run

Accepted line formats (blank lines and ``#`` comments ignored)::

    groq=gsk_...
    openai,sk-proj-...
    deepseek:sk-...
    gsk_...                      # provider auto-detected when unambiguous

Guarantees
----------
* plaintext keys are never printed, logged, or written to the database;
* only ``…a1b2`` fingerprints are shown, exactly like the Settings screen;
* obvious placeholders/example keys are rejected before they touch the vault;
* the same key offered for two providers is rejected instead of duplicated;
* nothing is "verified" here unless you pass ``--verify`` — a stored key is
  still only usable after a real provider capability check.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from config import get_settings  # noqa: E402
from core.crypto import KeyVault, load_or_create_persistent_secret  # noqa: E402
from core.key_validation import provider_for_key, validate_for_provider  # noqa: E402
from memory.db import create_engine_and_session, init_schema  # noqa: E402
from memory.models import ProviderKey  # noqa: E402
from services.providers import REGISTRY, ProviderService  # noqa: E402

_SEPARATORS = ("=", ",", ":", "\t")


class ImportProblem(ValueError):
    """A single input line was rejected; the message is safe to print."""


def parse_lines(text: str) -> list[tuple[str, str]]:
    """Parse ``provider<sep>key`` lines into (provider, key) pairs."""
    pairs: list[tuple[str, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        provider = ""
        key = line
        for separator in _SEPARATORS:
            if separator in line:
                head, _, tail = line.partition(separator)
                if head.strip().lower() in REGISTRY:
                    provider, key = head.strip().lower(), tail.strip()
                    break
        if not provider:
            candidates = [name for name in provider_for_key(key) if name in REGISTRY]
            if len(candidates) != 1:
                hint = ", ".join(candidates) if candidates else "none"
                raise ImportProblem(
                    f"line {number}: cannot tell which provider this key belongs to "
                    f"(possible: {hint}). Write it as `provider=key`."
                )
            provider = candidates[0]
        if not key:
            raise ImportProblem(f"line {number}: no key value after the separator.")
        pairs.append((provider, key))
    return pairs


def screen(pairs: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[str]]:
    """Split input into accepted pairs and human-readable rejections."""
    accepted: list[tuple[str, str]] = []
    problems: list[str] = []
    seen_keys: dict[str, str] = {}
    for provider, key in pairs:
        issues = validate_for_provider(provider, key)
        fingerprint = f"…{key[-4:]}"
        if issues:
            problems.append(f"{provider} {fingerprint}: " + " ".join(issues))
            continue
        if key in seen_keys:
            other = seen_keys[key]
            if other != provider:
                problems.append(
                    f"{provider} {fingerprint}: the identical key was already supplied for "
                    f"'{other}'. One credential per provider — refusing to duplicate it."
                )
            else:
                problems.append(f"{provider} {fingerprint}: duplicate line, skipped.")
            continue
        seen_keys[key] = provider
        accepted.append((provider, key))
    return accepted, problems


def _data_dir(settings) -> Path:
    prefix = "sqlite+aiosqlite:///"
    if settings.database_url.startswith(prefix):
        target = settings.database_url[len(prefix):]
        if target and target != ":memory:":
            return Path(target).parent
    return Path(settings.data_dir or "./data")


async def import_keys(
    pairs: list[tuple[str, str]], *, dry_run: bool = False, verify: bool = False,
) -> dict[str, str]:
    """Encrypt and store the accepted pairs. Returns provider → outcome."""
    settings = get_settings()
    _data_dir(settings).mkdir(parents=True, exist_ok=True)
    engine, sessions = create_engine_and_session(settings.database_url)
    await init_schema(engine)
    try:
        secret = await load_or_create_persistent_secret(
            _data_dir(settings), sessions, settings.secret_key,
        )
        vault = KeyVault(secret)
        outcomes: dict[str, str] = {}
        for provider, key in pairs:
            row = None
            async with sessions() as db:
                row = (
                    await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
                ).scalar_one_or_none()
            if dry_run:
                outcomes[provider] = "valid (dry run: nothing written)"
                continue
            async with sessions() as db:
                row = (
                    await db.execute(select(ProviderKey).where(ProviderKey.provider == provider))
                ).scalar_one_or_none()
                if row is None:
                    row = ProviderKey(provider=provider, key_ciphertext="")
                    db.add(row)
                row.key_ciphertext = vault.encrypt(key)
                row.key_hint = KeyVault.fingerprint(key)
                # A fresh key is never trusted on import: the UI's live check
                # must still verify it before it can answer a chat request.
                row.status = "unverified"
                row.status_detail = ""
                row.verified_at = None
                row.enabled = False
                await db.commit()
            outcomes[provider] = f"encrypted and stored ({KeyVault.fingerprint(key)})"

        if verify and not dry_run and pairs:
            service = ProviderService(sessions, vault)
            for provider, _key in pairs:
                try:
                    result = await service.verify(provider, settings=settings)
                except Exception as exc:  # provider/network failure stays a report line
                    outcomes[provider] += f"; verification failed ({type(exc).__name__})"
                    continue
                outcomes[provider] += (
                    "; verified live" if result.get("connected")
                    else f"; not verified: {result.get('detail', '')[:160]}"
                )
        return outcomes
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import provider API keys into Vednix's encrypted vault.",
        epilog="Keys are read from a file/stdin only — never pass them on the command line, "
               "where they would land in your shell history and process list.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="local file with one key per line")
    source.add_argument("--stdin", action="store_true", help="read keys from stdin")
    parser.add_argument("--dry-run", action="store_true", help="validate only, write nothing")
    parser.add_argument("--verify", action="store_true", help="run a live provider check after import")
    args = parser.parse_args(argv)

    if args.file:
        try:
            text = args.file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read {args.file} ({exc.strerror})", file=sys.stderr)
            return 2
    else:
        text = sys.stdin.read()

    problems: list[str] = []
    try:
        pairs = parse_lines(text)
    except ImportProblem:
        # One bad line must not discard a whole batch: retry line by line and
        # report the offenders individually.
        pairs = []
        for line in text.splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            try:
                pairs.extend(parse_lines(line))
            except ImportProblem as exc:
                problems.append(str(exc))
    if not pairs and not problems:
        print("Nothing to import (no key lines found).")
        return 1

    accepted, screen_problems = screen(pairs)
    problems.extend(screen_problems)
    for problem in problems:
        print(f"rejected  {problem}")
    if not accepted:
        print("No key passed validation; the vault was not touched.")
        return 1

    outcomes = asyncio.run(import_keys(accepted, dry_run=args.dry_run, verify=args.verify))
    for provider, outcome in outcomes.items():
        print(f"accepted  {provider}: {outcome}")
    print(
        "\nReminder: delete the temporary key file now, and never commit it. "
        "Settings → API Keys shows the same fingerprint for each stored key."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
