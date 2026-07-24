"""Read web pages into plain text for citation — stdlib-only HTML parsing.

Why not bs4/readability: zero new heavy deps for a task that is 90%
"drop script/style/nav, strip tags, collapse whitespace". The extractor is a
strict HTMLParser subclass — no regex-on-HTML sins.
"""

from __future__ import annotations

import asyncio
import html
import re
from html.parser import HTMLParser

import httpx

_DROP_TAGS = {"script", "style", "noscript", "template", "svg", "nav", "footer", "header", "form"}
_WS_RE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._drop_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _DROP_TAGS:
            self._drop_depth += 1
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section", "article") and not self._drop_depth:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP_TAGS and self._drop_depth:
            self._drop_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._drop_depth:
            self.parts.append(data)

    def text(self) -> str:
        return _WS_RE.sub(" ", html.unescape(" ".join(self.parts))).strip()


def html_to_text(raw_html: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw_html)
    return parser.text()


async def fetch_page_text(
    client: httpx.AsyncClient, url: str, *, max_chars: int = 6000, timeout: float = 12.0
) -> str:
    """Readable text of one page; empty string on any failure (fetch is best-effort,
    a page that refuses just leaves its snippet as the citation)."""
    try:
        resp = await asyncio.wait_for(
            client.get(url, follow_redirects=True), timeout=timeout
        )
        if resp.status_code != 200:
            return ""
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type.lower():
            return ""
        htmlbody = resp.text
        # head/tail windows usually carry the article body before boilerplate soup
        return html_to_text(htmlbody)[:max_chars]
    except (httpx.HTTPError, asyncio.TimeoutError, ValueError):
        return ""
