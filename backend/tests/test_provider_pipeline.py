"""Provider pipeline regressions: encrypted Gemini setup through WebSocket chat,
model-capability filtering, honest status, CORS/auth and the local Ollama contract.
All provider transports are MockTransport; no real keys or external API calls.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai_engine.cloud_client import CloudProviderError, OpenAICompatibleClient
from ai_engine.model_catalog import GEMINI_DEFAULT_MODEL, GEMINI_TEXT_MODELS
from ai_engine.ollama_client import OllamaClient
from main import create_app
from services.providers import REGISTRY
from tests.conftest import FakeLLM


FAKE_GEMINI_KEY = "AIzaFakeKeyForTestsOnly0123456789"
CHAT_REPLY = "Gemini says hello from its text chat API."


def _sse(text: str) -> bytes:
    frames = [
        {"choices": [{"delta": {"content": text}}]},
        "[DONE]",
    ]
    return "".join(f"data: {frame if isinstance(frame, str) else json.dumps(frame)}\n\n" for frame in frames).encode()


def install_gemini_mock(app, *, reject_key: bool = False, fail_stream: bool = False) -> list[dict]:
    """Replace only the cloud transport factory; provider code still runs unchanged."""
    from httpx import MockTransport

    service = app.state.providers
    original_build = service.build_client
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == f"Bearer {FAKE_GEMINI_KEY}"
        if request.url.path.endswith("/models"):
            requests.append({"path": request.url.path, "operation": "list_models"})
            if reject_key:
                return httpx.Response(
                    401,
                    json={"error": {"message": f"Invalid API key {FAKE_GEMINI_KEY}"}},
                )
            return httpx.Response(200, json={
                "data": [
                    {"id": f"models/{GEMINI_DEFAULT_MODEL}"},
                    {"id": "models/gemini-3.7-flash"},
                    {"id": "models/lyria-realtime-exp"},
                    {"id": "models/text-embedding-004"},
                ]
            })

        payload = json.loads(request.content or b"{}")
        requests.append({
            "path": request.url.path,
            "operation": "chat",
            "model": payload.get("model"),
            "stream": payload.get("stream"),
            "messages": payload.get("messages", []),
        })
        if reject_key:
            return httpx.Response(
                401,
                json={"error": {"message": f"Invalid API key {FAKE_GEMINI_KEY}"}},
            )
        if payload.get("stream") and fail_stream:
            return httpx.Response(503, json={"error": {"message": "temporary outage"}})
        if payload.get("stream"):
            return httpx.Response(200, content=_sse(CHAT_REPLY), headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "VEDNIX_PROVIDER_OK"}}]})

    def build_client(provider, row, *, settings, for_verification=False):
        if provider != "gemini":
            return original_build(provider, row, settings=settings, for_verification=for_verification)
        key = service._decrypt(row)
        http = httpx.AsyncClient(
            transport=MockTransport(handler),
            base_url=REGISTRY["gemini"].base_url,
            timeout=httpx.Timeout(5.0),
        )
        client = OpenAICompatibleClient(
            key,
            row.model_override or settings.gemini_model,
            base_url=REGISTRY["gemini"].base_url,
            provider_name="Google Gemini",
            timeout=5.0,
            health_ttl=0.0,
            static_models=list(REGISTRY["gemini"].static_models),
            supported_models=list(REGISTRY["gemini"].static_models),
            vision=True,
            client=http,
        )
        # Test transport is owned by this constructed adapter, just as the
        # production adapter owns its live AsyncClient.
        client._owns_client = True
        return client

    service.build_client = build_client
    return requests


OPENROUTER_TEST_KEY = "sk-or-test-key-without-provider-credentials"
GROK_MODEL = "x-ai/grok-4.20"


def install_openrouter_mock(app) -> list[dict]:
    """Drive the configured OpenRouter provider through a mock transport."""
    from httpx import MockTransport

    service = app.state.providers
    original_build = service.build_client
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == f"Bearer {OPENROUTER_TEST_KEY}"
        if request.url.path.endswith("/models"):
            requests.append({"operation": "list_models"})
            return httpx.Response(200, json={"data": [
                {"id": REGISTRY["openrouter"].default_model},
                {"id": GROK_MODEL},
                {"id": "openai/tts-1"},
                {"id": "x-ai/grok-4.20-voice"},
            ]})
        payload = json.loads(request.content or b"{}")
        requests.append({
            "operation": "chat", "model": payload.get("model"),
            "stream": payload.get("stream"), "messages": payload.get("messages", []),
        })
        if payload.get("stream"):
            return httpx.Response(200, content=_sse("Grok replies through OpenRouter."),
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "VEDNIX_PROVIDER_OK"}}]})

    def build_client(provider, row, *, settings, for_verification=False):
        if provider != "openrouter":
            return original_build(
                provider, row, settings=settings, for_verification=for_verification
            )
        key = service._decrypt(row) if row else ""
        if not key:
            return None
        http = httpx.AsyncClient(
            transport=MockTransport(handler), base_url=REGISTRY["openrouter"].base_url,
            timeout=httpx.Timeout(5.0),
        )
        client = OpenAICompatibleClient(
            key, (row.model_override if row else None) or REGISTRY["openrouter"].default_model,
            base_url=REGISTRY["openrouter"].base_url, provider_name="OpenRouter",
            timeout=5.0, health_ttl=0.0,
            static_models=list(REGISTRY["openrouter"].static_models),
            supported_models=list(REGISTRY["openrouter"].static_models), client=http,
        )
        client._owns_client = True
        return client

    service.build_client = build_client
    return requests


def read_until(ws, terminal: str = "message_done") -> list[dict]:
    frames = []
    while True:
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get("type") == terminal:
            return frames


def test_gemini_end_to_end_provider_routes_and_websocket(settings):
    with TestClient(create_app(settings=settings)) as client:
        calls = install_gemini_mock(client.app)

        saved = client.put("/api/providers/gemini/key", json={"api_key": FAKE_GEMINI_KEY})
        assert saved.status_code == 200, saved.text
        assert FAKE_GEMINI_KEY not in saved.text
        assert saved.json()["status"] == "unverified"
        assert saved.json()["enabled"] is False

        catalog = client.get("/api/providers/catalog")
        assert catalog.status_code == 200
        gemini_card = next(p for p in catalog.json()["providers"] if p["id"] == "gemini")
        assert gemini_card["default_model"] == GEMINI_DEFAULT_MODEL
        assert "models/lyria-realtime-exp" not in gemini_card["models"]

        verified = client.post("/api/providers/gemini/verify")
        assert verified.status_code == 200, verified.text
        verification = verified.json()
        assert verification["connected"] is True
        assert verification["verified"] is True
        assert verification["enabled"] is True
        assert verification["verification_model"] == GEMINI_DEFAULT_MODEL
        assert GEMINI_DEFAULT_MODEL in verification["models"]
        assert not any("lyria" in model.lower() for model in verification["models"])
        assert FAKE_GEMINI_KEY not in verified.text

        # A deliberate disable remains disabled when re-tested; verified
        # re-enable is explicit.
        disabled = client.post("/api/providers/gemini/toggle", json={"enabled": False})
        assert disabled.status_code == 200 and disabled.json()["enabled"] is False
        retested = client.post("/api/providers/gemini/verify").json()
        assert retested["connected"] is True and retested["enabled"] is False
        enabled = client.post("/api/providers/gemini/toggle", json={"enabled": True})
        assert enabled.status_code == 200 and enabled.json()["enabled"] is True

        priority = client.put("/api/providers/priority", json={"order": ["gemini", "ollama"]})
        assert priority.status_code == 200
        assert priority.json()["priority"][0] == "gemini"

        configured = client.get("/api/providers")
        assert configured.status_code == 200
        gemini_row = next(p for p in configured.json()["providers"] if p["provider"] == "gemini")
        assert gemini_row["enabled"] and gemini_row["verified"] and gemini_row["has_key"]
        assert FAKE_GEMINI_KEY not in configured.text

        models = client.get("/api/models", params={"provider": "gemini"})
        assert models.status_code == 200
        model_data = models.json()
        assert model_data["default"] == GEMINI_DEFAULT_MODEL
        assert GEMINI_DEFAULT_MODEL in model_data["available"]
        assert "gemini-3.7-flash" in model_data["available"]
        assert "models/lyria-realtime-exp" not in model_data["available"]
        assert "text-embedding-004" not in model_data["available"]
        assert model_data["chat_available"] is True

        list_requests_before_status = sum(call["operation"] == "list_models" for call in calls)
        health = client.get("/api/health").json()
        assert health["backend_online"] is True
        assert health["ollama_available"] is False
        assert health["provider_verified"] is True
        assert health["model_available"] is True
        assert health["chat_available"] is True
        assert health["provider"] == "Google Gemini"

        system = client.get("/api/system/status").json()
        assert system["backend_online"] is True
        assert system["chat_available"] is True
        assert system["ollama"]["running"] is False
        assert any(p["provider"] == "gemini" and p["chat_available"] for p in system["providers"])
        assert sum(call["operation"] == "list_models" for call in calls) == list_requests_before_status

        ollama = client.get("/api/providers/ollama/status").json()
        assert ollama["running"] is False
        assert ollama["chat_available"] is False
        assert ollama["detail"]

        # This is the same websocket route and router used by the browser.
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({
                "type": "user_message", "content": "hi", "conversation_id": None,
                "provider": "gemini", "model": GEMINI_DEFAULT_MODEL, "temperature": 0.0,
            })
            frames = read_until(ws)
        reply = "".join(f["content"] for f in frames if f["type"] == "token")
        assert reply == CHAT_REPLY

        # Return to default priority so automatic mode first tries local Ollama.
        # It then skips the unavailable engine and visibly labels the cloud
        # handoff instead of pretending that a local model answered.
        client.put("/api/providers/priority", json={"order": ["ollama", "gemini"]})
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "content": "hi", "provider": None, "model": None})
            auto_frames = read_until(ws)
        auto_reply = "".join(f["content"] for f in auto_frames if f["type"] == "token")
        assert "Earlier provider unavailable" in auto_reply
        assert "Google Gemini" in auto_reply and CHAT_REPLY in auto_reply

        chat_requests = [call for call in calls if call["operation"] == "chat"]
        assert any(
            call["model"] == GEMINI_DEFAULT_MODEL and call["stream"] is True
            for call in chat_requests
        )
        assert any(call["path"].endswith("/chat/completions") for call in chat_requests)
        assert GEMINI_TEXT_MODELS[0] == GEMINI_DEFAULT_MODEL


def test_openrouter_grok_key_verification_model_catalog_and_websocket(settings):
    with TestClient(create_app(settings=settings)) as client:
        calls = install_openrouter_mock(client.app)
        saved = client.put(
            "/api/providers/openrouter/key", json={"api_key": OPENROUTER_TEST_KEY}
        )
        assert saved.status_code == 200, saved.text
        assert OPENROUTER_TEST_KEY not in saved.text
        assert saved.json()["has_key"] is True

        verified = client.post("/api/providers/openrouter/verify")
        assert verified.status_code == 200, verified.text
        assert verified.json()["connected"] is True
        assert verified.json()["enabled"] is True
        assert verified.json()["verification_model"] == REGISTRY["openrouter"].default_model
        assert OPENROUTER_TEST_KEY not in verified.text

        configured = client.get("/api/providers")
        row = next(item for item in configured.json()["providers"] if item["provider"] == "openrouter")
        assert row["verified"] and row["enabled"] and row["has_key"]
        assert OPENROUTER_TEST_KEY not in configured.text

        catalog = client.get("/api/providers/catalog").json()
        card = next(item for item in catalog["providers"] if item["id"] == "openrouter")
        assert GROK_MODEL in card["models"]
        models = client.get("/api/models", params={"provider": "openrouter"}).json()
        assert models["chat_available"] and models["model_available"]
        assert GROK_MODEL in models["available"]
        assert "openai/tts-1" not in models["available"]
        assert "x-ai/grok-4.20-voice" not in models["available"]

        assert client.put(
            "/api/providers/priority", json={"order": ["openrouter", "ollama"]}
        ).status_code == 200
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({
                "type": "user_message", "content": "hi", "provider": "openrouter",
                "model": GROK_MODEL, "temperature": 0.0,
            })
            frames = read_until(ws)
        reply = "".join(frame["content"] for frame in frames if frame["type"] == "token")
        assert reply == "Grok replies through OpenRouter."
        assert any(
            call.get("model") == GROK_MODEL and call.get("stream") is True
            for call in calls if call["operation"] == "chat"
        )


def test_gemini_verification_failure_is_safe_and_not_enabled(settings):
    with TestClient(create_app(settings=settings)) as client:
        install_gemini_mock(client.app, reject_key=True)
        rejected_model = client.put(
            "/api/providers/gemini/key",
            json={"api_key": FAKE_GEMINI_KEY, "model": "models/lyria-realtime-exp"},
        )
        assert rejected_model.status_code == 422
        assert FAKE_GEMINI_KEY not in rejected_model.text
        oversized_key = "AIza" + "X" * 600
        malformed = client.put("/api/providers/gemini/key", json={"api_key": oversized_key})
        assert malformed.status_code == 422
        assert oversized_key not in malformed.text

        saved = client.put("/api/providers/gemini/key", json={"api_key": FAKE_GEMINI_KEY})
        assert saved.status_code == 200 and FAKE_GEMINI_KEY not in saved.text

        result = client.post("/api/providers/gemini/verify")
        assert result.status_code == 200
        assert result.json()["connected"] is False
        assert result.json()["enabled"] is False
        assert "API key rejected" in result.json()["detail"]
        assert FAKE_GEMINI_KEY not in result.text

        listing = client.get("/api/providers")
        row = next(p for p in listing.json()["providers"] if p["provider"] == "gemini")
        assert row["status"] == "failed" and row["enabled"] is False
        assert FAKE_GEMINI_KEY not in listing.text
        cannot_enable = client.post("/api/providers/gemini/toggle", json={"enabled": True})
        assert cannot_enable.status_code == 409
        assert FAKE_GEMINI_KEY not in cannot_enable.text


def test_legacy_provider_status_detail_redacts_stored_api_key(settings):
    from sqlalchemy import select
    from memory.models import ProviderKey

    with TestClient(create_app(settings=settings)) as client:
        client.put("/api/providers/gemini/key", json={"api_key": FAKE_GEMINI_KEY})

        async def seed_legacy_detail():
            async with client.app.state.providers._sessions() as db:
                row = (await db.execute(
                    select(ProviderKey).where(ProviderKey.provider == "gemini")
                )).scalar_one()
                row.status_detail = f"Legacy upstream error echoed {FAKE_GEMINI_KEY}"
                await db.commit()

        client.portal.call(seed_legacy_detail)
        configured = client.get("/api/providers")
        row = next(item for item in configured.json()["providers"] if item["provider"] == "gemini")
        assert "[redacted]" in row["status_detail"]
        assert FAKE_GEMINI_KEY not in configured.text


def test_selected_gemini_failure_is_reported_and_disables_provider(settings):
    with TestClient(create_app(settings=settings)) as client:
        calls = install_gemini_mock(client.app, fail_stream=True)
        client.put("/api/providers/gemini/key", json={"api_key": FAKE_GEMINI_KEY})
        assert client.post("/api/providers/gemini/verify").json()["connected"] is True

        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({
                "type": "user_message", "content": "hi", "provider": "gemini",
                "model": GEMINI_DEFAULT_MODEL,
            })
            frames = read_until(ws)
        reply = "".join(f["content"] for f in frames if f["type"] == "token")
        assert "Google Gemini could not complete this reply" in reply
        assert "HTTP 503" in reply
        assert "not saved" in reply

        row = next(p for p in client.get("/api/providers").json()["providers"] if p["provider"] == "gemini")
        assert row["status"] == "failed" and row["enabled"] is False
        assert any(call.get("stream") is True for call in calls if call["operation"] == "chat")


def test_credentialed_cors_uses_exact_vercel_origin(settings):
    production_origin = "https://vednix.vercel.app"
    assert production_origin in settings.cors_origins_list
    production = settings.model_copy(update={"cors_origins": production_origin})
    with TestClient(create_app(settings=production, llm_client=FakeLLM())) as client:
        allowed = client.options(
            "/api/providers/gemini/verify",
            headers={
                "Origin": production_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == production_origin
        assert allowed.headers["access-control-allow-credentials"] == "true"
        assert "origin" in {part.strip().lower() for part in allowed.headers["vary"].split(",")}

        denied = client.options(
            "/api/providers/gemini/verify",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
        assert "access-control-allow-origin" not in denied.headers

        with client.websocket_connect("/ws/chat", headers={"origin": production_origin}) as ws:
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/chat", headers={"origin": "https://evil.example"}):
                pass


def test_cors_rejects_wildcard_credentials_configuration():
    from config import Settings

    with pytest.raises(ValueError, match="exact http\\(s\\) origins"):
        _ = Settings(cors_origins="*").cors_origins_list


def test_gemini_model_setting_is_canonical_and_text_only():
    from config import Settings

    assert Settings(gemini_model=f"models/{GEMINI_DEFAULT_MODEL}").gemini_model == GEMINI_DEFAULT_MODEL
    with pytest.raises(ValueError, match="supported Gemini text-generation model"):
        Settings(gemini_model="models/lyria-realtime-exp")


def test_cloud_provider_error_explains_payment_and_redacts_key():
    from ai_engine.cloud_client import _provider_http_error

    error = _provider_http_error(
        "OpenRouter", httpx.Response(402, json={"error": {"message": OPENROUTER_TEST_KEY}}),
        OPENROUTER_TEST_KEY,
    )
    assert "credits or billing balance" in str(error)
    assert OPENROUTER_TEST_KEY not in str(error)


def test_cloud_client_filters_google_non_text_and_rejects_lyria():
    import anyio

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [
                {"id": f"models/{GEMINI_DEFAULT_MODEL}"},
                {"id": "models/lyria-realtime-exp"},
                {"id": "models/text-embedding-004"},
            ]})
        return httpx.Response(400, json={"error": {"message": "bad model"}})

    async def run():
        http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url=REGISTRY["gemini"].base_url,
        )
        adapter = OpenAICompatibleClient(
            FAKE_GEMINI_KEY, GEMINI_DEFAULT_MODEL,
            base_url=REGISTRY["gemini"].base_url,
            provider_name="Google Gemini",
            supported_models=list(GEMINI_TEXT_MODELS),
            static_models=list(GEMINI_TEXT_MODELS),
            client=http,
        )
        models = await adapter.list_models()
        assert models == [GEMINI_DEFAULT_MODEL]
        with pytest.raises(CloudProviderError, match="not a supported text-chat model"):
            await adapter.chat_stream(
                [{"role": "user", "content": "hi"}], 0.0, model="models/lyria-realtime-exp"
            ).__anext__()
        await http.aclose()

    anyio.run(run)


def test_ollama_client_runs_qwen_model_and_returns_real_chat_payload():
    import anyio

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/tags"):
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:3b"}]})
        if request.url.path.endswith("/api/chat"):
            payload = json.loads(request.content)
            captured.update(payload)
            return httpx.Response(200, json={"message": {"content": "Local Qwen answer for hi."}})
        return httpx.Response(404)

    async def run():
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ollama.test")
        ollama = OllamaClient("http://ollama.test", "qwen2.5:3b", client=http, health_ttl=0.0)
        assert await ollama.is_available()
        assert await ollama.list_models() == ["qwen2.5:3b"]
        answer = await ollama.chat([{"role": "user", "content": "hi"}], 0.0)
        assert answer == "Local Qwen answer for hi."
        assert captured["model"] == "qwen2.5:3b"
        assert captured["messages"][-1]["content"] == "hi"
        await http.aclose()

    anyio.run(run)


def test_qwen_local_provider_uses_real_ollama_websocket_pipeline(settings):
    from httpx import MockTransport

    settings = settings.model_copy(update={"ollama_model": "qwen2.5:3b"})
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/tags"):
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:3b"}]})
        if request.url.path.endswith("/api/chat"):
            payload = json.loads(request.content)
            requests.append(payload)
            if payload.get("stream"):
                body = (
                    json.dumps({"message": {"content": "Local Qwen answer."}, "done": False}) + "\n"
                    + json.dumps({"done": True}) + "\n"
                )
                return httpx.Response(200, content=body.encode())
            return httpx.Response(200, json={"message": {"content": "Local chat title"}})
        return httpx.Response(404)

    with TestClient(create_app(settings=settings)) as client:
        router = client.app.state.core.llm

        async def inject_ollama_transport():
            await router._ollama._client.aclose()
            router._ollama._client = httpx.AsyncClient(
                transport=MockTransport(handler), base_url="http://ollama.mock"
            )
            router._ollama.host = "http://ollama.mock"

        client.portal.call(inject_ollama_transport)

        models = client.get("/api/models", params={"provider": "ollama"}).json()
        assert models["available"] == ["qwen2.5:3b"]
        assert models["model_available"] and models["chat_available"]

        health = client.get("/api/health").json()
        assert health["backend_online"] and health["ollama_available"] and health["chat_available"]
        assert health["default_model"] == "qwen2.5:3b"

        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({
                "type": "user_message", "content": "hi", "provider": None,
                "model": "qwen2.5:3b", "temperature": 0.0,
            })
            frames = read_until(ws)
        reply = "".join(frame["content"] for frame in frames if frame["type"] == "token")
        assert reply == "Local Qwen answer."
        assert requests
        assert all(payload["model"] == "qwen2.5:3b" for payload in requests)
        assert any(payload["stream"] for payload in requests)


def test_local_http_auth_keeps_lax_cookies(settings):
    with TestClient(create_app(settings=settings), base_url="http://api.test") as client:
        registered = client.post(
            "/api/auth/register",
            headers={"Origin": "http://localhost:3000"},
            json={"username": "local-auth-user", "password": "correct-horse-battery"},
        )
        assert registered.status_code == 201, registered.text
        cookies = registered.headers.get_list("set-cookie")
        refresh = next(value.lower() for value in cookies if "vednix_rt=" in value)
        csrf = next(value.lower() for value in cookies if "vednix_csrf=" in value)
        assert "samesite=lax" in refresh and "secure" not in refresh
        assert "samesite=lax" in csrf and "secure" not in csrf


def test_https_cross_origin_auth_keeps_secure_refresh_cookie_and_csrf(settings):
    """Default Vercel and Render hostnames are cross-site; the session cookie
    must be Secure/SameSite=None and the SPA must bootstrap its CSRF nonce.
    """
    production_origin = "https://vednix.vercel.app"
    production = settings.model_copy(update={"cors_origins": production_origin})
    with TestClient(create_app(settings=production), base_url="https://api.test") as client:
        registered = client.post(
            "/api/auth/register",
            headers={"Origin": production_origin},
            json={"username": "cross-site-user", "password": "correct-horse-battery"},
        )
        assert registered.status_code == 201, registered.text
        body = registered.json()
        assert body["csrf_token"]
        assert "refresh_token" not in body
        cookie_headers = registered.headers.get_list("set-cookie")
        assert any("vednix_rt=" in value and "httponly" in value.lower()
                   and "secure" in value.lower() and "samesite=none" in value.lower()
                   for value in cookie_headers)
        assert any("vednix_csrf=" in value and "secure" in value.lower()
                   and "samesite=none" in value.lower() for value in cookie_headers)

        # Simulate a page reload: the frontend origin cannot read the API
        # domain's cookie, so it retrieves the nonce from this CORS endpoint.
        csrf = client.get("/api/auth/csrf", headers={"Origin": production_origin})
        assert csrf.status_code == 200
        assert csrf.json()["csrf_token"] == body["csrf_token"]

        refreshed = client.post(
            "/api/auth/refresh",
            headers={"Origin": production_origin, "X-CSRF-Token": csrf.json()["csrf_token"]},
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["user"]["username"] == "cross-site-user"
        assert refreshed.headers["access-control-allow-origin"] == production_origin
        assert refreshed.headers["access-control-allow-credentials"] == "true"
        assert refreshed.json()["csrf_token"]
