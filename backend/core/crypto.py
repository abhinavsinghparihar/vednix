"""Local secret management + authenticated encryption for stored API keys.

Two jobs, one file:

1. ``secret_key()`` — a machine-local 48-byte secret living at
   ``<data>/secret.key`` (mode 0600). It signs session tokens (core/tokens.py)
   and encrypts provider keys below. Rotating = deleting the file, which
   invalidates all sessions and stored keys at once — the honest nuclear reset.

2. ``KeyVault`` — Fernet (AES-128-CBC + HMAC-SHA256, authenticated) wrapper so
   cloud API keys are never stored in plaintext. The Fernet key is derived
   from the machine secret, so a stolen vednix.db alone reveals nothing.

Stdlib-only fallbacks were considered and rejected on purpose: hand-rolled XOR
"s encryption" would be theater. ``cryptography`` is a declared dependency.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_SECRET_NAME = "secret.key"


def secret_key_path(data_dir: Path) -> Path:
    return data_dir / _SECRET_NAME


def load_or_create_secret(data_dir: Path) -> bytes:
    """Read the machine secret, creating it on first boot (0600, owner-only)."""
    path = secret_key_path(data_dir)
    if path.exists():
        blob = path.read_bytes()
        if len(blob) >= 32:
            return blob
    data_dir.mkdir(parents=True, exist_ok=True)
    blob = os.urandom(48)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, blob)
    finally:
        os.close(fd)
    return blob


class KeyVault:
    """Encrypt/decrypt provider API keys. Never logs, never returns plaintext
    at rest; ``decrypt`` exists only for the server-side provider clients."""

    def __init__(self, secret: bytes) -> None:
        fernet_key = base64.urlsafe_b64encode(hashlib.sha256(b"vednix-keys:" + secret).digest())
        self._fernet = Fernet(fernet_key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:  # tampered db or rotated secret
            raise ValueError("Stored key could not be decrypted (secret rotated?).") from exc

    @staticmethod
    def fingerprint(plaintext: str) -> str:
        """Public, safe-to-display marker: `…a1b2` — enough for the user to
        recognize which key is stored, useless to anyone else."""
        tail = plaintext.strip()[-4:] if plaintext.strip() else "????"
        return f"…{tail}"
