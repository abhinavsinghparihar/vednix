"""Phase 6 tests — multi-agent deep research (planner → researcher → critic →
refine loop), live agent steps, and the multi_agent WS routing. Mock web +
scriptable LLM; no real internet or LLM touched.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.research import ResearchService
from main import create_app
from tests.conftest import FakeLLM


class ScriptLLM:
    """LLM whose chat() answer depends on which agent is prompting."""

    model = "fake-model"

    def __init__(self, *, plan=None, verdicts: list[dict] | None = None, fail_plan: bool = False) -> None:
        self.plan = plan or ["alpha", "beta"]
        self.verdicts = verdicts or [
            {"verdicts": [{"sub": "alpha", "answered": True}], "follow_ups": []}
        ]
        self.fail_plan = fail_plan
        self.critic_calls = 0
        self.plan_calls = 0

    async def chat(self, messages, temperature, *, model=None, images=None):
        prompt = messages[-1]["content"]
        if "CRITIC agent" in prompt:
            v = self.verdicts[min(self.critic_calls, len(self.verdicts) - 1)]
            self.critic_calls += 1
            return json.dumps(v)
        if "PLANNER agent" in prompt or "JSON array" in prompt:
            self.plan_calls += 1
            if self.fail_plan:
                raise RuntimeError("planner brain dead")
            return json.dumps(self.plan)
        return "note"


def mock_web(*, pages_per_query: int = 1, connect_error_on: tuple[str, ...] = ()) -> httpx.AsyncClient:
    """SearXNG + article server in one handler; remembers every query searched."""
    handler_obj = type("H", (), {"queries": []})

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/search":
            q = request.url.params["q"]
            handler_obj.queries.append(q)
            if q in connect_error_on:
                raise httpx.ConnectError("dead")
            return httpx.Response(200, json={"results": [
                {"title": f"Article: {q} #{i}", "url": f"https://web.test/{q.replace(' ', '-')}-{i}",
                 "content": f"snippet about {q}"}
                for i in range(pages_per_query)
            ]})
        return httpx.Response(
            200, text=f"<html><body><article><p>Body of {path}.</p></article></body></html>",
            headers={"content-type": "text/html"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client._queries = handler_obj.queries  # type: ignore[attr-defined]
    return client


def make_service(llm, client, **kw) -> ResearchService:
    defaults = dict(max_results=3, fetch_pages=2, page_chars=2000, timeout=5.0,
                    max_iterations=2, max_subquestions=4)
    defaults.update(kw)
    return ResearchService(searxng_url="http://searx.test", llm=llm, client=client, **defaults)


async def collect_steps():
    steps: list[tuple[str, str]] = []

    async def cb(step: str, detail: str) -> None:
        steps.append((step, detail))

    return steps, cb


# --- the deep graph ----------------------------------------------------------------

async def test_deep_path_runs_full_agent_team():
    client = mock_web()
    svc = make_service(ScriptLLM(), client)
    steps, cb = await collect_steps()
    web = await svc.run("compare alpha and beta", depth="deep", on_step=cb)

    names = [s[0] for s in steps]
    assert names == ["plan", "search", "fetch", "critique", "build"]
    assert client._queries == ["alpha", "beta"]              # both sub-questions searched
    assert "Web research results" in web.block and "[1]" in web.block
    assert len(web.sources) == 2                              # top fetch_pages pages


async def test_critic_triggers_followup_round_with_loop():
    client = mock_web()
    llm = ScriptLLM(plan=["alpha"], verdicts=[
        {"verdicts": [{"sub": "alpha", "answered": False}], "follow_ups": ["alpha extra"]},
        {"verdicts": [{"sub": "alpha", "answered": True}], "follow_ups": []},
    ])
    svc = make_service(llm, client)
    steps, cb = await collect_steps()
    web = await svc.run("tell me about alpha", depth="deep", on_step=cb)

    assert client._queries == ["alpha", "alpha extra"]       # refine round searched follow-up
    assert llm.critic_calls == 2
    seq = [s[0] for s in steps]
    assert seq == ["plan", "search", "fetch", "critique", "refine", "search", "fetch", "critique", "build"]
    assert len(web.sources) == 2                              # merged + deduped across rounds


async def test_iteration_cap_guarantees_termination():
    client = mock_web()
    llm = ScriptLLM(plan=["alpha"], verdicts=[{"verdicts": [{"sub": "alpha", "answered": False}],
                                               "follow_ups": ["never satisfied"]}])  # critic NEVER happy
    svc = make_service(llm, client, max_iterations=2)
    web = await svc.run("anything", depth="deep")
    # plan search + 2 capped refine rounds → 3 searches, 3 critiques, then build anyway
    assert client._queries == ["alpha", "never satisfied", "never satisfied"]
    assert llm.critic_calls == 3
    assert "Web research results" in web.block  # still produces a usable context


async def test_critic_malformed_json_finishes_gracefully():
    llm = ScriptLLM(verdicts=["garbage — no json here"])  # type: ignore[list-item]
    llm.critic_calls = 0
    orig_chat = llm.chat

    async def chat(messages, temperature, *, model=None, images=None):
        if "CRITIC agent" in messages[-1]["content"]:
            return "The verdicts are… hard to say. But here: not-json"
        return await orig_chat(messages, temperature, model=model, images=images)

    llm.chat = chat
    svc = make_service(llm, mock_web())
    web = await svc.run("anything", depth="deep")
    assert "Web research results" in web.block  # no crash, one critique round, done


async def test_planner_failure_falls_back_to_single_subquestion():
    llm = ScriptLLM(fail_plan=True)
    client = mock_web()
    svc = make_service(llm, client)
    web = await svc.run("fallback question", depth="deep")
    assert client._queries == ["fallback question"]
    assert "Web research results" in web.block


async def test_quick_path_is_unchanged_and_skips_critic():
    llm = ScriptLLM()
    client = mock_web()
    svc = make_service(llm, client)
    steps, cb = await collect_steps()
    await svc.run("quick question", depth="quick", on_step=cb)
    assert llm.critic_calls == 0
    assert [s[0] for s in steps] == ["plan", "search", "fetch", "build"]


async def test_all_search_failures_surface_honestly():
    client = mock_web(connect_error_on=("alpha", "beta"))
    svc = make_service(ScriptLLM(), client)
    from agents.research import ResearchUnavailable
    with pytest.raises(ResearchUnavailable):
        await svc.run("alpha beta", depth="deep")


# --- engine + WS routing -----------------------------------------------------------

class SpyResearch:
    def __init__(self, unavailable_msg: str | None = None) -> None:
        self.calls: list[dict] = []
        self.unavailable_msg = unavailable_msg

    async def run(self, question, *, depth="quick", on_step=None):
        self.calls.append({"depth": depth, "question": question})
        if on_step:
            await on_step("plan", "planner decomposing")
            await on_step("search", "researcher searching the web")
            await on_step("critique", "critic checking coverage")
        from agents.research import ResearchUnavailable
        if self.unavailable_msg:
            raise ResearchUnavailable(self.unavailable_msg)
        from agents.research.service import WebContext, WebSource
        return WebContext(
            block='Web research results:\n[1] "Deep Docs" — https://deep.example\nFound via loop.\n\n',
            sources=[WebSource(title="Deep Docs", url="https://deep.example")],
        )


def _collect_ws_turn(client, **payload_extras):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "user_message", "content": "deep question please", **payload_extras})
        frames: list[dict] = []
        for _ in range(80):
            frame = ws.receive_json()
            frames.append(frame)
            if frame.get("type") == "message_done":
                break
        else:
            raise AssertionError(f"no message_done; saw {[f.get('type') for f in frames]}")
    return frames


def test_ws_multi_agent_routes_deep_and_streams_steps(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        spy = SpyResearch()
        client.app.state.core.research = spy
        try:
            frames = _collect_ws_turn(client, multi_agent=True)
            assert spy.calls[0]["depth"] == "deep"
            steps = [f for f in frames if f.get("type") == "agent_step"]
            assert [s["step"] for s in steps] == ["plan", "search", "critique"]
            done = frames[-1]
            assert done["steps"] == [
                {"step": "plan", "detail": "planner decomposing"},
                {"step": "search", "detail": "researcher searching the web"},
                {"step": "critique", "detail": "critic checking coverage"},
            ]
            assert done["sources"] == [{"title": "Deep Docs", "url": "https://deep.example"}]
            llm: FakeLLM = client.app.state.core.llm
            assert "Found via loop." in llm.calls[0][-1]["content"]
        finally:
            client.app.state.core.research = None


def test_ws_multi_agent_implies_research_even_without_internet_flag(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        spy = SpyResearch()
        client.app.state.core.research = spy
        try:
            frames = _collect_ws_turn(client, multi_agent=True)  # NO internet flag
            assert spy.calls and spy.calls[0]["depth"] == "deep"
            assert frames[-1]["sources"]
        finally:
            client.app.state.core.research = None


def test_ws_quick_flag_still_routes_quick(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        spy = SpyResearch()
        client.app.state.core.research = spy
        try:
            _collect_ws_turn(client, internet=True)
            assert spy.calls[0]["depth"] == "quick"
        finally:
            client.app.state.core.research = None


def test_ws_multi_agent_unavailable_is_honest(settings):
    with TestClient(create_app(settings=settings, llm_client=FakeLLM())) as client:
        client.app.state.core.research = SpyResearch(unavailable_msg="SearXNG unreachable. docker run …")
        try:
            frames = _collect_ws_turn(client, multi_agent=True)
            tokens = "".join(f.get("content", "") for f in frames if f.get("type") == "token")
            assert "SearXNG unreachable" in tokens
        finally:
            client.app.state.core.research = None
