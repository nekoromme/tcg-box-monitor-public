"""既存の店舗索引の詳細を、公式本文が読めない回だけ使う。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from tcg_monitor.models import Config, LotteryCase, SourceConfig, SourceTier
from tcg_monitor.parsers.local_lottery import _box_products, _game_id
from tcg_monitor.store_scope import outside_store_scope


@dataclass(frozen=True)
class IndexDetailFallback:
    url: str
    official_url: str
    product_keys: frozenset[str]


def discover_index_detail_fallbacks(
    html: str, url: str, source: SourceConfig, config: Config, events: list[str],
) -> dict[str, IndexDetailFallback]:
    # 設定した索引と、同じ行にある詳細URLだけを許可する。別店舗や広告を追わない。
    if (not source.parser_options.get("store_index_detail_fallback")
            or source.parser_options.get("store_index_url") != url):
        return {}
    soup = BeautifulSoup(html, "lxml")
    found = {}
    for anchor in soup.select("#list li a[href]"):
        event = urljoin(url, str(anchor.get("href")))
        if event not in events:
            continue
        row = anchor.find_parent("li")
        if row is None:
            continue
        for detail in row.select("a[href]"):
            detail_url = urljoin(url, str(detail.get("href")))
            parts = urlsplit(detail_url)
            if (parts.scheme != "https" or parts.netloc != urlsplit(url).netloc
                    or not re.fullmatch(r"/l/[A-Za-z0-9_-]+/", parts.path)
                    or parts.query or parts.fragment):
                continue
            label = detail.get_text(" ", strip=True)
            game_id = _game_id(label)
            if (not game_id or not source.supports(game_id)
                    or game_id not in config.active_game_ids):
                continue
            keys = frozenset(item[2] for item in _box_products(label, game_id, config))
            if keys:
                found[event] = IndexDetailFallback(detail_url, event, keys)
    return found


def parse_index_detail_fallback(
    html: str, fallback: IndexDetailFallback, source: SourceConfig, config: Config,
) -> list[LotteryCase]:
    soup = BeautifulSoup(html, "lxml")
    article = soup.select_one("main article")
    if article is None:
        raise ValueError("lottery index detail article missing")
    def compact(text: str) -> str:
        return re.sub(r"\s+", "", text)
    store = article.select_one(".store")
    expected = str(source.parser_options.get("required_store_name") or "")
    if not expected or store is None or compact(store.get_text()) != compact(expected):
        raise ValueError("lottery index detail store mismatch")
    links = {str(anchor.get("href")) for anchor in article.select("a.go[href]")}
    if links != {fallback.official_url}:
        raise ValueError("lottery index detail application URL mismatch")
    fields = {}
    for label in article.select("dl dt"):
        value = label.find_next_sibling("dd")
        if value is not None:
            fields[label.get_text(strip=True)] = value.get_text(" ", strip=True)
    period = article.select_one("[data-start][data-end]")
    if period is None or not fields.get("応募期間"):
        raise ValueError("lottery index detail application period missing")
    start = datetime.fromisoformat(str(period.get("data-start")))
    end = datetime.fromisoformat(str(period.get("data-end")))
    # 年・時刻・時差が明示された開始と締切を両方要求する。締切や初回発見日で
    # 開始日を作らず、壊れた期間と終了済みの情報を新規通知へ戻さない。
    if (start.tzinfo is None or end.tzinfo is None or not start < end
            or end - start > timedelta(days=90)):
        raise ValueError("lottery index detail invalid application period")
    if end < datetime.now(UTC):
        return []
    product = fields.get("商品", "")
    game_id = _game_id(product)
    if (not game_id or not source.supports(game_id)
            or game_id not in config.active_game_ids):
        raise ValueError("lottery index detail game missing")
    products = _box_products(product, game_id, config)
    if frozenset(item[2] for item in products) != fallback.product_keys:
        raise ValueError("lottery index detail product mismatch")
    retailer_id = str(source.parser_options["retailer_id"])
    if outside_store_scope(config, retailer_id, article.get_text(" "), source.id, fallback.url):
        return []
    return [LotteryCase(
        game_id=game_id, retailer_id=retailer_id,
        retailer_name=str(source.parser_options["retailer_name"]),
        product_name=name, product_category=category, canonical_product_key=key,
        start_at=start, end_at=end, official_url=fallback.official_url,
        source_url=fallback.url, source_tier=SourceTier.SECONDARY,
        extraction_method="tcg_chusen_detail_application_period", confidence="medium",
    ).with_id() for name, category, key in products]
