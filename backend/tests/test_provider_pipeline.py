"""Gemini/Groq provider regressions using deterministic HTTP MockTransport only.

The application code still uses real official endpoints and real capability
requests. Tests inject transport at the adapter boundary; no credentials or live
provider calls are required.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_engine.cloud_client import GeminiClient, GroqClient
from ai_engine.model_catalog import normalize_gemini_model
from ai_engine.provider_error import ProviderError
from main import create_app
from services.providers import REGISTRY

GEMINI_KEY = "AIzaMockKeyForTests0123456789"
GROQ_KEY = "gsk_mock_key_for_provider_tests"
_TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _sse(text: str) -> bytes:
    frames = [
        {"choices": [{"delta": {"content": text}}]},
        "[DONE]",
    ]
    return "".join(
        f"data: {frame if isinstance(frame, str) else json.dumps(frame)}\n\n"
        for frame in frames
    ).encode()


@dataclass
class MockProvider:
    provider: str
    key: str
    model_pages: list[list[dict]]
    text_models: set[str]
    vision_models: set[str] = field(default_factory=set)
    tool_models: set[str] = field(default_factory=set)
    reject_key: bool = False
    catalog_status: int | None = None
    fail_stream: bool = False
    stream_text: str = "Mock provider reply."
    requests: list[dict] = field(default_factory=list)


def gemini_model(model_id: str, methods: list[str] | None = None) -> dict:
    return {
        "name": f"models/{model_id}",
        "baseModelId": model_id,
        "displayName": f"Test {model_id}",
        "supportedGenerationMethods": methods or ["generateContent"],
        "inputTokenLimit": 32768,
        "outputTokenLimit": 8192,
    }


def install_mocks(app, *configs: MockProvider) -> dict[str, MockProvider]:
    service = app.state.providers
    original_build = service.build_client
    by_provider = {item.provider: item for item in configs}

    def handler_for(config: MockProvider):
        def handler(request: httpx.Request) -> httpx.Response:
            if config.provider == "gemini":
                assert config.key not in str(request.url), "Gemini keys must not enter URLs"
                assert request.headers.get("x-goog-api-key") == config.key
            else:
                assert request.headers.get("Authorization") == f"Bearer {config.key}"

            if request.url.path.endswith("/models"):
                config.requests.append({
                    "provider": config.provider,
                    "operation": "list_models",
                    "path": request.url.path,
                    "pageToken": request.url.params.get("pageToken"),
                })
                if config.reject_key:
                    return httpx.Response(401, json={"error": {"message": f"Invalid API key {config.key}"}})
                if config.catalog_status:
                    return httpx.Response(config.catalog_status, json={"error": {"message": "temporary provider outage"}})
                page_token = request.url.params.get("pageToken")
                page_index = 1 if page_token else 0
                if page_index >= len(config.model_pages):
                    return httpx.Response(200, json={"data": []} if config.provider == "groq" else {"models": []})
                rows = config.model_pages[page_index]
                has_more = page_index + 1 < len(config.model_pages)
                if config.provider == "gemini":
                    return httpx.Response(200, json={
                        "models": rows,
                        "nextPageToken": "next-page" if has_more else None,
                    })
                return httpx.Response(200, json={"data": rows})

            if request.url.path.endswith("/chat/completions"):
                payload = json.loads(request.content or b"{}")
                model = payload.get("model", "")
                is_vision = any(
                    isinstance(part, dict) and part.get("type") == "image_url"
                    for message in payload.get("messages", [])
                    for part in (message.get("content", []) if isinstance(message.get("content"), list) else [])
                )
                is_tools = bool(payload.get("tools"))
                config.requests.append({
                    "provider": config.provider,
                    "operation": "chat",
                    "path": request.url.path,
                    "model": model,
                    "stream": bool(payload.get("stream")),
                    "vision": is_vision,
                    "tools": is_tools,
                })
                if config.reject_key:
                    return httpx.Response(401, json={"error": {"message": f"Invalid API key {config.key}"}})
                if is_tools:
                    if model not in config.tool_models:
                        return httpx.Response(400, json={"error": {"message": "Tool calling is not supported for this model."}})
                    return httpx.Response(200, json={"choices": [{"message": {
                        "content": None,
                        "tool_calls": [{"id": "call-test", "type": "function", "function": {"name": "ping", "arguments": "{}"}}],
                    }}]})
                if is_vision and model not in config.vision_models:
                    return httpx.Response(400, json={"error": {"message": "Image input is not supported for this model."}})
                if model not in config.text_models:
                    return httpx.Response(400, json={"error": {"message": f"Model {model} does not support chat completions."}})
                if payload.get("stream"):
                    if config.fail_stream:
                        return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})
                    return httpx.Response(200, content=_sse(config.stream_text), headers={"content-type": "text/event-stream"})
                return httpx.Response(200, json={"choices": [{"message": {"content": "1"}}]})

            return httpx.Response(404, json={"error": {"message": "not found"}})
        return handler

    def build_client(provider, row, *, settings, for_verification=False):
        config = by_provider.get(provider)
        if config is None:
            return original_build(provider, row, settings=settings, for_verification=for_verification)
        key = service._decrypt(row) if row is not None else config.key
        headers = {"Authorization": f"Bearer {key}"}
        if provider == "gemini":
            headers["x-goog-api-key"] = key
        transport = httpx.MockTransport(handler_for(config))
        http = httpx.AsyncClient(
            transport=transport,
            base_url=REGISTRY[provider].base_url,
            headers=headers,
            timeout=httpx.Timeout(5.0),
        )
        client_class = GeminiClient if provider == "gemini" else GroqClient
        model = row.model_override if row is not None and row.model_override else ""
        client = client_class(key, model, timeout=5.0, client=http)
        client._owns_client = True
        return client

    service.build_client = build_client
    return by_provider


def _gemini_config(*, fail_stream: bool = False, reject_key: bool = False) -> MockProvider:
    return MockProvider(
        provider="gemini",
        key=GEMINI_KEY,
        model_pages=[[
            gemini_model("gemini-text-a"),
            gemini_model("gemini-vision-b"),
        ], [gemini_model("gemini-embed-c", ["embedContent"]) ]],
        text_models={"gemini-text-a", "gemini-vision-b"},
        vision_models={"gemini-vision-b"},
        tool_models={"gemini-text-a"},
        reject_key=reject_key,
        fail_stream=fail_stream,
        stream_text="Gemini answered from a live mocked transport.",
    )


def _groq_config(*, fail_stream: bool = False) -> MockProvider:
    return MockProvider(
        provider="groq",
        key=GROQ_KEY,
        model_pages=[[
            {"id": "groq-chat-a", "active": True, "context_window": 32768, "max_completion_tokens": 4096},
            {"id": "whisper-large-v3", "active": True},
            {"id": "groq-inactive", "active": False},
        ]],
        text_models={"groq-chat-a"},
        fail_stream=fail_stream,
        stream_text="Groq answered after compatible-provider failover.",
    )


def _save_and_verify(client: TestClient, provider: str, key: str) -> dict:
    stored = client.put(f"/api/providers/{provider}/key", json={"api_key": key})
    assert stored.status_code == 200, stored.text
    assert key not in stored.text
    verified = client.post(f"/api/providers/{provider}/verify")
    assert verified.status_code == 200, verified.text
    assert key not in verified.text
    assert verified.json()["connected"] is True, verified.text
    return verified.json()


def _read_turn(ws, terminal: str = "message_done") -> list[dict]:
    frames = []
    for _ in range(100):
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get("type") == terminal:
            return frames
    raise AssertionError(f"Did not receive {terminal}.")


def test_catalog_has_only_supported_provider_setup_metadata(settings):
    with TestClient(create_app(settings=settings)) as client:
        result = client.get("/api/providers/catalog")
        assert result.status_code == 200
        providers = result.json()["providers"]
        assert {item["id"] for item in providers} == {"gemini", "groq"}
        assert all("models" not in item for item in providers)
        assert all("models" not in item and "api_key" not in item for item in providers)


def test_gemini_official_paginated_discovery_text_and_vision_filters(settings):
    with TestClient(create_app(settings=settings)) as client:
        mock = install_mocks(client.app, _gemini_config())["gemini"]
        verified = _save_and_verify(client, "gemini", GEMINI_KEY)
        assert verified["verification_model"] == "gemini-text-a"

        text = client.get("/api/models", params={"provider": "gemini", "task": "text"}).json()
        assert text["available"] == ["gemini-text-a"]
        assert len(text["models"]) == 1  # one verified recommendation per provider/task
        assert all(item["available"] is True for item in text["models"])
        assert "gemini-embed-c" not in text["available"]
        assert all(item["capabilities"]["text"] for item in text["models"])
        assert any(item["pageToken"] == "next-page" for item in mock.requests if item["operation"] == "list_models")

        vision = client.get("/api/models", params={"provider": "gemini", "task": "vision"}).json()
        assert vision["available"] == ["gemini-vision-b"]
        assert vision["models"][0]["capabilities"]["vision"] is True
        assert set(vision["models"][0]["checkedCapabilities"]) >= {"text", "vision"}

        # Audio, generation and video are never inferred from model names or
        # generic generateContent support when no adapter-level probe exists.
        for task in ("audio_input", "audio_output", "image_generation", "video"):
            result = client.get("/api/models", params={"provider": "gemini", "task": task})
            assert result.status_code == 200
            assert result.json()["available"] == []

        paths = {item["path"] for item in mock.requests if item["operation"] == "list_models"}
        assert "/v1beta/models" in paths
        chat_paths = {item["path"] for item in mock.requests if item["operation"] == "chat"}
        assert "/v1beta/openai/chat/completions" in chat_paths
        configured = client.get("/api/providers").text
        assert GEMINI_KEY not in configured


def test_groq_live_discovery_hides_non_chat_models(settings):
    with TestClient(create_app(settings=settings)) as client:
        mock = install_mocks(client.app, _groq_config())["groq"]
        verified = _save_and_verify(client, "groq", GROQ_KEY)
        assert verified["verification_model"] == "groq-chat-a"

        text = client.get("/api/models", params={"provider": "groq", "task": "text"}).json()
        assert text["available"] == ["groq-chat-a"]
        assert "whisper-large-v3" not in text["available"]
        assert "groq-inactive" not in text["available"]
        assert len(text["models"]) == 1  # only the recommended compatible chat model is exposed
        assert all(item["available"] for item in text["models"])
        assert not any(item["model"] == "whisper-large-v3" for item in mock.requests if item["operation"] == "chat")
        assert any(item["path"] == "/openai/v1/models" for item in mock.requests if item["operation"] == "list_models")


def test_vision_and_tools_require_real_capability_probes(settings):
    with TestClient(create_app(settings=settings)) as client:
        mock = install_mocks(client.app, _gemini_config())["gemini"]
        _save_and_verify(client, "gemini", GEMINI_KEY)

        vision = client.get("/api/providers/gemini/models", params={"task": "vision"}).json()
        assert vision["available"] == ["gemini-vision-b"]
        assert any(call["vision"] for call in mock.requests if call["operation"] == "chat")

        tools = client.get("/api/providers/gemini/models", params={"task": "tools"}).json()
        assert tools["available"] == ["gemini-text-a"]
        assert all(item["capabilities"]["tools"] for item in tools["models"])
        assert any(call["tools"] for call in mock.requests if call["operation"] == "chat")

        documents = client.get("/api/providers/gemini/models", params={"task": "document_input"}).json()
        assert documents["available"] == ["gemini-text-a"]
        document_model = documents["models"][0]
        assert document_model["capabilities"]["documentInput"] is True
        assert "document_input" in document_model["checkedCapabilities"]


def test_transient_reverification_failure_does_not_disable_a_verified_provider(settings):
    with TestClient(create_app(settings=settings)) as client:
        config = _gemini_config()
        install_mocks(client.app, config)
        _save_and_verify(client, "gemini", GEMINI_KEY)
        config.catalog_status = 503

        result = client.post("/api/providers/gemini/verify").json()
        stored = client.get("/api/providers").json()["providers"][0]
        assert result["connected"] is False and result["verified"] is True
        assert result["enabled"] is True and "temporarily unavailable" in result["detail"]
        assert stored["status"] == "connected" and stored["enabled"] is True


def test_invalid_key_returns_safe_error_and_never_exposes_secret(settings):
    with TestClient(create_app(settings=settings)) as client:
        config = _gemini_config(reject_key=True)
        install_mocks(client.app, config)
        stored = client.put("/api/providers/gemini/key", json={"api_key": GEMINI_KEY})
        assert stored.status_code == 200
        assert GEMINI_KEY not in stored.text
        result = client.post("/api/providers/gemini/verify")
        assert result.status_code == 200
        assert result.json()["connected"] is False
        assert "API key was rejected" in result.json()["detail"]
        assert GEMINI_KEY not in result.text
        assert GEMINI_KEY not in client.get("/api/providers").text


def test_unlisted_or_non_chat_model_cannot_be_selected_for_chat(settings):
    with TestClient(create_app(settings=settings)) as client:
        mock = install_mocks(client.app, _groq_config())["groq"]
        _save_and_verify(client, "groq", GROQ_KEY)
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({
                "type": "user_message", "content": "transcribe this", "provider": "groq",
                "model": "whisper-large-v3",
            })
            frames = _read_turn(ws)
        output = "".join(frame.get("content", "") for frame in frames if frame["type"] == "token")
        assert "non-chat model" in output or "does not support" in output
        # The rejected model is probed through a non-stream check, never used
        # for a user chat stream.
        assert not any(item["model"] == "whisper-large-v3" and item["stream"] for item in mock.requests if item["operation"] == "chat")


def test_provider_failover_happens_before_first_token_and_is_visible(settings):
    with TestClient(create_app(settings=settings)) as client:
        gemini = _gemini_config()
        groq = _groq_config()
        install_mocks(client.app, gemini, groq)
        _save_and_verify(client, "gemini", GEMINI_KEY)
        _save_and_verify(client, "groq", GROQ_KEY)
        gemini.fail_stream = True  # verified successfully; fail only at the user turn
        client.put("/api/providers/priority", json={"order": ["gemini", "groq"]})

        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "content": "hello", "provider": None})
            frames = _read_turn(ws)
        response = "".join(frame.get("content", "") for frame in frames if frame["type"] == "token")
        assert "Earlier provider unavailable" in response
        assert "Groq" in response
        assert "Groq answered after compatible-provider failover." in response

        assert any(item.get("operation") == "chat" and item["provider"] == "gemini" and item["stream"] for item in gemini.requests)
        assert any(item.get("operation") == "chat" and item["provider"] == "groq" and item["stream"] for item in groq.requests)


def test_explicit_provider_selection_is_strict(settings):
    with TestClient(create_app(settings=settings)) as client:
        gemini = _gemini_config()
        groq = _groq_config()
        install_mocks(client.app, gemini, groq)
        _save_and_verify(client, "gemini", GEMINI_KEY)
        _save_and_verify(client, "groq", GROQ_KEY)
        gemini.fail_stream = True  # strict explicit selection must not hand off
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "content": "hello", "provider": "gemini"})
            frames = _read_turn(ws)
        response = "".join(frame.get("content", "") for frame in frames if frame["type"] == "token")
        assert "Google Gemini could not complete this reply" in response
        assert "Groq answered" not in response


def test_explicit_provider_is_not_overridden_when_an_attachment_needs_vision(settings):
    with TestClient(create_app(settings=settings)) as client:
        gemini = _gemini_config()
        groq = _groq_config()
        install_mocks(client.app, gemini, groq)
        _save_and_verify(client, "gemini", GEMINI_KEY)
        _save_and_verify(client, "groq", GROQ_KEY)
        upload = client.post(
            "/api/uploads",
            files=[("files", ("dot.png", _TEST_PNG, "image/png"))],
        )
        assert upload.status_code == 201, upload.text

        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({
                "type": "user_message", "content": "describe this", "provider": "groq",
                "model": "groq-chat-a", "attachments": [upload.json()[0]["id"]],
            })
            frames = _read_turn(ws)

        output = "".join(frame.get("content", "") for frame in frames if frame["type"] == "token")
        assert "groq has no verified" in output
        assert not any(item.get("vision") for item in gemini.requests if item["operation"] == "chat")


def test_expired_preflight_auth_failure_marks_provider_unavailable(settings):
    with TestClient(create_app(settings=settings)) as client:
        config = _gemini_config()
        install_mocks(client.app, config)
        _save_and_verify(client, "gemini", GEMINI_KEY)
        database_path = settings.database_url.split("///", 1)[1]
        with sqlite3.connect(database_path) as db:
            db.execute("UPDATE provider_models SET checked_at = '2000-01-01 00:00:00.000000'")
            db.commit()
        config.reject_key = True

        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "content": "hello", "provider": "gemini"})
            frames = _read_turn(ws)

        output = "".join(frame.get("content", "") for frame in frames if frame["type"] == "token")
        provider = next(row for row in client.get("/api/providers").json()["providers"] if row["provider"] == "gemini")
        assert "API key was rejected" in output
        assert provider["status"] == "failed" and provider["enabled"] is False
        assert GEMINI_KEY not in output


def test_cors_is_exact_credentialed_and_wildcard_is_rejected(settings):
    with TestClient(create_app(settings=settings)) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "https://vednix.vercel.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://vednix.vercel.app"
        assert response.headers["access-control-allow-credentials"] == "true"
        denied = client.options(
            "/api/health",
            headers={"Origin": "https://attacker.invalid", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in denied.headers

    with pytest.raises(ValueError, match="wildcards"):
        _ = type(settings)(cors_origins="*", database_url=settings.database_url).cors_origins_list


def test_gemini_model_normalization_does_not_use_a_static_catalog():
    assert normalize_gemini_model("models/gemini-live-model") == "gemini-live-model"
    assert normalize_gemini_model("gemini-live-model") == "gemini-live-model"


def test_provider_error_redacts_api_keys_and_classifies_quota():
    error = ProviderError.from_http("Groq", 429, f"Quota exceeded for {GROQ_KEY}")
    assert error.retryable is True
    assert error.category == "rate_limit"
    assert GROQ_KEY not in str(error)


def test_custom_live_models_are_not_assumed_available(settings):
    """A candidate model is not returned until the chat operation succeeds."""
    with TestClient(create_app(settings=settings)) as client:
        config = _groq_config()
        config.model_pages[0].insert(0, {"id": "new-unknown-chat", "active": True})
        install_mocks(client.app, config)
        _save_and_verify(client, "groq", GROQ_KEY)
        result = client.get("/api/models", params={"provider": "groq", "task": "text"}).json()
        assert "new-unknown-chat" not in result["available"]
        assert len(result["available"]) == 1
        assert all(item["available"] for item in result["models"])
        assert not any(
            item["model"] == "new-unknown-chat" and item["stream"]
            for item in config.requests if item["operation"] == "chat"
        )
