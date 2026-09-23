"""Phase 5 tests — OpenRouter provider, web research agent (LangGraph),
Redis limiter, auth middleware. Every network boundary is a MockTransport;
nothing here touches the real internet or a real Redis.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.research import ResearchService, ResearchUnavailable
from agents.research.fetcher import html_to_text
from agents.research.searx import query_searxng
from ai_engine.ollama_client import OllamaError
from ai_engine.openrouter_client import OpenRouterClient
from config import Settings
from core.rate_limit import RedisRateLimiter, RateLimiter, build_rate_limiter
from main import create_app
from tests.conftest import FakeLLM



# --- OpenRouterClient -------------------------------------------------------

def _sse(lines: list[str]) -> bytes:
    return "".join(f"data: {line}\n\n" for line in lines).encode()


def openrouter_client(handler, *, api_key: str = "sk-test") -> OpenRouterClient:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://openrouter.ai/api/v1")
    return OpenRouterClient(api_key, "or-model", client=client, health_ttl=0.0)


async def test_openrouter_chat_roundtrip():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "or-model" and payload["stream"] is False
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello cloud"}}]})

    orc = openrouter_client(handler)
    assert await orc.chat([{"role": "user", "content": "hi"}], 0.5) == "hello cloud"


async def test_openrouter_stream_yields_deltas_and_stops_at_done():
    def handler(request: httpx.Request) -> httpx.Response:
        chunks = [
            json.dumps({"choices": [{"delta": {"content": "Hello "}}]}),
            "not-json",  # malformed lines are logged & skipped, not fatal
            json.dumps({"choices": [{"delta": {"content": "world"}}]}),
            json.dumps({"choices": [{"delta": {}}]}),  # empty delta ignored
            "[DONE]",
            json.dumps({"choices": [{"delta": {"content": "NEVER"}}]}),
        ]
        return httpx.Response(200, content=_sse(chunks), headers={"content-type": "text/event-stream"})

    orc = openrouter_client(handler)
    out = "".join([c async for c in orc.chat_stream([{"role": "user", "content": "hi"}], 0.5)])
    assert out == "Hello world"


async def test_openrouter_http_error_and_error_frame_raise():
    orc_bad_http = openrouter_client(lambda req: httpx.Response(429, json={"error": "rate limited"}))
    with pytest.raises(OllamaError, match="429"):
        await orc_bad_http.chat([{"role": "user", "content": "hi"}], 0.5)

    orc_err_frame = openrouter_client(
        lambda req: httpx.Response(200, json={"error": {"message": "model down"}})
    )
    with pytest.raises(OllamaError, match="OpenRouter error"):
        await orc_err_frame.chat([{"role": "user", "content": "hi"}], 0.5)


async def test_openrouter_missing_key_fails_fast():
    orc = openrouter_client(lambda req: httpx.Response(200, json={}), api_key="")
    assert await orc.is_available() is False
    with pytest.raises(OllamaError, match="key missing"):
        await orc.list_models()


async def test_openrouter_images_use_parts_contract():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "an image"}}]})

    orc = openrouter_client(handler)
    await orc.chat(
        [{"role": "user", "content": "what is this?"}], 0.5, images=["QUJD"]
    )
    parts = captured["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "what is this?"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


# --- SearXNG client -----------------------------------------------------------

def mk_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://searx.local")


async def test_searx_parses_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        return httpx.Response(200, json={"results": [
            {"title": "Vednix docs", "url": "https://docs.vednix.ai", "content": "all about vednix"},
            {"title": "skip me — no url"},
        ]})

    results = await query_searxng("http://searx.local", mk_client(handler), "vednix", count=5)
    assert len(results) == 1 and results[0].title == "Vednix docs"


async def test_searx_unreachable_is_honest_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ResearchUnavailable, match="docker run"):
        await query_searxng("http://searx.local", mk_client(handler), "anything")


async def test_searx_no_results_is_unavailable():
    with pytest.raises(ResearchUnavailable, match="no results"):
        await query_searxng("http://searx.local", mk_client(lambda r: httpx.Response(200, json={"results": []})), "obscure")


# --- page fetch / extraction -----------------------------------------------

def test_html_to_text_drops_boilerplate():
    raw = """
    <html><head><style>body{color:red}</style></head><body>
    <nav>Home | Login | Ads</nav>
    <article><h1>Launch Update</h1><p>The code is GARUDA-77.</p></article>
    <script>track();</script><footer>© nobody</footer>
    </body></html>"""
    text = html_to_text(raw)
    assert "GARUDA-77" in text and "Launch Update" in text
    assert "track()" not in text and "color:red" not in text


# --- ResearchService (LangGraph end-to-end over mock web) -------------------

class _PlannerLLM:
    model = "fake-model"

    async def chat(self, messages, temperature, *, model=None, images=None):
        return '["garuda launch", "q3 rollout"]'


def _fake_web() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/search":
            q = request.url.params["q"]
            return httpx.Response(200, json={"results": [{
                "title": f"Result for {q}", "url": f"https://example.com/{q.replace(' ', '-')}",
                "content": f"snippet about {q}",
            }]})
        return httpx.Response(
            200, text=f"<html><body><article><p>Full page body for {path}.</p></article></body></html>",
            headers={"content-type": "text/html"},
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_research_service_runs_graph_and_cites():
    svc = ResearchService(
        searxng_url="http://searx.local", llm=_PlannerLLM(),
        max_results=3, fetch_pages=2, page_chars=2000, timeout=5.0, client=_fake_web(),
    )
    web = await svc.run("tell me about the garuda launch")
    assert "Web research results" in web.block
    assert "[1]" in web.block and "Result for garuda launch" in web.block
    assert "Full page body for /garuda-launch" in web.block or "snippet about" in web.block
    assert len(web.sources) == 2 and web.sources[0].url.startswith("https://example.com/")
    titles = {s.title for s in web.sources}
    assert any("garuda" in t or "q3" in t for t in titles)


async def test_research_service_all_queries_failing_is_honest():
    def dead(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    svc = ResearchService(
        searxng_url="http://searx.local", llm=None,  # plan falls back to raw question
        max_results=3, fetch_pages=2, timeout=3.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(dead)),
    )
    with pytest.raises(ResearchUnavailable):
        await svc.run("anything")


# --- Redis rate limiter -------------------------------------------------------

class _StubRedis:
    """In-memory stand-in proving the fixed-window INCR/EXPIRE logic contract."""

    def __init__(self) -> None:
        self.kv: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.kv[key] = self.kv.get(key, 0) + 1
        return self.kv[key]

    async def expire(self, key: str, seconds: int) -> None:  # noqa: ARG002
        self.kv.setdefault(f"{key}:ttl", seconds)


async def test_redis_limiter_window_logic():
    limiter = RedisRateLimiter(_StubRedis(), rate=3, per_seconds=60)
    assert [await limiter.allow("ip") for _ in range(4)] == [True, True, True, False]
    assert await limiter.allow("other-ip") is True  # keys independent


async def test_build_rate_limiter_fallbacks():
    assert isinstance(await build_rate_limiter("", rate=1, per_seconds=1), RateLimiter)
    # nothing listens on 6399 → falls back to in-process instead of crashing
    assert isinstance(await build_rate_limiter("redis://127.0.0.1:6399/0", rate=1, per_seconds=1), RateLimiter)


# --- Auth middleware ------------------------------------------------------------

def test_auth_gate_open_by_default(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        assert client.get("/api/conversations").status_code == 200


def test_auth_gate_when_token_set(settings):
    locked = settings.model_copy(update={"auth_token": "s3cr3t"})
    with TestClient(create_app(settings=locked, llm_client=FakeLLM())) as client:
        assert client.get("/api/health").status_code == 200  # open path by design
        assert client.get("/api/conversations").status_code == 401
        assert client.get("/api/conversations", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/api/conversations", headers={"Authorization": "Bearer s3cr3t"}).status_code == 200
        with pytest.raises(Exception):  # websocket closed 4401 before accept
            with client.websocket_connect("/ws/chat"):
                pass


# --- provider selection via the app ----------------------------------------------

def test_provider_switch_env_key_missing_falls_back_to_ollama(settings):
    """Phase 7 router: llm_provider=openrouter WITHOUT a key must NOT build a
    client destined to 401 — the router honestly degrades to Engine-only."""
    cloud = settings.model_copy(update={"llm_provider": "openrouter", "openrouter_api_key": ""})
    with TestClient(create_app(settings=cloud)) as client:  # no llm injection → real wiring
        health = client.get("/api/health").json()
        assert health["provider"] == "unavailable"
        assert health["ollama_available"] is False
        assert health["chat_available"] is False  # no ollama in the test env
        assert health["default_model"] == cloud.ollama_model


def test_provider_switch_env_key_pins_openrouter_first(settings, monkeypatch):
    """With an environment key, OpenRouter is pinned as candidate #1 and the
    router's reported model/label reflect it (no network needed)."""
    cloud = settings.model_copy(
        update={"llm_provider": "openrouter", "openrouter_api_key": "sk-or-test-key"}
    )
    with TestClient(create_app(settings=cloud)) as client:
        health = client.get("/api/health").json()
        assert health["provider"] == "OpenRouter (env)"  # pinned label wins honestly
        assert health["default_model"] == cloud.openrouter_model
        assert health["provider_configured"] is True
        assert health["provider_verified"] is False
        assert health["chat_available"] is False
        models = client.get("/api/models", params={"provider": "openrouter"}).json()
        assert "x-ai/grok-4.20" in models["available"]


def test_openrouter_env_key_pinned_path_streams_grok(settings, monkeypatch):
    """The legacy environment-key route must accept a selected Grok model."""
    model = "x-ai/grok-4.20"
    api_key = "sk-or-pinned-test-key"
    cloud = settings.model_copy(update={
        "llm_provider": "openrouter",
        "openrouter_api_key": api_key,
        "openrouter_model": "openai/gpt-oss-20b:free",
    })
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content or b"{}")
        assert request.headers.get("Authorization") == f"Bearer {api_key}"
        requests.append(payload)
        if payload.get("stream"):
            return httpx.Response(
                200,
                content=_sse([json.dumps({"choices": [{"delta": {"content": "Grok via env key."}}]}), "[DONE]"]),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "Conversation title"}}]})

    original_async_client = httpx.AsyncClient

    def mock_openrouter_client(*args, **kwargs):
        if kwargs.get("base_url") == cloud.openrouter_base_url:
            kwargs["transport"] = httpx.MockTransport(handler)
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_openrouter_client)
    with TestClient(create_app(settings=cloud)) as client:
        models = client.get("/api/models", params={"provider": "openrouter"}).json()
        assert model in models["available"]
        assert models["chat_available"] is False  # no successful generation yet
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({
                "type": "user_message", "content": "hi", "provider": "openrouter",
                "model": model, "temperature": 0.0,
            })
            frames = []
            for _ in range(80):
                frame = ws.receive_json()
                frames.append(frame)
                if frame.get("type") in {"message_done", "error"}:
                    break
        assert "".join(frame.get("content", "") for frame in frames if frame["type"] == "token") == "Grok via env key."
        assert any(request.get("model") == model and request.get("stream") is True for request in requests)
        health = client.get("/api/health").json()
        assert health["provider_verified"] is True
        assert health["chat_available"] is True
        assert api_key not in client.get("/api/health").text


# --- internet research through the WS pipeline -------------------------------------

class _FakeWebResearch:
    async def run(self, question: str, *, depth: str = "quick", on_step=None):
        from agents.research.service import WebContext, WebSource
        return WebContext(
            block='Web research results:\n[1] "Docs" — https://docs.example\nThe answer is 42.\n\n',
            sources=[WebSource(title="Docs", url="https://docs.example")],
        )


class _UnavailableResearch:
    async def run(self, question: str, *, depth: str = "quick", on_step=None):
        raise ResearchUnavailable("SearXNG unreachable at http://localhost:8080. docker run …")


def _collect_turn(client, internet: bool, content: str = "what is the answer?"):
    """One full WS turn inside a `with` — matches the proven test_api pattern."""
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "user_message", "content": content, "internet": internet})
        frames: list[dict] = []
        for _ in range(80):
            frame = ws.receive_json()
            frames.append(frame)
            if frame.get("type") == "message_done":
                break
        else:
            raise AssertionError(f"no message_done; saw {[f.get('type') for f in frames]}")
    tokens = "".join(f.get("content", "") for f in frames if f.get("type") == "token")
    return frames, tokens


def test_ws_internet_injects_web_context_and_cites(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        client.app.state.core.research = _FakeWebResearch()
        try:
            llm: FakeLLM = client.app.state.core.llm
            frames, tokens = _collect_turn(client, internet=True)
            done = frames[-1]
            assert done["sources"] == [{"title": "Docs", "url": "https://docs.example"}]
            fed = llm.calls[0][-1]["content"]
            assert "Web research results" in fed and "The answer is 42." in fed
            states = [f.get("state") for f in frames if f.get("type") == "state_changed"]
            assert "SEARCHING" in states  # orb gets its moment
        finally:
            client.app.state.core.research = None


def test_ws_internet_unavailable_is_honest_guidance(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        client.app.state.core.research = _UnavailableResearch()
        try:
            frames, tokens = _collect_turn(client, internet=True)
            assert "SearXNG unreachable" in tokens
        finally:
            client.app.state.core.research = None


def test_ws_internet_disabled_server_side(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        assert client.app.state.core.research is not None  # default URL builds the service…
        no_web = settings.model_copy(update={"searxng_url": ""})
        with TestClient(create_app(settings=no_web, llm_client=FakeLLM())) as client2:
            assert client2.app.state.core.research is None  # …while "" disables it
            frames, tokens = _collect_turn(client2, internet=True)
            assert "disabled on this server" in tokens
