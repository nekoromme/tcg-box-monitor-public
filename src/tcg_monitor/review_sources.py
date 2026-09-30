"""Public, read-only evidence for the two pre-release purchase reviews."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from tcg_monitor.http_client import HttpFetcher
from tcg_monitor.identity import release_title_token
from tcg_monitor.models import Release

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


@dataclass
class ContentEvidence:
    url: str = ""
    card_list_url: str = ""
    card_list_label: str = "商品別の収録紹介（全公開かは未確認）"
    card_index_url: str = ""
    complete: bool = False
    card_count: int | None = None
    total_cards: int | None = None
    msrp: int | None = None
    features: dict[str, str] = field(default_factory=dict)
    rarity_details: list[str] = field(default_factory=list)
    error: str = ""


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


def parse_content(html: str, url: str) -> ContentEvidence:
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("main, article, #main") or soup
    # Related goods often advertise a different set's limited bonus/rarity.
    for other in root.select("aside, nav, footer, #recommend, .related-products"):
        other.decompose()
    text = _text(root.get_text(" ", strip=True))
    result = ContentEvidence(url=url, card_list_url=url)
    info = root.select_one("#information, .product-information, .product-spec") or root
    specification = _text(info.get_text(" ", strip=True))
    if match := re.search(r"(?:カード種類\s*[:：]?|収録カード)\s*全\s*(\d+)\s*種", specification):
        result.total_cards = int(match[1])
    # Never mistake the per-pack price for the BOX price or invent pack counts.
    box = re.search(
        r"1\s*(?:BOX|ボックス|ボックスセット|セット)\s*[:：]?\s*([\d,]+)\s*円", specification, re.I
    )
    pack = re.search(r"1\s*パック\s*[:：]?\s*([\d,]+)\s*円", specification)
    packs = re.search(r"1\s*(?:BOX|ボックス)\s*[:：]?\s*(\d+)\s*パック", specification, re.I)
    if box:
        result.msrp = int(box[1].replace(",", ""))
    elif pack and packs:
        result.msrp = int(pack[1].replace(",", "")) * int(packs[1])
    checks = {
        "初回生産限定・初回BOX特典": r"初回(?:生産|限定|製造)|初版限定",
        "シリアル入り・枚数限定": r"シリアル(?:No\.?|ナンバー|番号)?|世界(?:で)?\d+枚限定",
        "グランドマスターレア": r"グランドマスターレア|GRANDMASTER RARE",
        "特殊イラスト・特殊仕様": (
            r"オーバーフレーム|新規(?:描き下ろし)?イラスト|アートワーク|パラレル"
        ),
    }
    for label, pattern in checks.items():
        match = re.search(pattern, text, re.I)
        # Absence of a keyword is not proof that a feature does not exist.
        value = "不明（公式記載を確認できず）"
        if re.search(
            r"(?:" + pattern + r")(?:は|の)?(?:ありません|なし|収録されません)", text, re.I
        ):
            value = "なし（公式明記）"
        elif match:
            value = "あり: " + text[max(0, match.start() - 15) : match.end() + 70]
        result.features[label] = value
    result.rarity_details = [
        line.strip()
        for line in re.findall(
            r"[^。]{0,60}(?:レア[^。]{0,30}\d+種|\d+枚限定|001[^。]{0,20}100)[^。]{0,50}",
            specification,
        )[:5]
    ]
    if serial := re.search(r"(?:001\s*[～~〜-]\s*100|(?:各|限定)\s*\d+\s*枚)", text):
        result.rarity_details.append(text[max(0, serial.start() - 35) : serial.end() + 40])
    for anchor in root.select("a[href]"):
        href = urljoin(url, str(anchor.get("href", "")))
        label = anchor.get_text(" ", strip=True)
        # A global card search is not a set-specific list.
        if (
            re.search(r"card[_-]?(?:list|search)|/cardlist/", href, re.I)
            and ("収録" in label or "カード" in label or "card" in label.lower())
            and (
                re.search(r"[?&](?:pid|series|product|expansion|category)=", href)
                or re.search(r"cardlist/.+", urlsplit(href).path)
            )
        ):
            result.card_list_url = href
            result.card_list_label = "商品ページからリンクされた収録カード一覧"
            break
    return result


def card_list_count(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("#card_list, #cardlist, .card_list, .cardlist, main") or soup
    ids = {
        match.group(0)
        for anchor in root.select("a[href]")
        if (match := re.search(r"(?:[?&]cid=|/card/)(\d+)", str(anchor.get("href"))))
    }
    return len(ids)


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
    if not prices:
        text = _text(BeautifulSoup(html, "lxml").get_text(" ", strip=True))
        if match := re.search(r"(?<!\d)1個\s*\([^)]*\)\s*[¥￥]\s*([\d,]+)", text):
            prices.append(int(match[1].replace(",", "")))
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

    def content(self, release: Release) -> ContentEvidence:
        url = release.official_url or release.source_url
        try:
            response = self.fetcher.fetch(url)
            if response.status_code != 200:
                return ContentEvidence(
                    url=url, card_list_url=url, error=f"HTTP {response.status_code}"
                )
            result = parse_content(response.text, url)
            result.card_index_url = CARD_INDEXES.get(release.game_id, "")
            # Also support product pages embedding their full card list.
            if result.card_list_url == url and result.total_cards:
                result.card_count = card_list_count(response.text)
                result.complete = result.card_count >= result.total_cards
            if result.card_list_url != url:
                cards = self.fetcher.fetch(result.card_list_url)
                if cards.status_code == 200:
                    result.card_count = card_list_count(cards.text)
                    result.complete = bool(
                        result.total_cards and result.card_count >= result.total_cards
                    )
            return result
        except Exception as exc:
            return ContentEvidence(url=url, card_list_url=url, error=type(exc).__name__)

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
