from __future__ import annotations

import re
from hashlib import sha256

from tcg_monitor.models import ClassifiedProduct, GameConfig


def canonical_product_key(game: GameConfig, name: str, url: str | None = None) -> str:
    for pat in game.product_code_patterns:
        if m := re.search(pat, name, re.I):
            return m.group("code").upper()
    if url:
        m = re.search(r"(?:/products/|/rb/|/)([A-Za-z0-9_-]{4,})(?:\.html|\.php|/)?$", url)
        if m:
            return m.group(1)
    return re.sub(r"\s+", "", name)


def classify_product(
    game: GameConfig, name: str, text: str, url: str | None = None
) -> ClassifiedProduct:
    block = f"{name}\n{text}"
    excludes = [k for k in game.product_exclude_keywords if k in block]
    evidence = []
    for k in game.box_product_keywords:
        if k in block:
            evidence.append(k)
    for p in game.box_evidence_patterns:
        if re.search(p, block):
            evidence.append(p)
    is_box = bool(evidence) and not excludes
    key = canonical_product_key(game, name, url)
    if len(key) > 80:
        key = sha256(key.encode()).hexdigest()
    return ClassifiedProduct(
        game.id.value, name, evidence[0] if evidence else "unknown", is_box, key, evidence, excludes
    )
