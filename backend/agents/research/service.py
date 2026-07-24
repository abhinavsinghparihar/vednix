"""ResearchService — web retrieval for a chat turn, orchestrated by LangGraph.

Graph:  plan → search → fetch → build
  plan:   the LLM distills the user message into 1-3 focused search queries
          (falls back to the raw message when the LLM is unavailable —
          retrieval must never die because the brain is being slow)
  search: SearXNG for every query, results merged + deduped by URL
  fetch:  top N pages read into plain text (best-effort; snippet as fallback)
  build:  a cited context block the ENGINE streams an answer from (single
          message-assembly pipeline, audit B3 — the agent never streams itself)

LangGraph is genuinely doing work here: typed state, sequential nodes, and the
parallel fan-out of search/fetch framed as graph steps so richer agent graphs
(Phase 6: multi-hop, reflect loops) extend this file instead of replacing it.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, StateGraph

from agents.research.fetcher import fetch_page_text
from agents.research.searx import ResearchUnavailable, SearchResult, query_searxng
from core.logging import get_logger

logger = get_logger(__name__)


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
    results: list[dict]
    pages: list[dict]
    block: str


_QUERIES_PROMPT = (
    "Rewrite the user's message as 1-3 precise web search queries. "
    "Return ONLY a JSON array of strings, no prose.\n\nUser: "
)


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
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.searxng_url = searxng_url.rstrip("/")
        self.llm = llm
        self.max_results = max_results
        self.fetch_pages = fetch_pages
        self.page_chars = page_chars
        self.timeout = timeout
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=4.0),
            headers={"User-Agent": "VednixAI/0.1 (+research; self-hosted)"},
        )
        self._owns_client = client is None
        self._graph = self._build_graph()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # --- graph nodes ----------------------------------------------------------

    async def _node_plan(self, state: _ResearchState) -> dict[str, Any]:
        question = state["question"]
        if self.llm is not None:
            try:
                raw = await self.llm.chat(
                    [{"role": "user", "content": _QUERIES_PROMPT + question[:800]}], temperature=0.1
                )
                match = re.search(r"\[.*\]", raw, re.DOTALL)
                queries = [str(q).strip() for q in json.loads(match.group(0)) if str(q).strip()][:3] if match else []
                if queries:
                    return {"queries": queries}
            except Exception:
                logger.warning("research plan node fell back to raw question", exc_info=True)
        return {"queries": [question[:200]]}

    async def _node_search(self, state: _ResearchState) -> dict[str, Any]:
        batches = await asyncio.gather(
            *(query_searxng(self.searxng_url, self._client, q, count=self.max_results, timeout=self.timeout)
              for q in state["queries"]),
            return_exceptions=True,
        )
        seen: set[str] = set()
        merged: list[dict] = []
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
            raise failures[0]  # all queries failed → honest ResearchUnavailable
        return {"results": merged[: self.max_results]}

    async def _node_fetch(self, state: _ResearchState) -> dict[str, Any]:
        top = state["results"][: self.fetch_pages]
        bodies = await asyncio.gather(
            *(fetch_page_text(self._client, r["url"], max_chars=self.page_chars, timeout=self.timeout)
              for r in top)
        )
        pages = [
            {**r, "body": body or r["snippet"]}
            for r, body in zip(top, bodies)
        ]
        return {"pages": pages}

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

    def _build_graph(self):
        graph = StateGraph(_ResearchState)
        graph.add_node("plan", self._node_plan)
        graph.add_node("search", self._node_search)
        graph.add_node("fetch", self._node_fetch)
        graph.add_node("build", self._node_build)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "search")
        graph.add_edge("search", "fetch")
        graph.add_edge("fetch", "build")
        graph.add_edge("build", END)
        return graph.compile()

    # --- public API -------------------------------------------------------------

    async def run(self, question: str) -> WebContext:
        state = await self._graph.ainvoke({"question": question})
        pages = state.get("pages", [])
        return WebContext(
            block=state.get("block", ""),
            sources=[WebSource(title=p["title"], url=p["url"]) for p in pages],
        )
