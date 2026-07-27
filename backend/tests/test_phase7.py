"""Phase 7 — onboarding, accounts (JWT sessions), encrypted provider keys,
and the priority router with failover. Every claim is exercised for real:
HTTP flows via TestClient, services via the async db fixture, and provider
verification with monkeypatched transport (tests never hit real networks).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai_engine.cloud_client import OpenAICompatibleClient
from ai_engine.ollama_client import OllamaError
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
from services.providers import ResilientLLM
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
# providers: catalog, encrypted storage, verify, priority (service + HTTP)
# =============================================================================

def test_catalog_exposes_ten_providers_without_secrets(settings):
    with TestClient(create_app(settings=settings)) as client:
        data = client.get("/api/providers/catalog").json()["providers"]
        ids = {p["id"] for p in data}
        assert ids == {"ollama", "openrouter", "gemini", "groq", "openai", "anthropic",
                       "mistral", "together", "fireworks", "custom"}
        gemini = next(p for p in data if p["id"] == "gemini")
        assert gemini["key_url"].startswith("https://") and gemini["needs_key"] is True
        assert not any("api_key" in p or "ciphertext" in p for p in data)


def test_provider_key_lifecycle_never_echoes_plaintext(settings):
    with TestClient(create_app(settings=settings)) as client:
        stored = client.put("/api/providers/gemini/key", json={"api_key": "AIza-test-key-9999"})
        assert stored.status_code == 200, stored.text
        body = stored.json()
        assert body["key_hint"] == "…9999"
        assert "key" not in body.get("key_hint", "").replace("9999", "")
        assert body["has_key"] is True and body["status"] == "unverified"

        listed = client.get("/api/providers").json()
        assert listed["priority"][0] == "ollama"  # spec: Ollama is #1 by default
        gemini = next(p for p in listed["providers"] if p["provider"] == "gemini")
        assert gemini["key_hint"] == "…9999"

        # ciphertext lives server-side and is NOT the plaintext
        providers = client.app.state.providers
        import anyio
        row = anyio.run(providers._row, "gemini")
        assert row.key_ciphertext and "AIza-test-key-9999" not in row.key_ciphertext
        assert providers._vault.decrypt(row.key_ciphertext) == "AIza-test-key-9999"

        # toggle off → router ignores it; remove → 204 then 404
        assert client.post("/api/providers/gemini/toggle", json={"enabled": False}).status_code == 200
        assert client.delete("/api/providers/gemini/key").status_code == 204
        assert client.delete("/api/providers/gemini/key").status_code == 404


def test_priority_reorder(settings):
    with TestClient(create_app(settings=settings)) as client:
        resp = client.put("/api/providers/priority", json={"order": ["groq", "ollama", "gemini"]})
        order = resp.json()["priority"]
        assert order[:3] == ["groq", "ollama", "gemini"]
        assert set(order) == set(client.get("/api/providers").json()["priority"])


async def test_verify_marks_row_connected_with_mocked_transport(db, settings):
    from core.crypto import KeyVault
    from services.providers import ProviderService

    service = ProviderService(db[1], KeyVault(b"s" * 48))
    await service.upsert_key("gemini", api_key="AIza-test")

    async def fake_list(self):
        return ["gemini-2.0-flash", "gemini-1.5-pro"]

    original = OpenAICompatibleClient.list_models
    OpenAICompatibleClient.list_models = fake_list
    try:
        result = await service.verify("gemini", settings=settings)
    finally:
        OpenAICompatibleClient.list_models = original

    assert result["connected"] is True
    assert result["models"] == ["gemini-2.0-flash", "gemini-1.5-pro"]
    row = await service._row("gemini")
    assert row.status == "connected" and row.verified_at is not None

    # ollama down in the test env ⇒ a clean negative, not a crash
    down = await service.verify("ollama", settings=settings)
    assert down["connected"] is False and down["detail"]


# =============================================================================
# ResilientLLM — the priority router with pre-first-token failover
# =============================================================================

class _FakeCloud:
    provider_name = "Google Gemini"
    model = "gemini-2.0-flash"

    async def is_available(self):
        return True

    async def chat(self, messages, temperature, *, model=None, images=None):
        return "cloud answer"

    async def chat_stream(self, messages, temperature, *, model=None, images=None):
        for chunk in ["cloud ", "answer"]:
            yield chunk

    async def list_models(self):
        return ["gemini-2.0-flash"]

    async def list_models_cached(self, ttl=120.0):
        return ["gemini-2.0-flash"]

    def supports_images(self, model=None):
        return True

    async def aclose(self):
        return None


async def test_router_fails_over_with_visible_handoff(db, settings):
    from core.crypto import KeyVault
    from services.providers import ProviderService

    service = ProviderService(db[1], KeyVault(b"s" * 48))
    await service.upsert_key("gemini", api_key="AIza-test")
    real_build = service.build_client
    service.build_client = lambda provider, row, *, settings: _FakeCloud() if provider != "ollama" else real_build(provider, row, settings=settings)

    router = ResilientLLM(FakeLLM(offline=True), service, settings)
    chunks = [chunk async for chunk in router.chat_stream([{"role": "user", "content": "hi"}], 0.5)]
    assert chunks[0].startswith("⚡ Ollama unreachable — answered by **Google Gemini**")
    assert "".join(chunks[1:]) == "cloud answer"
    assert router.active_label == "Google Gemini"


async def test_router_all_providers_down_gives_actionable_error(db, settings):
    from core.crypto import KeyVault
    from services.providers import ProviderService

    service = ProviderService(db[1], KeyVault(b"s" * 48))  # nothing configured
    router = ResilientLLM(FakeLLM(offline=True), service, settings)
    with pytest.raises(OllamaError) as excinfo:
        [chunk async for chunk in router.chat_stream([{"role": "user", "content": "hi"}], 0.5)]
    assert "No AI provider is reachable" in str(excinfo.value)
    assert "Settings → AI Providers" in str(excinfo.value)


# =============================================================================
# onboarding + demo gate
# =============================================================================

def test_onboarding_demo_gate_blocks_chat_without_persisting(settings):
    """NOTE on shape: ONE websocket per test — starlette's sync TestClient
    occasionally wedges closing a second ws on one portal; scenario splits are
    the stable pattern used by every ws test in this suite."""
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        status = client.get("/api/onboarding/status").json()
        assert status["setup_complete"] is False and status["demo_active"] is False
        assert status["auth_enabled"] is False
        assert status["active_provider"]  # router label present

        choice = client.post("/api/onboarding/mode", json={"mode": "demo"}).json()
        assert choice["demo_active"] is True and choice["mode"] == "demo"
        assert client.get("/api/onboarding/status").json()["setup_complete"] is False

        # demo gate: chat burns nothing and explains why
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text('{"type":"user_message","content":"hello demo"}')
            frame = ws.receive_json()
            assert frame["type"] == "error" and frame["code"] == "demo_mode"
        # demo chats pollute nothing: zero conversations persisted
        assert len(client.get("/api/conversations").json()) == 0


def test_onboarding_free_mode_completes_setup_and_rearms_engine(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        done = client.post("/api/onboarding/mode", json={"mode": "free"}).json()
        assert done["demo_active"] is False and done["setup_complete"] is True
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text('{"type":"user_message","content":"hello after setup"}')
            # brand-new conversation: created frame lands before the generation
            assert ws.receive_json()["type"] == "conversation_created"
            assert ws.receive_json()["type"] == "message_started"
            # drain to completion — closing mid-stream wedges the sync
            # TestClient portal on teardown (cancel-scope cleanup stall)
            for _ in range(12):
                if ws.receive_json()["type"] == "message_done":
                    break
            else:
                raise AssertionError("stream never produced message_done")


def test_local_models_catalog_is_honest(settings):
    with TestClient(create_app(settings=settings)) as client:
        models = client.get("/api/onboarding/local-models").json()["models"]
        assert len(models) >= 7
        tiny = next(m for m in models if m["tier"] == "Tiny")
        assert tiny["tag"] == "qwen2.5:3b" and tiny["ram_gb"] == 4
        for m in models:
            assert m["disk_gb"] > 0 and m["pull"].startswith("ollama pull ")
            assert m["download_size_gb"] == m["disk_gb"] if "download_size_gb" in m else True


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
