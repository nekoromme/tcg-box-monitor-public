from __future__ import annotations

import json
from datetime import date, datetime
from html import escape
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig


def is_pokemon_products_api(url: str) -> bool:
    parts = urlsplit(url)
    return (
        parts.hostname == "www.pokemon-card.com"
        and parts.path == "/products/resultAPI.php"
    )


def _api_data(payload: str) -> dict[str, Any]:
    data = json.loads(payload)
    if (
        not isinstance(data, dict)
        or data.get("result") != 1
        or data.get("errMsg") != ""
        or not isinstance(data.get("products"), list)
        or any(type(data.get(key)) is not int for key in ("hitCnt", "thisPage", "maxPage"))
    ):
        raise ValueError("Official Pokemon product API returned an invalid result")
    if not (
        0 <= data["thisPage"] <= data["maxPage"] <= 100
        and data["hitCnt"] >= len(data["products"])
        and bool(data["products"]) == bool(data["hitCnt"])
        and bool(data["products"]) == bool(data["thisPage"])
        and bool(data["products"]) == bool(data["maxPage"])
    ):
        raise ValueError("Official Pokemon product API returned inconsistent counts")
    return data


def discover_pokemon_product_api_pages(payload: str, url: str) -> list[str]:
    if not is_pokemon_products_api(url):
        return []
    data = _api_data(payload)
    if data["thisPage"] >= data["maxPage"]:
        return []
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["page"] = str(data["thisPage"] + 1)
    return [urlunsplit((*parts[:3], urlencode(query), parts.fragment))]


def _api_product_cards(data: dict[str, Any], url: str) -> str:
    cards: list[str] = []
    for product in data["products"]:
        if not isinstance(product, dict) or not all(
            isinstance(product.get(key), str)
            for key in ("productTitle", "productType", "releaseDate")
        ) or not product["productTitle"].strip():
            raise ValueError("Official Pokemon product API returned a malformed product")
        target = urljoin(url, product.get("link_detailPage") or "/products/")
        host = urlsplit(target).hostname or ""
        if host != "www.pokemon-card.com" and not host.endswith(".pokemon-card.com"):
            raise ValueError("Official Pokemon product API returned an unrelated URL")
        title = BeautifulSoup(product["productTitle"], "lxml").get_text(" ", strip=True)
        cards.append(
            f'<a href="{escape(target, quote=True)}"><div class="product-card">'
            f'<div class="product-title">{escape(title)}</div>'
            f'<div class="product-type">{escape(product["productType"])}</div>'
            '<div class="product-table"><span>発売日</span>'
            f'<span>{escape(product["releaseDate"])}</span></div></div></a>'
        )
    return "".join(cards)


def parse_pokemon_official_products(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    if is_pokemon_products_api(url):
        data = _api_data(html)
        if not data["products"]:
            return [], [], []
        html = _api_product_cards(data, url)
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(".product-card")
    if not cards:
        return (
            [],
            [],
            [
                Alert(
                    "pokemon_card",
                    source.id,
                    url,
                    source.name,
                    ["商品情報"],
                    "expected_element_missing",
                    "公式商品カード（.product-card）が見つかりません",
                    None,
                    url,
                ).with_fingerprint()
            ],
        )

    game = config.games["pokemon_card"]
    releases: list[Release] = []
    alerts: list[Alert] = []
    for card in cards:
        title_node = card.select_one(".product-title")
        type_node = card.select_one(".product-type")
        product_name = title_node.get_text(" ", strip=True) if title_node else ""
        product_type = type_node.get_text(" ", strip=True) if type_node else ""
        if product_type and product_type not in product_name:
            product_name = f"{product_type} {product_name}".strip()

        # The official catalog exposes an authoritative product type.  Do not
        # let a marketing title such as ``FUTURISTIC BOX`` turn an explicit
        # "その他の商品" card into an unopened booster-box release merely
        # because the shared classifier also accepts ``1?BOX`` evidence.
        if product_type and not any(
            keyword in product_type for keyword in game.box_product_keywords
        ):
            continue

        card_text = card.get_text(" ", strip=True)
        anchor = card.find_parent("a", href=True) or card.select_one("a[href]")
        official_url = urljoin(url, str(anchor.get("href"))) if anchor else url
        classified = classify_product(game, product_name, card_text, official_url)
        if not classified.is_box:
            continue

        release_text = ""
        for row in card.select(".product-table"):
            spans = row.find_all("span")
            label = spans[0].get_text(" ", strip=True) if spans else row.get_text(" ", strip=True)
            if label in {"販売日", "発売日", "発売予定日"}:
                release_text = (
                    spans[1].get_text(" ", strip=True)
                    if len(spans) > 1
                    else row.get_text(" ", strip=True).replace(label, "", 1)
                )
                break

        parsed = parse_first_datetime(release_text)
        release_date: date | None = None
        if isinstance(parsed.value, datetime):
            release_date = parsed.value.date()
        elif isinstance(parsed.value, date):
            release_date = parsed.value
        if release_date or parsed.month_only:
            releases.append(
                Release(
                    "pokemon_card",
                    product_name,
                    classified.product_category,
                    classified.canonical_product_key,
                    release_date,
                    parsed.month_only,
                    official_url,
                    url,
                    source.source_tier,
                    "pokemon_official_product_card",
                    "high" if release_date else "medium",
                ).with_id()
            )
        else:
            alerts.append(
                Alert(
                    "pokemon_card",
                    source.id,
                    url,
                    product_name or source.name,
                    ["販売日", "発売日"],
                    "new_box_product_without_exact_release_date",
                    "BOX商品カードから発売日を解析できません",
                    None,
                    official_url,
                ).with_fingerprint()
            )
    return [], releases, alerts


__all__ = ["parse_pokemon_official_products"]
