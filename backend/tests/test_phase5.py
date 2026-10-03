"""Research agent, rate limiting, and auth middleware regressions.
External services use MockTransport or a local stub; no live credentials are used.
"""

from __future__ import annotations

import asyncio
import httpx
import pytest
from fastapi.testclient import TestClient

from agents.research import ResearchService, ResearchUnavailable
from agents.research.fetcher import html_to_text
from agents.research.searx import query_searxng
from core.rate_limit import RedisRateLimiter, RateLimiter, build_rate_limiter
from main import create_app
from tests.conftest import FakeLLM



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

    def __init__(self):
        self.providers = []

    async def chat(self, messages, temperature, *, model=None, images=None, provider=None):
        self.providers.append(provider)
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


async def test_research_planner_preserves_explicit_provider_selection():
    llm = _PlannerLLM()
    service = ResearchService(searxng_url="http://searx.local", llm=llm, client=_fake_web())
    await service.run("find the launch update", provider="groq")
    assert llm.providers == ["groq"]


async def test_research_callbacks_are_isolated_between_concurrent_turns():
    service = ResearchService(searxng_url="http://searx.local", client=_fake_web())
    observed: dict[str, list[str]] = {"first": [], "second": []}

    async def run(label: str) -> None:
        async def on_step(step: str, detail: str) -> None:
            observed[label].append(step)
        await service.run(f"question {label}", on_step=on_step)

    await asyncio.gather(run("first"), run("second"))
    assert observed["first"] and observed["second"]


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
            assert "Search is temporarily unavailable" in tokens
            assert "answering from model knowledge" in tokens
        finally:
            client.app.state.core.research = None


def test_ws_internet_disabled_server_side(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        assert client.app.state.core.research is not None  # default URL builds the service…
        no_web = settings.model_copy(update={"searxng_url": ""})
        with TestClient(create_app(settings=no_web, llm_client=FakeLLM())) as client2:
            assert client2.app.state.core.research is None  # …while "" disables it
            frames, tokens = _collect_turn(client2, internet=True)
            assert "Search is unavailable on this server" in tokens
            assert "answering from model knowledge" in tokens
