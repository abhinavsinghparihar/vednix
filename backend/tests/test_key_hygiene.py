"""Key hygiene: placeholders are caught, real keys are encrypted, leaks fail CI.

The threat model is concrete: a provider key that lives in a source file is
already leaked. These tests pin down the three guards:

  * ``core.key_validation`` rejects typed examples before they reach the vault;
  * ``scripts/import_keys.py`` stores real keys only as Fernet ciphertext and
    leaves them unverified (the live probe is still the gate);
  * ``scripts/scan_secrets.py`` fails when a credential-shaped string is added
    to a tracked file, while letting deliberate fixtures through.
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys

import pytest
from sqlalchemy import select

from config import get_settings
from core.crypto import KeyVault, load_or_create_persistent_secret
from core.key_validation import (
    detect_placeholder,
    provider_for_key,
    validate_for_provider,
)
from memory.db import create_engine_and_session, init_schema
from memory.models import ProviderKey
from scripts.import_keys import ImportProblem, parse_lines, screen

# The exact family of values this task started with: sk- + abc/123 blocks.
EXAMPLE_KEYS = [
    "sk-abcdef1234567890abcdef1234567890abcdef12",
    "sk-1234abcd1234abcd1234abcd1234abcd1234abcd",
    "sk-ijklmnopqrstuvwxijklmnopqrstuvwxijklmnop",
    "sk-mnopqrstuvwxabcdmnopqrstuvwxabcdmnopqrst",
]
REAL_LOOKING = "sk-proj-Q7f2LmZ0aT9xR4vB1nC6kH3dY8sW5gJ2pU0eA7rN4tM9zX6cV1bK8hD3"


@pytest.mark.parametrize("key", EXAMPLE_KEYS)
def test_typed_example_keys_are_rejected(key):
    reason = detect_placeholder(key)
    assert reason, f"{key[:8]}… should be recognised as a placeholder"
    assert validate_for_provider("openai", key)


def test_a_realistic_key_shape_passes():
    assert detect_placeholder(REAL_LOOKING) is None
    assert validate_for_provider("openai", REAL_LOOKING) == []
    assert provider_for_key(REAL_LOOKING) == ["openai"]


def test_specific_prefixes_beat_the_generic_sk_shape():
    assert provider_for_key("sk-or-v1-9f8e7d6c5b4a39281706f5e4d3c2b1a0") == ["openrouter"]
    assert provider_for_key("gsk_" + "a1B2c3D4e5F6g7H8i9J0kL") == ["groq"]


def test_value_for_the_wrong_provider_is_rejected():
    assert validate_for_provider("groq", REAL_LOOKING)


def test_import_lines_accept_the_common_layouts():
    text = f"openai={REAL_LOOKING}\n# comment\n\ngroq,gsk_a1B2c3D4e5F6g7H8i9J0kL\n"
    pairs = parse_lines(text)
    assert pairs == [
        ("openai", REAL_LOOKING),
        ("groq", "gsk_a1B2c3D4e5F6g7H8i9J0kL"),
    ]


def test_an_ambiguous_bare_key_is_refused():
    with pytest.raises(ImportProblem):
        parse_lines("sk-9f8e7d6c5b4a39281706f5e4d3c2b1a0")


def test_the_same_credential_for_two_providers_is_refused():
    shared = "sk-" + "Q7f2LmZ0aT9xR4vB1nC6kH3dY8sW5gJ2pU0eA7rN4"
    accepted, problems = screen([
        ("openai", shared),
        ("deepseek", shared),
    ])
    assert accepted == [("openai", shared)]
    assert any("already supplied" in problem for problem in problems)


def test_import_encrypts_and_never_stores_plaintext(monkeypatch, tmp_path):
    from scripts import import_keys as importer

    db_path = tmp_path / "import.db"
    monkeypatch.setenv("VEDNIX_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("VEDNIX_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VEDNIX_UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    try:
        outcomes = asyncio.run(importer.import_keys([("openai", REAL_LOOKING)]))
        assert "encrypted and stored" in outcomes["openai"]

        async def read_back():
            engine, sessions = create_engine_and_session(f"sqlite+aiosqlite:///{db_path}")
            await init_schema(engine)
            async with sessions() as db:
                row = (
                    await db.execute(select(ProviderKey).where(ProviderKey.provider == "openai"))
                ).scalar_one()
            secret = await load_or_create_persistent_secret(pathlib.Path(tmp_path / "data"), sessions)
            await engine.dispose()
            return row, secret

        row, secret = asyncio.run(read_back())
        assert row.key_ciphertext and REAL_LOOKING not in row.key_ciphertext
        assert row.key_hint.endswith(REAL_LOOKING[-4:])
        # Import never grants trust: the live probe still has to pass.
        assert row.enabled is False and row.status == "unverified"
        # The server can still decrypt it with the same machine secret.
        assert KeyVault(secret).decrypt(row.key_ciphertext) == REAL_LOOKING
    finally:
        get_settings.cache_clear()


def test_repo_scanner_flags_credentials_but_allows_fixtures():
    spec = importlib.util.spec_from_file_location(
        "scan_secrets", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "scan_secrets.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["scan_secrets"] = module
    spec.loader.exec_module(module)

    assert module.scan_text(f'KEY = "{REAL_LOOKING}"')
    assert module.scan_text("GROQ = 'gsk_a1B2c3D4e5F6g7H8i9J0kL'")
    # Fixtures and docs placeholders stay quiet.
    assert not module.scan_text('openai = "sk-mock_key_for_openai_provider_tests"')
    assert not module.scan_text('"sk-your-key-here"')
    assert not module.scan_text("no credentials in this sentence")
