from __future__ import annotations

from hashlib import sha256

from bs4 import BeautifulSoup


def discover_links(html: str, patterns: list[str]) -> list[str]:
    links: list[str] = []
    for anchor in BeautifulSoup(html, "lxml").find_all("a"):
        href = anchor.get("href")
        if isinstance(href, str):
            links.append(href)
    return links


def semantic_hash(text: str) -> str:
    return sha256(" ".join(text.split()).encode()).hexdigest()
