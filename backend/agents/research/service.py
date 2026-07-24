"""ResearchService — web retrieval for a chat turn, orchestrated by LangGraph.

Phase 5 graph (depth="quick"):  plan → search → fetch → build
Phase 6 graph (depth="deep", multi-agent mode):

    planner → researcher(search+fetch) → critic ─┐
        ▲         ▲                               │ verdicts unanswered & rounds left
        │         └────── refine(follow-ups) ◄────┘
        └──────────────────────────── all covered (or round cap) → build

Design invariants carried from Phase 5:
  - Retrieval only. The final answer is still the ENGINE's single streaming
    pipeline (audit B3) — agents never stream tokens themselves.
  - Strict I/O: every LLM node parses a JSON contract with a salvage path; a
    broken/malformed verdict degrades to "answered" so graphs always terminate.
  - Steps: nodes report `(step, detail)` through `on_step`, which the engine
    turns into live "agent_step" WS frames — the orchestration is visible
    instead of magic.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypedDict

import httpx
from langgraph.graph import END, StateGraph

from agents.research.fetcher import fetch_page_text
from agents.research.searx import ResearchUnavailable, SearchResult, query_searxng
from core.logging import get_logger

logger = get_logger(__name__)

StepCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class WebSource:
    title: str
    url: str


@dataclass
class WebContext:
    block: str                       # injected above the user question
    sources: list[WebSource] = field(default_factory=list)


class _ResearchState(TypedDict, total=False):
    question: str
    queries: list[str]
    subqs: list[str]                  # deep mode: planner agent decomposition
    results: list[dict]
    pages: list[dict]
    block: str
    round: int                        # deep mode: critique/refine iteration
    follow_ups: list[str]             # deep mode: critic-requested next queries


_QUERIES_PROMPT = (
    "Rewrite the user's message as 1-3 precise web search queries. "
    "Return ONLY a JSON array of strings, no prose.\n\nUser: "
)

_PLAN_DEEP_PROMPT = (
    "You are the PLANNER agent in a research team. Break the user's request into 2-4 focused "
    "search sub-questions that, answered together, fully cover it. "
    "Return ONLY a JSON array of strings, no prose.\n\nUser: "
)

_CRITIC_PROMPT = (
    "You are the CRITIC agent in a research team. Research question: {question}\n"
    "Sub-questions: {subqs}\n\nEvidence gathered so far:\n{evidence}\n\n"
    "For each sub-question decide if the evidence answers it. "
    "Return ONLY JSON of the form "
    '{{"verdicts": [{{"sub": "…", "answered": true}}], "follow_ups": ["new search query", …]}} — '
    "follow_ups lists ONLY what is still missing (empty array when fully covered)."
)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _salvage_json_array(raw: str, *, cap: int) -> list[str]:
    match = _JSON_ARRAY_RE.search(raw or "")
    if not match:
        return []
    try:
        out = [str(q).strip() for q in json.loads(match.group(0)) if str(q).strip()]
        return out[:cap]
    except ValueError:
        logger.warning("agent emitted malformed JSON array: %.160s", raw)
        return []


class ResearchService:
    def __init__(
        self,
        *,
        searxng_url: str,
        llm=None,
        max_results: int = 5,
        fetch_pages: int = 3,
        page_chars: int = 6000,
        timeout: float = 12.0,
        max_iterations: int = 2,        # deep mode: critique/refine rounds
        max_subquestions: int = 4,      # deep mode: planner fan-out cap
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.searxng_url = searxng_url.rstrip("/")
        self.llm = llm
        self.max_results = max_results
        self.fetch_pages = fetch_pages
        self.page_chars = page_chars
        self.timeout = timeout
        self.max_iterations = max_iterations
        self.max_subquestions = max_subquestions
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=4.0),
            headers={"User-Agent": "VednixAI/0.1 (+research; self-hosted)"},
        )
        self._owns_client = client is None
        self._graphs = {"quick": self._build_quick_graph(), "deep": self._build_deep_graph()}
        self._on_step: StepCallback | None = None  # set per run() call

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # --- shared agents -----------------------------------------------------

    async def _emit(self, step: str, detail: str) -> None:
        if self._on_step is not None:
            try:
                await self._on_step(step, detail)
            except Exception:
                logger.warning("agent_step subscriber failed on %s", step, exc_info=True)

    async def _node_search(self, state: _ResearchState) -> dict[str, Any]:
        """Researcher agent, retrieval leg. Queries come from the plan (quick),
        sub-questions (deep first round) or critic follow-ups (deep refine)."""
        queries = state.get("queries") or state.get("subqs") or state.get("follow_ups") or []
        if state.get("follow_ups") and state.get("round", 0) > 0:
            queries = state["follow_ups"]  # refine rounds use ONLY the follow-ups
        batches = await asyncio.gather(
            *(query_searxng(self.searxng_url, self._client, q, count=self.max_results, timeout=self.timeout)
              for q in queries),
            return_exceptions=True,
        )
        seen = {r["url"] for r in state.get("results", [])}
        merged: list[dict] = list(state.get("results", []))
        failures: list[Exception] = []
        for batch in batches:
            if isinstance(batch, Exception):
                failures.append(batch)
                continue
            for r in batch:
                if r.url not in seen:
                    seen.add(r.url)
                    merged.append({"title": r.title, "url": r.url, "snippet": r.snippet})
        if not merged and failures:
            raise failures[0]  # everything failed → honest ResearchUnavailable
        return {"results": merged, "queries": queries}

    async def _node_fetch(self, state: _ResearchState) -> dict[str, Any]:
        """Researcher agent, reading leg. Refresh the reading list from the
        most recent round of results (earlier pages already quoted stay)."""
        recent = [r for r in state["results"] if not any(p["url"] == r["url"] for p in state.get("pages", []))]
        top = (recent + state.get("pages", []))[: self.fetch_pages]
        new_pages = [p for p in top if p not in state.get("pages", [])]
        bodies = await asyncio.gather(
            *(fetch_page_text(self._client, p["url"], max_chars=self.page_chars, timeout=self.timeout)
              for p in new_pages)
        )
        pages = [{**p, "body": body or p["snippet"]} for p, body in zip(new_pages, bodies)]
        return {"pages": state.get("pages", []) + pages}

    def _node_build(self, state: _ResearchState) -> dict[str, Any]:
        lines = []
        for i, page in enumerate(state["pages"], start=1):
            excerpt = page["body"][:1200]
            lines.append(f'[{i}] "{page["title"]}" — {page["url"]}\n{excerpt}')
        block = (
            "Web research results (cite them inline like [1], [2]; mention when "
            "the web and your knowledge disagree):\n" + "\n\n".join(lines) + "\n\n"
        )
        return {"block": block}

    # --- quick mode agents -------------------------------------------------

    async def _node_plan(self, state: _ResearchState) -> dict[str, Any]:
        question = state["question"]
        if self.llm is not None:
            try:
                raw = await self.llm.chat(
                    [{"role": "user", "content": _QUERIES_PROMPT + question[:800]}], temperature=0.1
                )
                queries = _salvage_json_array(raw, cap=3)
                if queries:
                    return {"queries": queries}
            except Exception:
                logger.warning("plan node fell back to raw question", exc_info=True)
        return {"queries": [question[:200]]}

    # --- deep mode agents ------------------------------------------------

    async def _node_plan_deep(self, state: _ResearchState) -> dict[str, Any]:
        question = state["question"]
        if self.llm is not None:
            try:
                raw = await self.llm.chat(
                    [{"role": "user", "content": _PLAN_DEEP_PROMPT + question[:800]}], temperature=0.1
                )
                subqs = _salvage_json_array(raw, cap=self.max_subquestions)
                if subqs:
                    return {"subqs": subqs}
            except Exception:
                logger.warning("planner agent fell back to raw question", exc_info=True)
        return {"subqs": [question[:200]]}  # single "sub-question" keeps the graph valid

    async def _node_critique(self, state: _ResearchState) -> dict[str, Any]:
        """Critic agent: coverage verdict. Any parse/LLM trouble → answered
        (graph must terminate; perfection is the refinement's job, not a hang)."""
        if self.llm is None:
            return {"follow_ups": []}
        evidence = "\n\n".join(
            f'- "{p["title"]}" ({p["url"]}): {p["body"][:400]}' for p in state.get("pages", [])[:6]
        ) or "(no evidence fetched)"
        try:
            raw = await self.llm.chat(
                [{"role": "user", "content": _CRITIC_PROMPT.format(
                    question=state["question"][:400], subqs=json.dumps(state.get("subqs", []), ensure_ascii=False),
                    evidence=evidence,
                )}], temperature=0.1,
            )
            match = _JSON_OBJECT_RE.search(raw or "")
            data = json.loads(match.group(0)) if match else {}
        except Exception:
            logger.warning("critic agent unparseable → treating as covered", exc_info=True)
            return {"follow_ups": []}
        follow_ups = [str(q).strip() for q in (data.get("follow_ups") or []) if str(q).strip()]
        return {"follow_ups": follow_ups[: self.max_subquestions]}

    def _deep_router(self, state: _ResearchState) -> str:
        """The conditional edge that makes this a LOOP, not a chain."""
        if not state.get("follow_ups"):
            return "build"
        if state.get("round", 0) + 1 > self.max_iterations:
            return "build"
        return "refine"

    async def _node_refine(self, state: _ResearchState) -> dict[str, Any]:
        return {"round": state.get("round", 0) + 1, "queries": []}  # queries cleared → follow_ups take over

    def _build_quick_graph(self):
        graph = StateGraph(_ResearchState)
        graph.add_node("plan", self._stepped("plan", "planning queries", self._node_plan))
        graph.add_node("search", self._stepped("search", "searching the web", self._node_search))
        graph.add_node("fetch", self._stepped("fetch", "reading top pages", self._node_fetch))
        graph.add_node("build", self._stepped("build", "preparing citations", self._node_build))
        graph.set_entry_point("plan")
        graph.add_edge("plan", "search")
        graph.add_edge("search", "fetch")
        graph.add_edge("fetch", "build")
        graph.add_edge("build", END)
        return graph.compile()

    def _build_deep_graph(self):
        graph = StateGraph(_ResearchState)
        graph.add_node("plan", self._stepped("plan", "planner decomposing the question", self._node_plan_deep))
        graph.add_node("search", self._stepped(
            "search",
            lambda s: (f"researcher searching follow-ups (round {s.get('round', 0) + 1})"
                       if s.get("round", 0) > 0 else "researcher searching the web"),
            self._node_search,
        ))
        graph.add_node("fetch", self._stepped("fetch", "researcher reading pages", self._node_fetch))
        graph.add_node("critique", self._stepped("critique", "critic checking coverage", self._node_critique))
        graph.add_node("refine", self._stepped("refine", "refining with follow-up queries", self._node_refine))
        graph.add_node("build", self._stepped("build", "preparing citations", self._node_build))
        graph.set_entry_point("plan")
        graph.add_edge("plan", "search")
        graph.add_edge("search", "fetch")
        graph.add_edge("fetch", "critique")
        graph.add_conditional_edges("critique", self._deep_router, {"refine": "refine", "build": "build"})
        graph.add_edge("refine", "search")  # the loop
        graph.add_edge("build", END)
        return graph.compile()

    def _stepped(self, step_name, label, fn):
        """Wrap a node so every graph transition is observable in the UI.
        `label` may be a string or a state→string callable (refine rounds
        change the message; bound-method identity checks can't carry this)."""

        async def wrapped(state: _ResearchState):
            detail = label(state) if callable(label) else label
            await self._emit(step_name, detail)
            return await fn(state) if asyncio.iscoroutinefunction(fn) else fn(state)

        return wrapped

    # --- public API -------------------------------------------------------------

    async def run(
        self, question: str, *, depth: str = "quick", on_step: StepCallback | None = None
    ) -> WebContext:
        self._on_step = on_step
        try:
            state = await self._graphs["deep" if depth == "deep" else "quick"].ainvoke(
                {"question": question, "round": 0, "pages": [], "results": []}
            )
        finally:
            self._on_step = None
        pages = state.get("pages", [])
        return WebContext(
            block=state.get("block", ""),
            sources=[WebSource(title=p["title"], url=p["url"]) for p in pages],
        )
