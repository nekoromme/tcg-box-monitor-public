"""Public, read-only evidence for the two pre-release purchase reviews."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from tcg_monitor.http_client import HttpFetcher
from tcg_monitor.identity import release_title_token
from tcg_monitor.models import Release
from tcg_monitor.review_content import (
    ContentEvidence as ContentEvidence,
)
from tcg_monitor.review_content import (
    card_list_count,
    normalized,
    parse_content,
    product_root,
    usable_content,
)

SNKR = "https://snkrdunk.com"
GAME_MARKERS = {
    "pokemon_card": ("ポケモン", "pokemon"),
    "one_piece_card": ("ワンピース", "one piece", "onepiece"),
    "dragon_ball_fusion_world": ("ドラゴンボール", "dragon ball"),
    "yu_gi_oh": ("遊戯王", "遊☆戯☆王", "yu-gi-oh"),
    "gundam_card": ("ガンダム", "gundam"),
    "lorcana": ("ロルカナ", "lorcana"),
}
CARD_INDEXES = {
    "pokemon_card": "https://www.pokemon-card.com/card-search/",
    "one_piece_card": "https://www.onepiece-cardgame.com/cardlist/",
    "dragon_ball_fusion_world": "https://www.dbs-cardgame.com/fw/jp/cardlist/",
    "yu_gi_oh": "https://www.db.yugioh-card.com/yugiohdb/card_list.action",
    "gundam_card": "https://www.gundam-gcg.com/jp/cards/",
    "lorcana": "https://www.takaratomy.co.jp/products/disneylorcana/cardlist/",
}
PRODUCT_INDEXES = {
    "pokemon_card": "https://www.pokemon-card.com/products/",
    "one_piece_card": "https://www.onepiece-cardgame.com/products/",
    "dragon_ball_fusion_world": "https://www.dbs-cardgame.com/fw/jp/products/",
    "yu_gi_oh": "https://www.yugioh-card.com/japan/products/",
    "gundam_card": "https://www.gundam-gcg.com/jp/products/",
    "lorcana": "https://www.takaratomy.co.jp/products/disneylorcana/product/",
}


def _official(url: str, game: str) -> bool:
    domain = (
        (urlsplit(CARD_INDEXES.get(game, "")).hostname or "")
        .removeprefix("www.")
        .removeprefix("db.")
    )
    host = urlsplit(url).hostname or ""
    return bool(domain and (host == domain or host.endswith("." + domain)))


def _product_heading(soup: BeautifulSoup, release: Release) -> bool:
    # Product logos are often images and the textual title may be h2 or h4.
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    nodes = product_root(soup).select("h1, h2, h4, .product-name")
    names = [node.get_text(" ", strip=True) for node in nodes]
    names.append(title)
    names += [str(img.get("alt", "")) for node in nodes for img in node.select("img")]
    token = _product_token(release.product_name)
    return bool(token) and any(token in _product_token(name) for name in names)


@dataclass
class PriceEvidence:
    status: str  # found / missing / error / unpriced / mismatch
    url: str = ""
    title: str = ""
    price: int | None = None
    msrp: int | None = None
    error: str = ""
    basis: str = "新品・1BOX（セット商品は1セット）の最安出品価格"


def _text(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def _amount(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    match = re.fullmatch(r"[¥￥]?\s*([\d,]+)\s*(?:円)?", str(value))
    return int(match[1].replace(",", "")) if match else None


def _json_objects(html: str) -> list[dict[str, Any]]:
    """Decode Next flight data as JSON; never execute the page's scripts."""
    soup = BeautifulSoup(html, "lxml")
    strings: list[str] = []
    for script in soup.find_all("script"):
        match = re.search(r"self\.__next_f\.push\((\[.*\])\)", script.get_text(), re.S)
        if match:
            try:
                payload = json.loads(match[1])
                if len(payload) > 1 and isinstance(payload[1], str):
                    strings.append(payload[1])
            except (ValueError, TypeError):
                continue
        elif script.get("type") == "application/json":
            strings.append(script.get_text())
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    # Concatenation also handles flight chunks splitting an object across scripts.
    raw = "".join(strings)
    for match in re.finditer(r"\{", raw):
        try:
            value, _ = decoder.raw_decode(raw[match.start() :])
        except ValueError:
            continue
        if isinstance(value, dict):
            objects.append(value)
    return objects


def _product_token(name: str) -> str:
    # Marketplace translations must preserve distinguishing subtitles/editions.
    name = re.sub(
        r"yu-gi-oh\s*(?:ocg)?\s*(?:duel monsters)?|遊[☆・]?戯[☆・]?王(?:OCG)?"
        r"(?:\s*デュエルモンスターズ)?|(?:JP|Japanese)\s+Edition|日本(?:語)?版"
        r"|スペシャルパック|special pack|\bbox\b",
        "",
        _text(name),
        flags=re.I,
    )
    token = release_title_token(name)
    aliases = {
        "オリジナルアートワークコレクション": "originalartworkcollection",
        "リミットオーバーコレクション": "limitovercollection",
        "ザライバルズ": "therivals",
        "ザヒーローズ": "theheroes",
        "リミテッドパック": "limitedpack",
        "リミテッド": "limited",
        "クォーターセンチュリー": "quartercentury",
        "レアリティコレクション": "raritycollection",
    }
    for japanese, english in aliases.items():
        token = token.replace(japanese, english)
    return re.sub(r"^(?:遊戯王|yugioh)", "", token)


def product_matches(release: Release, names: list[str]) -> bool:
    combined = _text(" ".join(names)).casefold()
    if re.search(
        r"韓国版|英語版|中国語|アジア版|海外版|再販|再版|korean|english edition|asia edition",
        combined,
    ):
        return False
    if not any(marker.casefold() in combined for marker in GAME_MARKERS.get(release.game_id, ())):
        return False
    if not re.search(
        r"ボックス|\bbox\b|デッキセット|deck set|プレミアムセット|premium set", combined
    ):
        return False
    token = _product_token(release.product_name)
    return len(token) >= 4 and any(token == _product_token(name) for name in names)


def parse_snkr_price(html: str, url: str, release: Release) -> PriceEvidence:
    objects = _json_objects(html)
    product_id = int(urlsplit(url).path.rstrip("/").split("/")[-1])
    product = next(
        (
            obj
            for obj in objects
            if obj.get("id") == product_id and "regularPrice" in obj and "localizedName" in obj
        ),
        None,
    )
    if product is None:
        return PriceEvidence("error", url=url, error="商品データ形式を確認できず")
    currency = product.get("currency", product.get("currencyCode"))
    display_regular = str(product.get("displayRegularPrice", ""))
    rendered = _text(BeautifulSoup(html, "lxml").get_text(" ", strip=True))
    quantity_yen = re.search(r"(?<!\d)1個\s*\([^)]*\)\s*[¥￥]\s*([\d,]+)", rendered)
    if (currency and currency != "JPY") or not (
        currency == "JPY" or re.match(r"[¥￥]", display_regular) or quantity_yen
    ):
        return PriceEvidence("error", url=url, error="日本円の価格と確認できず")
    names = [str(product.get(key, "")) for key in ("name", "localizedName")]
    if not product_matches(release, names):
        return PriceEvidence("mismatch", url=url, title=names[1], error="商品名・言語・単位不一致")
    # If a date is provided it must identify this release, not a reprint/other edition.
    if release.release_date and (raw_date := product.get("displayReleasedAt")):
        match = re.search(r"(\d{4})年(\d+)月(\d+)日", str(raw_date))
        if match and tuple(map(int, match.groups())) != (
            release.release_date.year,
            release.release_date.month,
            release.release_date.day,
        ):
            return PriceEvidence("mismatch", url=url, error="発売日不一致")
    # minPrice is a catalog-wide minimum and must NEVER be used for quantity=1.
    prices: list[int] = []
    for group in objects:
        if group.get("apparelId") != product_id or not isinstance(group.get("listings"), list):
            continue
        for obj in group["listings"]:
            variant = obj.get("variant") if isinstance(obj, dict) else None
            if not isinstance(variant, dict):
                continue
            if variant.get("sizeName", variant.get("localizedName")) == "1個" and (
                price := _amount(obj.get("minNewListingPrice"))
            ):
                prices.append(price)
    # Rendered quantity rows support the same page when data keys change.
    if not prices and quantity_yen:
        prices.append(int(quantity_yen[1].replace(",", "")))
    return PriceEvidence(
        "found" if prices else "unpriced",
        url=url,
        title=names[1],
        price=min(prices) if prices else None,
        msrp=_amount(product.get("regularPrice")),
        error="" if prices else "1個の新品出品価格を確認できず",
    )


class ReviewSource:
    def __init__(self, fetcher: HttpFetcher) -> None:
        self.fetcher = fetcher

    def _product_url(self, release: Release, url: str) -> str:
        """Resolve retailer-only releases through the official catalog, never its text."""
        index = PRODUCT_INDEXES.get(release.game_id, "")
        if _official(url, release.game_id) and url.rstrip("/") != index.rstrip("/"):
            return url
        if not index:
            return ""
        response = self.fetcher.fetch(index)
        if response.status_code != 200:
            return ""
        root = product_root(BeautifulSoup(response.text, "lxml"))
        token = _product_token(release.product_name)
        for anchor in root.select("a[href]"):
            name = (
                anchor.get_text(" ", strip=True)
                + " "
                + " ".join(str(img.get("alt", "")) for img in anchor.select("img"))
            )
            href = urljoin(index, str(anchor.get("href", ""))).split("#")[0]
            if token and token in _product_token(name) and _official(href, release.game_id):
                return href
        return ""

    def _card_list(self, release: Release, result: ContentEvidence, product_html: str) -> None:
        index = result.card_index_url
        if result.card_list_url != result.url:
            if not _official(result.card_list_url, release.game_id):
                result.list_status = "収録一覧リンクが公式ドメイン外のため確認保留"
                return
            cards = self.fetcher.fetch(result.card_list_url)
            if cards.status_code != 200:
                result.list_status = f"収録一覧の取得失敗（HTTP {cards.status_code}）・再確認対象"
                return
            result.card_count = card_list_count(cards.text)
        elif release.game_id in {"one_piece_card", "dragon_ball_fusion_world", "gundam_card"}:
            response = self.fetcher.fetch(index)
            if response.status_code != 200:
                result.list_status = f"公式カード検索の取得失敗（HTTP {response.status_code}）"
                return
            soup = BeautifulSoup(response.text, "lxml")
            code = re.search(r"(?:OP|EB|PRB)-\d{2}|(?:FB|SB|GD)\d{2}", release.product_name, re.I)
            if not code:
                result.list_status = "対象弾の検索条件を照合できず"
                return
            selected = next(
                (
                    node
                    for node in soup.select("option[value], a[data-val]")
                    if re.search(
                        r"(?<![A-Z0-9])" + re.escape(code[0]) + r"(?![A-Z0-9])",
                        normalized(node.get_text(" ", strip=True)),
                        re.I,
                    )
                ),
                None,
            )
            if selected is None:
                result.list_status = "公式カード検索に対象弾の選択肢なし（商品紹介と一覧公開は別）"
                return
            value = str(selected.get("value") or selected.get("data-val") or "")
            if not value.isdigit():
                result.list_status = "対象弾の検索条件が不明"
                return
            parameter = {
                "one_piece_card": "series",
                "dragon_ball_fusion_world": "category[]",
                "gundam_card": "package",
            }[release.game_id]
            target = index + "?" + urlencode({"search": "true", parameter: value})
            cards = self.fetcher.fetch(target)
            if cards.status_code != 200:
                result.list_status = f"収録一覧の取得失敗（HTTP {cards.status_code}）"
                return
            filtered = BeautifulSoup(cards.text, "lxml")
            # A provider can ignore a stale query and render its newest set.
            # Confirm the selected option before counting unrelated cards.
            active = filtered.select(
                "option[selected], a.is-active[data-val], a.is-current[data-val]"
            )
            if not any(str(node.get("value") or node.get("data-val")) == value for node in active):
                result.list_status = "対象弾の絞込み結果を照合できず・再確認対象"
                return
            result.card_list_url = target
            result.card_list_label = "公式カード検索を対象弾で絞った収録一覧"
            result.card_count = card_list_count(cards.text)
        elif release.game_id == "lorcana":
            # The list is JavaScript-rendered. Read its published set choices;
            # an empty HTML shell is neither 0 cards nor proof of nonpublication.
            script = urljoin(index, "../common/components/js/env.js")
            response = self.fetcher.fetch(script)
            if response.status_code != 200 or "formDefault" not in response.text:
                result.list_status = "公式検索の収録弾設定を取得できず・再確認対象"
                return
            block = re.search(r"sets:\s*\{\s*sets:\s*\[([\s\S]*?)\]", response.text)
            if not block:
                result.list_status = "公式検索の収録弾設定を解析できず・再確認対象"
                return
            token = _product_token(release.product_name)
            names = re.findall(r"'([^']+)'", block[1])
            name = next((name for name in names if token in _product_token(name)), "")
            if name:
                result.card_index_url = index + "?" + urlencode({"sets[]": name})
                result.list_status = "対象弾の検索条件を確認（動的な検索結果の全公開は未確認）"
            else:
                result.list_status = "公式カード検索に対象弾の選択肢なし（商品紹介は公開済み）"
            return
        else:
            result.card_count = card_list_count(product_html)
        result.complete = bool(
            result.total_cards and result.card_count and result.card_count == result.total_cards
        )
        result.list_status = (
            "基本カードの種類数と一覧の重複除去件数が一致・特殊仕様の全公開は未確認"
            if result.complete
            else "商品別の一覧件数を確認・全公開は未確認"
        )

    def content(self, release: Release) -> ContentEvidence:
        url = release.official_url or release.source_url
        index = CARD_INDEXES.get(release.game_id, "")
        try:
            url = self._product_url(release, url)
            if not url:
                return ContentEvidence(
                    url=release.official_url or release.source_url,
                    card_index_url=index,
                    error="公式の商品別ページが未確認（公式カタログも照合済み）",
                )
            response = self.fetcher.fetch(url)
            if response.status_code != 200:
                return ContentEvidence(
                    url=url,
                    card_list_url=url,
                    card_index_url=index,
                    error=f"HTTP {response.status_code}",
                )
            soup = BeautifulSoup(response.text, "lxml")
            if not _product_heading(soup, release):
                return ContentEvidence(
                    url=url,
                    card_index_url=index,
                    card_list_label="商品ページ照合未完了",
                    error="商品名をページ見出しで確認できず",
                )
            result = parse_content(response.text, url)
            result.card_index_url = index
            try:
                self._card_list(release, result, response.text)
            except Exception as exc:
                # A failed list fetch must not discard successfully read content/BOX price.
                result.list_status = f"収録一覧の取得失敗（{type(exc).__name__}）・再確認対象"
            if not usable_content(result):
                result.error = (
                    "商品ページ取得済み・判断に必要な収録内容を抽出できず（未発表とは未確定）"
                )
            return result
        except Exception as exc:
            return ContentEvidence(
                url=url, card_list_url=url, card_index_url=index, error=type(exc).__name__
            )

    def price(self, release: Release, known_url: str = "") -> PriceEvidence:
        candidates: list[str] = []
        if re.fullmatch(r"https://snkrdunk\.com/apparels/\d+/?", known_url):
            candidates.append(known_url)
        if not candidates:
            # This public search page renders product links without requiring login.
            query = re.findall(r"[「『\"]([^」』\"]+)[」』\"]", release.product_name)
            keyword = max(query, key=len) if query else release.product_name
            url = SNKR + "/search?" + urlencode({"keywords": keyword})
            try:
                result = self.fetcher.fetch(url)
                if result.status_code != 200:
                    return PriceEvidence("error", url=url, error=f"検索HTTP {result.status_code}")
                soup = BeautifulSoup(result.text, "lxml")
                if not soup.title or "おすすめアイテム" not in soup.title.get_text():
                    return PriceEvidence("error", url=url, error="検索ページ形式を確認できず")
                for anchor in soup.select("a[href]"):
                    href = urljoin(SNKR, str(anchor.get("href", ""))).split("?")[0]
                    names = [anchor.get_text(" ", strip=True), str(anchor.get("aria-label", ""))]
                    names.extend(str(img.get("alt", "")) for img in anchor.select("img"))
                    if (
                        re.fullmatch(r"https://snkrdunk\.com/apparels/\d+/?", href)
                        and product_matches(release, names)
                        and href not in candidates
                    ):
                        candidates.append(href)
                if not candidates:
                    return PriceEvidence("missing", url=url, error="一致する商品ページ未発見")
            except Exception as exc:
                return PriceEvidence("error", url=url, error=type(exc).__name__)
        last = PriceEvidence("missing")
        for url in candidates[:3]:
            try:
                response = self.fetcher.fetch(url)
                if response.status_code == 404:
                    last = PriceEvidence("missing", url=url, error="商品ページ404")
                elif response.status_code != 200:
                    last = PriceEvidence("error", url=url, error=f"HTTP {response.status_code}")
                else:
                    last = parse_snkr_price(response.text, url, release)
                    if last.status in {"found", "unpriced"}:
                        return last
            except Exception as exc:
                last = PriceEvidence("error", url=url, error=type(exc).__name__)
        return last
