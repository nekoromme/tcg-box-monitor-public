from __future__ import annotations

from hashlib import sha256

from bs4 import BeautifulSoup


def structure_fingerprint(html: str) -> str:
    s = BeautifulSoup(html, "lxml")
    tags = [t.name for t in s.find_all()[:500]]
    return sha256("/".join(tags).encode()).hexdigest()


def similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    sa = set(a.split("/"))
    sb = set(b.split("/"))
    return len(sa & sb) / max(1, len(sa | sb))
