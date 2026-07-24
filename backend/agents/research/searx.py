"""SearXNG client — the self-hostable metasearch engine (offline-creed:

no vendor lock-in, no API key quota, `docker run -p 8080:8080 searxng/searxng`
and Vednix has the whole web. Errors raise ResearchUnavailable with the exact
fix so the chat layer can degrade honestly instead of faking results.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx


class ResearchUnavailable(RuntimeError):
    """Search cannot be performed right now (instance down/unreachable)."""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


_SEARX_HINT = (
    "Internet search needs a SearXNG instance. Quick fix:\n\n"
    "```bash\ndocker run -d -p 8080:8080 searxng/searxng\n```\n\n"
    "or point VEDNIX_SEARXNG_URL at one you already run."
)


async def query_searxng(
    base_url: str, client: httpx.AsyncClient, query: str, *, count: int = 5, timeout: float = 12.0
) -> list[SearchResult]:
    try:
        resp = await asyncio.wait_for(
            client.get(
                f"{base_url.rstrip('/')}/search",
                params={"q": query, "format": "json", "safesearch": "1"},
            ),
            timeout=timeout,
        )
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        raise ResearchUnavailable(f"SearXNG unreachable at {base_url} ({exc}). {_SEARX_HINT}") from exc
    if resp.status_code != 200:
        raise ResearchUnavailable(f"SearXNG answered HTTP {resp.status_code}. {_SEARX_HINT}")
    try:
        rows = resp.json().get("results", [])
    except ValueError as exc:
        raise ResearchUnavailable(f"SearXNG returned non-JSON (format=json unsupported?). {_SEARX_HINT}") from exc
    out = [
        SearchResult(str(r.get("title", "")).strip(), str(r.get("url", "")).strip(),
                     str(r.get("content", "")).strip())
        for r in rows[:count]
        if r.get("url") and r.get("title")
    ]
    if not out:
        raise ResearchUnavailable(f"SearXNG returned no results for that query. {_SEARX_HINT}")
    return out
