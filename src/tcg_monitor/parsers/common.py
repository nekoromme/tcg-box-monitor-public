from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hrefs: list[str] = []
        self.in_title = False
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "article", "section", "li", "tr", "h1", "h2"}:
            self.parts.append("\n")
        if tag == "title":
            self.in_title = True
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.hrefs.append(v)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        self.parts.append(data)
        if self.in_title:
            self.title_parts.append(data)


def _parse(html: str) -> _TextParser:
    p = _TextParser()
    p.feed(html)
    return p


def visible_text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(" ".join(_parse(html).parts))).strip()


def title(html: str) -> str:
    m = re.search(
        r"<h1[^>]*>(.*?)</h1>|<h2[^>]*>(.*?)</h2>|<title[^>]*>(.*?)</title>", html, re.I | re.S
    )
    if not m:
        return ""
    raw = next(g for g in m.groups() if g)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", raw)).strip()


def links(html: str, base: str = "") -> list[str]:
    return _parse(html).hrefs
