"""OllamaClient contract tests — incl. audit B8: error frames must RAISE, not vanish."""

from __future__ import annotations

import json

import httpx
import pytest

from ai_engine.ollama_client import OllamaClient, OllamaError


def make_client(handler, **kwargs) -> OllamaClient:
    transport = httpx.MockTransport(handler)
    injected = httpx.AsyncClient(transport=transport, base_url="http://ollama.test")
    return OllamaClient("http://ollama.test", "qwen2.5:3b", health_ttl=0.0, client=injected, **kwargs)


@pytest.fixture
def routes():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:3b"}, {"name": "llama3.2:3b"}]})
        if request.url.path == "/api/chat" and not body.get("stream"):
            return httpx.Response(200, json={"message": {"content": "pong"}, "done": True})
        if request.url.path == "/api/chat" and body.get("stream"):
            lines = [
                json.dumps({"message": {"content": "Hel"}}),
                json.dumps({"message": {"content": "lo"}}),
                "",  # keep-alives must be skipped
                json.dumps({"message": {"content": ""}, "done": True}),
            ]
            return httpx.Response(200, text="\n".join(lines))
        return httpx.Response(404)

    return handler


async def test_is_available_and_models_sorted(routes):
    client = make_client(routes)
    assert await client.is_available() is True
    assert await client.list_models() == ["llama3.2:3b", "qwen2.5:3b"]


async def test_is_available_false_when_down():
    transport = httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("down")))
    injected = httpx.AsyncClient(transport=transport, base_url="http://down.test")
    client = OllamaClient("http://down.test", "m", health_ttl=0.0, client=injected)
    assert await client.is_available() is False


async def test_chat_nonstreaming(routes):
    client = make_client(routes)
    assert await client.chat([], 0.7) == "pong"


async def test_chat_stream_yields_chunks_and_stops_at_done(routes):
    client = make_client(routes)
    chunks = [c async for c in client.chat_stream([], 0.7)]
    assert chunks == ["Hel", "lo"]


async def test_error_frame_raises_instead_of_vanishing():
    """Audit B8 regression: the original silently dropped such frames."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=json.dumps({"error": "model 'nope' not found"}))

    client = make_client(handler)
    with pytest.raises(OllamaError, match="not found"):
        _ = [c async for c in client.chat_stream([], 0.7)]


async def test_transport_error_raises_ollama_error():
    transport = httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    injected = httpx.AsyncClient(transport=transport, base_url="http://down.test")
    client = OllamaClient("http://down.test", "m", health_ttl=0.0, client=injected)
    with pytest.raises(OllamaError):
        await client.chat([], 0.7)
