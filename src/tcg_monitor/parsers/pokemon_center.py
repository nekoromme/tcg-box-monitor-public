from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

from tcg_monitor.classifier import canonical_product_key
from tcg_monitor.japanese_datetime import parse_period_start
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig
from tcg_monitor.parsers.common import title, visible_text

_ONLINE_SOURCE = "pokemon_center_online"
_STORE_SOURCE = "pokemon_center_store"
_CATEGORIES = ("強化拡張パック", "ハイクラスパック", "再拡張パック", "拡張パック")
_START_LABEL = re.compile(
    r"(?:抽選お申し込み期間|抽選お申込み期間|抽選応募受け付け期間|"
    r"抽選応募受付期間|応募受付期間|応募期間)(?P<group>[①②③0-9]*)\s*[：:]?"
)
_PUBLICATION_DATE = re.compile(r"(?:公開日[：:]?\s*)?(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?")


def is_pokemon_center_news_index(source_id: str, url: str) -> bool:
    parts = urlsplit(url)
    if source_id == _ONLINE_SOURCE:
        return parts.netloc == "www.pokemoncenter-online.com" and parts.path.rstrip("/") == "/news"
    if source_id == _STORE_SOURCE:
        return (
            parts.netloc == "shop.pokemon.co.jp"
            and parts.path.rstrip("/") == "/ja/shop/common/news"
        )
    return False


def _is_detail_url(source_id: str, candidate: str) -> bool:
    parts = urlsplit(candidate)
    if source_id == _ONLINE_SOURCE:
        return (
            parts.netloc == "www.pokemoncenter-online.com"
            and parts.path.rstrip("/") == "/news"
            and bool(parse_qs(parts.query).get("id"))
        )
    return bool(
        source_id == _STORE_SOURCE
        and parts.netloc == "shop.pokemon.co.jp"
        and re.fullmatch(r"/ja/shop/common/news/\d{6}/\d+\.html", parts.path)
    )


def discover_pokemon_center_news_urls(
    html: str, url: str, source: SourceConfig, limit: int = 12
) -> list[str]:
    """Follow only official Pokémon Card lottery articles from each news index."""
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        label = anchor.get_text(" ", strip=True)
        if "抽選" not in label or not any(
            word in label for word in ("ポケモンカード", "カードゲーム")
        ):
            continue
        candidate = urljoin(url, str(anchor.get("href")))
        if _is_detail_url(source.id, candidate) and candidate not in found:
            found.append(candidate)
        if len(found) >= limit:
            break
    return found


def _publication_date(text: str) -> date:
    match = _PUBLICATION_DATE.search(text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return datetime.now().date()


def _products(text: str, config: Config, allow_loose_packs: bool) -> list[tuple[str, str, str]]:
    """Extract expansion-pack products while excluding decks and accessory sets."""
    categories = "|".join(map(re.escape, _CATEGORIES))
    pattern = re.compile(
        rf"(?P<category>{categories})\s*[「『【\"“](?P<title>[^」』】\"”]{{2,100}})[」』】\"”]",
        re.I,
    )
    game = config.games["pokemon_card"]
    output: dict[str, tuple[str, str, str]] = {}
    for match in pattern.finditer(text):
        category = match.group("category")
        title_text = match.group("title").strip()
        nearby = text[match.start() : match.end() + 140]
        if not allow_loose_packs and not re.search(r"(?i)\b1?BOX\b", nearby):
            continue
        product_name = f"{category}「{title_text}」"
        key = canonical_product_key(game, product_name)
        output[key] = (product_name, category, key)
    return list(output.values())


def _application_starts(text: str, base_date: date) -> list[tuple[str, datetime | date]]:
    matches = list(_START_LABEL.finditer(text))
    output: list[tuple[str, datetime | date]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        scope = text[match.end() : min(end, match.end() + 220)]
        parsed = parse_period_start(scope, base_date)
        if not parsed.value:
            continue
        group = match.group("group") or ""
        item = (group, parsed.value)
        if item not in output:
            output.append(item)
    return output


def _alert(
    source: SourceConfig, url: str, page_title: str, reason: str, summary: str
) -> Alert:
    return Alert(
        "pokemon_card",
        source.id,
        url,
        page_title,
        ["抽選", "応募"],
        reason,
        summary,
        None,
        url,
    ).with_fingerprint()


def parse_pokemon_center_lottery(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Parse online/store lotteries without ever treating result dates as starts."""
    page_title = title(html) or source.name
    text = visible_text(html)
    if "抽選" not in text or not any(word in text for word in ("ポケモンカード", "カードゲーム")):
        return [], [], []

    is_store = source.id == _STORE_SOURCE
    products = _products(text, config, allow_loose_packs=is_store)
    if not products:
        return [], [], []
    starts = _application_starts(text, _publication_date(text))
    if not starts:
        return (
            [],
            [],
            [
                _alert(
                    source,
                    url,
                    page_title,
                    "pokemon_center_application_period_missing",
                    "対象商品の抽選記事だが、応募期間の開始日時を解析できません",
                )
            ],
        )

    retailer_id = "pokemon_center_store" if is_store else "pokemon_center_online"
    base_name = "ポケモンセンター（店頭）" if is_store else "ポケモンセンターオンライン"
    cases: list[LotteryCase] = []
    for group, start_at in starts:
        retailer_name = f"{base_name}・期間{group}" if group else base_name
        for product_name, product_category, product_key in products:
            cases.append(
                LotteryCase(
                    "pokemon_card",
                    retailer_id,
                    retailer_name,
                    product_name,
                    product_category,
                    product_key,
                    start_at,
                    url,
                    url,
                    source.source_tier,
                    "pokemon_center_labelled_application_period",
                    "high",
                ).with_id()
            )
    return cases, [], []


__all__ = [
    "discover_pokemon_center_news_urls",
    "is_pokemon_center_news_index",
    "parse_pokemon_center_lottery",
]
