"""Free use — the keyless shared tier — and its safety rails.

Product promise being tested:

  * no API key exists anywhere: none is stored, requested, echoed, or sent as a
    bearer credential;
  * "enabled" still means a real completion *and* a real streamed token were
    produced in a live probe — the same bar a paid provider clears;
  * own keys always win (free use is last in automatic routing);
  * the shared tier is budgeted per rolling hour and can be switched off by the
    operator without touching code.
"""

from __future__ import annotations

import json
import pathlib

import httpx
import pytest

from ai_engine.cloud_client import OpenAICompatibleClient
from ai_engine.provider_error import ProviderError
from core.crypto import KeyVault, load_or_create_secret
from main import create_app
from services.providers import FREE_PROVIDER_ID, REGISTRY, ProviderService
from services.resilient_llm import ResilientLLM
from fastapi.testclient import TestClient


def _sse(text: str) -> bytes:
    frames = [json.dumps({"choices": [{"delta": {"content": text}}]}), "[DONE]"]
    return "".join(f"data: {frame}\n\n" for frame in frames).encode()


class FreeGateway:
    """Deterministic stand-in for the keyless community endpoint."""

    def __init__(self, *, models: tuple[str, ...] = ("free-a", "free-b"), catalog: str = "openai") -> None:
        self.models = list(models)
        # "openai" → a normal /models response; "missing" → 404 (no catalog)
        self.catalog = catalog
        self.requests: list[dict] = []
        self.stream_text = "Free tier reply."

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert "authorization" not in {name.lower() for name in request.headers}, (
            "The keyless free path must never send a bearer credential"
        )
        if request.method == "GET":
            self.requests.append({"operation": "list_models", "path": request.url.path})
            if self.catalog == "missing":
                return httpx.Response(404, json={"error": {"message": "no catalog"}})
            return httpx.Response(200, json={"data": [{"id": model} for model in self.models]})

        payload = json.loads(request.content or b"{}")
        self.requests.append({
            "operation": "chat",
            "model": payload.get("model"),
            "stream": bool(payload.get("stream")),
        })
        if payload.get("stream"):
            return httpx.Response(
                200, content=_sse(self.stream_text), headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "1"}}]})


def _patch_service(service, gateway: FreeGateway) -> None:
    """Inject transport at the adapter boundary, like the paid-provider tests."""
    original_build = service.build_client

    def build_client(provider, row, *, settings, for_verification=False):
        if provider != FREE_PROVIDER_ID:
            return original_build(provider, row, settings=settings, for_verification=for_verification)
        http = httpx.AsyncClient(
            transport=httpx.MockTransport(gateway.handler),
            base_url="https://free.test/v1",
            timeout=httpx.Timeout(5.0),
        )
        selected = row.model_override if row is not None and row.model_override else "free-a"
        client = OpenAICompatibleClient(
            "", selected, provider=FREE_PROVIDER_ID, provider_name="Vednix Free",
            base_url="https://free.test/v1", timeout=5.0, client=http,
        )
        client._owns_client = True
        return client

    service.build_client = build_client


def install_free_gateway(app, gateway: FreeGateway) -> FreeGateway:
    _patch_service(app.state.providers, gateway)
    return gateway


def _free_row(client) -> dict:
    rows = client.get("/api/providers").json()["providers"]
    return next(row for row in rows if row["provider"] == FREE_PROVIDER_ID)


def test_free_use_needs_no_key_and_is_verified_with_a_real_probe(settings):
    with TestClient(create_app(settings=settings)) as client:
        gateway = install_free_gateway(client.app, FreeGateway())

        result = client.post("/api/providers/free/enable")
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["connected"] is True and body["enabled"] is True
        assert body["free"] is True
        assert body["verification_model"] == "free-a"

        row = _free_row(client)
        assert row["has_key"] is False
        assert row["keyless"] is True
        assert row["key_hint"] is None
        assert row["status"] == "connected"

        # A completion AND a streamed token were really produced.
        assert any(item["operation"] == "chat" and item["stream"] is False for item in gateway.requests)
        assert any(item["operation"] == "chat" and item["stream"] is True for item in gateway.requests)

        # Nothing in the API surface echoes a credential field.
        dumped = json.dumps(client.get("/api/providers").json())
        assert "api_key" not in dumped


def test_free_use_falls_back_to_configured_candidates_without_a_catalog(settings):
    settings = settings.model_copy(update={"free_use_models": "free-a, free-b"})
    with TestClient(create_app(settings=settings)) as client:
        install_free_gateway(client.app, FreeGateway(models=(), catalog="missing"))
        result = client.post("/api/providers/free/enable")
        assert result.status_code == 200, result.text
        assert result.json()["connected"] is True
        assert result.json()["verification_model"] == "free-a"


def test_free_use_streams_chat_without_any_credential(settings):
    with TestClient(create_app(settings=settings)) as client:
        gateway = install_free_gateway(client.app, FreeGateway())
        assert client.post("/api/providers/free/enable").json()["connected"] is True

        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "user_message", "content": "hello free tier"})
            chunks: list[str] = []
            for _ in range(60):
                frame = ws.receive_json()
                if frame["type"] == "token":
                    chunks.append(frame["content"])
                if frame["type"] == "message_done":
                    break
        assert "Free tier reply." in "".join(chunks)
        assert any(item["operation"] == "chat" and item["stream"] for item in gateway.requests)


def test_free_use_is_last_in_automatic_routing(settings):
    with TestClient(create_app(settings=settings)) as client:
        priority = client.get("/api/providers").json()["priority"]
    assert priority[-1] == FREE_PROVIDER_ID
    assert len(priority) == len(REGISTRY)


def test_operator_can_disable_free_use_without_code_changes(settings):
    settings = settings.model_copy(update={"free_use_enabled": False})
    with TestClient(create_app(settings=settings)) as client:
        ids = {item["id"] for item in client.get("/api/providers/catalog").json()["providers"]}
        assert FREE_PROVIDER_ID not in ids
        blocked = client.post("/api/providers/free/enable")
        assert blocked.status_code == 422
        assert "turned off" in blocked.json()["detail"]


def test_free_use_hourly_budget_is_enforced(settings):
    with TestClient(create_app(settings=settings)) as client:
        service = client.app.state.providers
        assert service.consume_free_request(limit=2) is True
        assert service.consume_free_request(limit=2) is True
        assert service.consume_free_request(limit=2) is False
        assert service.free_quota_remaining(limit=2) == 0


def test_free_use_metadata_never_requires_a_key():
    spec = REGISTRY[FREE_PROVIDER_ID]
    assert spec.needs_key is False and spec.keyless is True
    assert spec.key_url == ""


@pytest.mark.asyncio
async def test_exhausted_free_budget_explains_the_exit_path(db, settings):
    """A strict free selection fails with a human next step, not a raw error."""
    settings = settings.model_copy(update={"free_use_requests_per_hour": 1})
    _engine, sessions = db
    secret = load_or_create_secret(
        pathlib.Path(settings.database_url.replace("sqlite+aiosqlite:///", "")).parent
    )
    service = ProviderService(sessions, KeyVault(secret))
    _patch_service(service, FreeGateway())
    assert (await service.enable_free(settings=settings))["connected"] is True

    llm = ResilientLLM(service, settings)
    try:
        async for _chunk in llm.chat_stream(
            [{"role": "user", "content": "hello"}], 0.2, provider=FREE_PROVIDER_ID,
        ):
            pass  # consumes the single hourly slot

        with pytest.raises(ProviderError) as excinfo:
            async for _chunk in llm.chat_stream(
                [{"role": "user", "content": "again"}], 0.2, provider=FREE_PROVIDER_ID,
            ):
                pass
        assert excinfo.value.category == "rate_limit"
        assert "free-use limit" in excinfo.value.message
        assert "provider key" in excinfo.value.message
    finally:
        await llm.aclose()
