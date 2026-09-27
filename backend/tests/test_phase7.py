"""Authentication, encrypted credentials, onboarding, and account lifecycle regressions.
Provider network behavior is covered by the dedicated mocked provider pipeline tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.crypto import KeyVault
from core.tokens import (
    TokenError,
    hash_password,
    issue_access_token,
    refresh_digest,
    verify_access_token,
    verify_password,
)
from main import create_app
from tests.conftest import FakeLLM


# =============================================================================
# tokens / crypto primitives
# =============================================================================

def test_jwt_roundtrip_tamper_and_type():
    secret = b"s" * 48
    token = issue_access_token(secret, user_id="u1", username="abhinav", role="owner", ttl_seconds=60)
    claims = verify_access_token(secret, token)
    assert claims["sub"] == "u1" and claims["role"] == "owner"

    with pytest.raises(TokenError):  # wrong secret ⇒ signature mismatch
        verify_access_token(b"x" * 48, token)
    with pytest.raises(TokenError):  # tampered payload
        parts = token.split(".")
        verify_access_token(secret, parts[0] + "." + parts[1][:-2] + "xx." + parts[2])
    with pytest.raises(TokenError):  # expired
        dead = issue_access_token(secret, user_id="u1", username="a", role="owner", ttl_seconds=-5)
        verify_access_token(secret, dead)


def test_password_hash_roundtrip_and_wrong():
    digest = hash_password("correct horse 9")
    assert verify_password("correct horse 9", digest)
    assert not verify_password("wrong", digest)
    assert digest != hash_password("correct horse 9")  # salted ⇒ unique per hash


def test_keyvault_roundtrip_fingerprint_and_rotation(tmp_path):
    from core.crypto import load_or_create_secret

    secret = load_or_create_secret(tmp_path)
    vault = KeyVault(secret)
    cipher = vault.encrypt("sk-super-secret-key-1234")
    assert "sk-super-secret" not in cipher
    assert vault.decrypt(cipher) == "sk-super-secret-key-1234"
    assert vault.fingerprint("sk-super-secret-key-1234") == "…1234"

    rotated = KeyVault(load_or_create_secret(tmp_path / "other"))
    with pytest.raises(ValueError):
        rotated.decrypt(cipher)  # db stolen without the machine secret = noise


# =============================================================================
# HTTP auth flow (TestClient drives the full app, lifespan included)
# =============================================================================

def _register(client: TestClient, username="abhinav", password="vednix-pass-1") -> dict:
    resp = client.post("/api/auth/register", json={
        "username": username, "password": password, "display_name": "Abhinav Singh",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_register_login_refresh_logout_and_csrf(settings):
    with TestClient(create_app(settings=settings)) as client:
        body = _register(client)
        assert body["user"]["role"] == "owner"  # first account owns the machine
        assert client.cookies.get("vednix_rt"), "refresh cookie must be set"
        assert client.cookies.get("vednix_csrf"), "csrf cookie must be set"
        access = body["access_token"]

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert me.status_code == 200 and me.json()["username"] == "abhinav"

        # refresh REQUIRES the double-submit CSRF pair
        assert client.post("/api/auth/refresh").status_code == 403
        ok = client.post(
            "/api/auth/refresh",
            headers={"X-CSRF-Token": client.cookies.get("vednix_csrf")},
        )
        assert ok.status_code == 200
        rotated = ok.json()["access_token"]
        assert rotated != access  # fresh access token issued

        # reuse of the OLD refresh digest ⇒ theft path ⇒ 401
        # (jar already holds the rotated cookie, so a second refresh with the
        # same jar is legal — the theft check is covered at the service level)
        logout = client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": client.cookies.get("vednix_csrf")},
        )
        assert logout.status_code == 200
        assert client.cookies.get("vednix_rt") is None
        again = client.post(
            "/api/auth/refresh",
            headers={"X-CSRF-Token": "anything"},
        )
        # cookies wiped at logout ⇒ double-submit can't even be established ⇒ 403
        assert again.status_code == 403

        # wrong credentials ⇒ generic 401 (same shape for unknown user)
        bad = client.post("/api/auth/login", json={"username": "abhinav", "password": "nope-nope"})
        assert bad.status_code == 401
        good = client.post("/api/auth/login", json={"username": "abhinav", "password": "vednix-pass-1"})
        assert good.status_code == 200


def test_api_locks_down_after_first_registration(settings):
    with TestClient(create_app(settings=settings)) as client:
        assert client.get("/api/conversations").status_code == 200  # open mode
        body = _register(client)
        assert client.get("/api/conversations").status_code == 401  # locked
        opened = client.get(
            "/api/conversations", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
        assert opened.status_code == 200


def test_wrong_password_lockout(settings):
    with TestClient(create_app(settings=settings)) as client:
        _register(client)
        for _ in range(5):
            resp = client.post("/api/auth/login", json={"username": "abhinav", "password": "bad-pass"})
            assert resp.status_code == 401 and "Wrong username or password" in resp.json()["detail"]
        locked = client.post("/api/auth/login", json={"username": "abhinav", "password": "bad-pass"})
        assert locked.status_code == 401
        assert "Too many failed attempts" in locked.json()["detail"]


def test_ws_requires_token_once_registered(settings):
    with TestClient(create_app(settings=settings)) as client:
        # open mode: ws pings fine
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text('{"type":"ping"}')
            assert ws.receive_json()["type"] == "pong"

        body = _register(client)
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/chat"):
                pass
        assert excinfo.value.code == 4401

        with client.websocket_connect(f"/ws/chat?token={body['access_token']}") as ws:
            ws.send_text('{"type":"ping"}')
            assert ws.receive_json()["type"] == "pong"


def test_validation_rejects_bad_register(settings):
    with TestClient(create_app(settings=settings)) as client:
        short = client.post("/api/auth/register", json={"username": "ab", "password": "long-enough-1"})
        assert short.status_code == 422  # pydantic min_length
        weak = client.post("/api/auth/register", json={"username": "validname", "password": "short"})
        assert weak.status_code == 422


# =============================================================================
# refresh-token reuse detection at the service level (theft ⇒ revoked chain)
# =============================================================================

async def test_refresh_rotation_and_get_user_by_session(db, settings):
    from core.crypto import load_or_create_secret
    import pathlib
    from services.users import UserService, AuthError

    secret = load_or_create_secret(pathlib.Path(settings.database_url.replace("sqlite+aiosqlite:///", "")).parent)
    users = UserService(db[1], secret)
    user = await users.register(username="rotater", password="password-123", ip="t")
    tokens = await users.issue_session_for(user, remember=True, device_label="tests")

    rotated = await users.refresh(refresh_token=tokens.refresh_token)
    assert rotated.refresh_token != tokens.refresh_token
    with pytest.raises(AuthError):
        await users.refresh(refresh_token=tokens.refresh_token)  # old digest is dead

    fetched = await users.get_user_by_session(rotated.session_id)
    assert fetched and fetched.username == "rotater"

    await users.logout(refresh_token=rotated.refresh_token)
    with pytest.raises(AuthError):
        await users.refresh(refresh_token=rotated.refresh_token)  # revoked


# =============================================================================
# Data wipe and system status
# =============================================================================

def test_wipe_data_erases_chats_and_memories(settings):
    """The privacy wipe survived the guest retirement — every signed-in user
    gets the same one-button local amnesia."""
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        remember = client.post("/api/memory", json={"content": "vednix likes chai"})
        assert remember.status_code in (200, 201)
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text('{"type":"user_message","content":"temp history"}')
            ws.receive_json()
            ws.receive_json()
            for _ in range(12):
                if ws.receive_json()["type"] == "message_done":
                    break
        assert len(client.get("/api/conversations").json()) == 1
        wiped = client.post("/api/onboarding/wipe-data").json()
        assert wiped["conversations_deleted"] >= 1 and wiped["memories_deleted"] >= 1
        assert len(client.get("/api/conversations").json()) == 0
        assert client.get("/api/memory").json() in ({}, [], {"memory": [], "items": []}) or \
            len((client.get("/api/memory").json() or {}).get("items", [])) == 0


def test_system_status_is_provider_neutral(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        status = client.get("/api/system/status").json()
        assert status["cpu"]["cores"] >= 1
        assert status["db_bytes"] > 0
        assert status["counts"]["conversations"] == 0
        assert status["providers"] == []
        health = client.get("/api/health").json()
        assert health["status"] == "ok"
        assert health["chat_available"] is True
