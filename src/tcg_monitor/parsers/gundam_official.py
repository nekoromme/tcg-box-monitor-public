from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig


def _label_value(block: Tag, label: str) -> str:
    for term in block.select("dt"):
        if not isinstance(term, Tag) or label not in term.get_text(" ", strip=True):
            continue
        value = term.find_next_sibling("dd")
        if isinstance(value, Tag):
            return value.get_text(" ", strip=True)
    return ""


def parse_gundam_official_products(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    today: date | None = None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Read booster BOX dates from the official Gundam Card Game catalog."""

    soup = BeautifulSoup(html, "lxml")
    game = config.games["gundam_card"]
    current = today or datetime.now().astimezone().date()
    releases: dict[str, Release] = {}
    alerts: list[Alert] = []
    cards = [
        block
        for block in soup.select("div.productsDetail")
        if isinstance(block, Tag) and "BOOSTERPACK" in str(block.get("data-tags") or "").upper()
    ]

    for block in cards:
        anchor = block.select_one("a.productsDetailInner[href]") or block.select_one("a[href]")
        title = block.select_one(".cardTit")
        product_name = title.get_text(" ", strip=True) if isinstance(title, Tag) else ""
        if not product_name:
            continue
        official_url = (
            urljoin(url, str(anchor.get("href") or "")) if isinstance(anchor, Tag) else url
        )
        category_node = block.select_one(".cardCategory")
        category = (
            category_node.get_text(" ", strip=True)
            if isinstance(category_node, Tag)
            else "ブースターパック"
        )
        raw_release = _label_value(block, "発売日")
        classified = classify_product(
            game,
            product_name,
            f"{category} {product_name} {raw_release}",
            official_url,
        )
        if not classified.is_box:
            continue

        parsed = parse_first_datetime(raw_release)
        release_date: date | None = None
        if isinstance(parsed.value, datetime):
            release_date = parsed.value.date()
        elif isinstance(parsed.value, date):
            release_date = parsed.value
        if not release_date:
            alerts.append(
                Alert(
                    "gundam_card",
                    source.id,
                    url,
                    product_name,
                    ["発売日"],
                    "new_box_product_without_exact_release_date",
                    "ガンダムカードゲーム公式商品一覧から発売日を解析できません",
                    None,
                    official_url,
                ).with_fingerprint()
            )
            continue

        delta = (release_date - current).days
        if not (
            -int(config.system.get("implausible_past_days", 45))
            <= delta
            <= int(config.system.get("max_future_days", 365))
        ):
            continue

        release = Release(
            "gundam_card",
            product_name,
            "ブースターパック",
            classified.canonical_product_key,
            release_date,
            None,
            official_url,
            url,
            source.source_tier,
            "gundam_official_booster_catalog",
            "high",
        ).with_id()
        releases[release.release_id] = release

    if not cards:
        alerts.append(
            Alert(
                "gundam_card",
                source.id,
                url,
                source.name,
                ["ブースター", "発売日"],
                "expected_element_missing",
                "ガンダムカードゲーム公式商品一覧の商品カードが見つかりません",
                None,
                url,
            ).with_fingerprint()
        )

    return [], list(releases.values()), alerts


__all__ = ["parse_gundam_official_products"]
