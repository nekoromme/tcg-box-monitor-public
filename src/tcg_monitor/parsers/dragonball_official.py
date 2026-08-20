from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig
from tcg_monitor.parsers.common import visible_text
from tcg_monitor.parsers.generic import parse_generic

_PRODUCT_URL = re.compile(r"/fw/jp/products/01_\d+\.html$", re.I)
_STORE_ROOT_PATHS = {
    "/official_shop/dbs-cardgame",
    "/official_shop/dbs-cardgame/",
    "/official_shop/dbs-cardgame/index.html",
}
_STORE_NEWS_PATH = re.compile(
    r"^/official_shop/dbs-cardgame/news/(?:important|information)/[^/]+\.html$",
    re.I,
)
_PENDING_DETAIL_MARKERS = (
    "詳細は後日",
    "詳細につきましては後日",
    "準備が整い次第",
    "応募開始日は後日",
    "抽選開始日は後日",
    "事前抽選での販売を予定",
)


def parse_dragonball_official_products(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Read physical booster release dates from the official Fusion World catalog."""

    soup = BeautifulSoup(html, "lxml")
    game = config.games["dragon_ball_fusion_world"]
    releases: dict[str, Release] = {}
    alerts: list[Alert] = []
    saw_product_link = False

    for anchor in soup.select("a[href]"):
        if not isinstance(anchor, Tag):
            continue
        official_url = urljoin(url, str(anchor.get("href")))
        if not _PRODUCT_URL.search(urlsplit(official_url).path):
            continue
        block = anchor.get_text(" ", strip=True)
        # The navigation repeats product links without dates. Only catalog cards carry
        # the release label, so ignoring navigation avoids false missing-date alerts.
        if "発売日" not in block:
            continue
        saw_product_link = True
        product_name = block.split("発売日", 1)[0].strip()
        classified = classify_product(game, product_name, block, official_url)
        if not classified.is_box:
            continue

        parsed = parse_first_datetime(block.split("発売日", 1)[1])
        release_date: date | None = None
        if isinstance(parsed.value, datetime):
            release_date = parsed.value.date()
        elif isinstance(parsed.value, date):
            release_date = parsed.value

        if not release_date:
            alerts.append(
                Alert(
                    "dragon_ball_fusion_world",
                    source.id,
                    url,
                    product_name or source.name,
                    ["発売日"],
                    "new_box_product_without_exact_release_date",
                    "公式商品一覧のブースターから発売日を解析できません",
                    None,
                    official_url,
                ).with_fingerprint()
            )
            continue

        release = Release(
            "dragon_ball_fusion_world",
            product_name,
            classified.product_category,
            classified.canonical_product_key,
            release_date,
            None,
            official_url,
            url,
            source.source_tier,
            "dragonball_official_product_link",
            "high",
        ).with_id()
        releases[release.release_id] = release

    if not saw_product_link:
        alerts.append(
            Alert(
                "dragon_ball_fusion_world",
                source.id,
                url,
                source.name,
                ["商品情報", "発売日"],
                "expected_element_missing",
                "フュージョンワールド公式商品一覧から発売日付き商品リンクが見つかりません",
                None,
                url,
            ).with_fingerprint()
        )

    return [], list(releases.values()), alerts


def is_dragonball_official_store_index(source_id: str, url: str) -> bool:
    return (
        source_id == "dragonball_official_store"
        and urlsplit(url).path in _STORE_ROOT_PATHS
    )


def discover_dragonball_official_store_urls(
    html: str, url: str, limit: int = 12
) -> list[str]:
    """Follow only official-store sales-method notices, never tournament lotteries."""

    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        candidate = urljoin(url, str(anchor.get("href")))
        label = anchor.get_text(" ", strip=True)
        if not _STORE_NEWS_PATH.match(urlsplit(candidate).path):
            continue
        if not any(marker in label for marker in ("ブースターパック", "BOOSTER")):
            continue
        if not any(marker in label for marker in ("抽選", "販売方法", "販売について")):
            continue
        if candidate not in found:
            found.append(candidate)
        if len(found) >= limit:
            break
    return found


def parse_dragonball_official_store_lottery(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Parse official-store BOX application starts and tolerate announced-but-pending details."""

    cases, releases, alerts = parse_generic(html, url, source, config)
    text = visible_text(html)
    if any(marker in text for marker in _PENDING_DETAIL_MARKERS):
        alerts = [
            alert
            for alert in alerts
            if alert.reason_code != "lottery_text_without_start"
        ]
    return (
        [case for case in cases if case.game_id == "dragon_ball_fusion_world"],
        releases,
        alerts,
    )


__all__ = [
    "discover_dragonball_official_store_urls",
    "is_dragonball_official_store_index",
    "parse_dragonball_official_products",
    "parse_dragonball_official_store_lottery",
]
