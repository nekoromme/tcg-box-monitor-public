from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig

PRODUCT_URL = re.compile(r"/products/(?:op|eb|prb)\d+\.html$", re.I)


def parse_onepiece_official_products(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    soup = BeautifulSoup(html, "lxml")
    game = config.games["one_piece_card"]
    releases: list[Release] = []
    alerts: list[Alert] = []
    seen_urls: set[str] = set()

    for anchor in soup.select("a[href]"):
        official_url = urljoin(url, str(anchor.get("href")))
        if not PRODUCT_URL.search(official_url) or official_url in seen_urls:
            continue
        seen_urls.add(official_url)
        block = anchor.get_text(" ", strip=True)
        classified = classify_product(game, block, block, official_url)
        if not classified.is_box:
            continue
        scoped = block.split("発売日", 1)[1] if "発売日" in block else block
        parsed = parse_first_datetime(scoped)
        release_date: date | None = None
        if isinstance(parsed.value, datetime):
            release_date = parsed.value.date()
        elif isinstance(parsed.value, date):
            release_date = parsed.value
        if release_date or parsed.month_only:
            releases.append(
                Release(
                    "one_piece_card",
                    block.split("発売日", 1)[0].strip(),
                    classified.product_category,
                    classified.canonical_product_key,
                    release_date,
                    parsed.month_only,
                    official_url,
                    url,
                    source.source_tier,
                    "onepiece_official_product_link",
                    "high" if release_date else "medium",
                ).with_id()
            )
        else:
            alerts.append(
                Alert(
                    "one_piece_card",
                    source.id,
                    url,
                    block or source.name,
                    ["発売日"],
                    "new_box_product_without_release_value",
                    "公式商品リンクから発売日または発売月を解析できません",
                    None,
                    official_url,
                ).with_fingerprint()
            )
    if not seen_urls:
        alerts.append(
            Alert(
                "one_piece_card",
                source.id,
                url,
                source.name,
                ["商品ラインナップ"],
                "expected_element_missing",
                "OP/EB/PRBの商品リンクが見つかりません",
                None,
                url,
            ).with_fingerprint()
        )
    return [], releases, alerts


__all__ = ["parse_onepiece_official_products"]
