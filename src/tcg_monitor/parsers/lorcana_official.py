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

_PRODUCT_ROOT = "/products/disneylorcana/product/"
_SET_PAGE = re.compile(r"^/products/disneylorcana/product/[^/]+/?$")
_BOOSTER_PAGE = re.compile(
    r"^/products/disneylorcana/product/[^/]+/booster-pack/?$"
)


def is_lorcana_product_index(source_id: str, url: str) -> bool:
    if source_id != "lorcana_official_products":
        return False
    path = urlsplit(url).path
    return path.rstrip("/") == _PRODUCT_ROOT.rstrip("/") or bool(
        _SET_PAGE.fullmatch(path)
    )


def discover_lorcana_product_urls(
    html: str,
    url: str,
    limit: int = 8,
) -> list[str]:
    """Follow recent set pages, then their booster-pack detail page."""

    soup = BeautifulSoup(html, "lxml")
    root_page = urlsplit(url).path.rstrip("/") == _PRODUCT_ROOT.rstrip("/")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        candidate = urljoin(url, str(anchor.get("href") or ""))
        parts = urlsplit(candidate)
        if parts.netloc.casefold() not in {
            "www.takaratomy.co.jp",
            "takaratomy.co.jp",
        }:
            continue
        accepted = (
            bool(_SET_PAGE.fullmatch(parts.path))
            if root_page
            else bool(_BOOSTER_PAGE.fullmatch(parts.path))
        )
        if not accepted:
            continue
        normalized = candidate.split("#", 1)[0].split("?", 1)[0]
        if normalized not in found:
            found.append(normalized)
        if len(found) >= limit:
            break
    return found


def _product_name(soup: BeautifulSoup, url: str) -> str:
    raw_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    parts = [part.strip() for part in raw_title.split("|") if part.strip()]
    if parts and "ブースターパック" in parts[0]:
        set_name = next(
            (
                part
                for part in parts[1:]
                if part not in {"商品情報", "ディズニー・ロルカナ・TCG"}
                and "ディズニー・ロルカナ" not in part
            ),
            "",
        )
        return f"ブースターパック「{set_name}」" if set_name else parts[0]

    for heading in soup.find_all(("h1", "h2")):
        if not isinstance(heading, Tag):
            continue
        value = heading.get_text(" ", strip=True)
        if "ブースターパック" in value:
            return value
    slug = urlsplit(url).path.rstrip("/").split("/")[-2]
    return f"ブースターパック「{slug}」"


def parse_lorcana_official_product(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    today: date | None = None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Parse one official Lorcana booster detail page."""

    if not _BOOSTER_PAGE.fullmatch(urlsplit(url).path):
        return [], [], []
    soup = BeautifulSoup(html, "lxml")
    text = visible_text(html)
    product_name = _product_name(soup, url)
    game = config.games["lorcana"]
    # These are already official ``/booster-pack/`` detail pages.  The global
    # Takara Tomy navigation contains labels such as 「イベント・キャンペーン」
    # and related-product areas can mention starter decks.  Feeding the entire
    # page to the generic classifier therefore excluded every real booster.
    # Classify the scoped product heading instead; release parsing below still
    # reads the exact date from the product specification.
    classified = classify_product(game, product_name, product_name)
    if not classified.is_box:
        return [], [], []

    release_scope = text.split("発売日", 1)[1][:160] if "発売日" in text else ""
    parsed = parse_first_datetime(release_scope)
    release_date: date | None = None
    if isinstance(parsed.value, datetime):
        release_date = parsed.value.date()
    elif isinstance(parsed.value, date):
        release_date = parsed.value
    if not release_date:
        return (
            [],
            [],
            [
                Alert(
                    "lorcana",
                    source.id,
                    url,
                    product_name,
                    ["発売日"],
                    "new_box_product_without_exact_release_date",
                    "ロルカナ公式商品ページから発売日を解析できません",
                    None,
                    url,
                ).with_fingerprint()
            ],
        )

    current = today or datetime.now().astimezone().date()
    delta = (release_date - current).days
    if not (
        -int(config.system.get("implausible_past_days", 45))
        <= delta
        <= int(config.system.get("max_future_days", 365))
    ):
        return [], [], []

    release = Release(
        "lorcana",
        product_name,
        classified.product_category,
        classified.canonical_product_key,
        release_date,
        None,
        url,
        url,
        source.source_tier,
        "lorcana_official_booster_detail",
        "high",
    ).with_id()
    return [], [release], []


__all__ = [
    "discover_lorcana_product_urls",
    "is_lorcana_product_index",
    "parse_lorcana_official_product",
]
