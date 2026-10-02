"""Read product content without confusing a pack, a preview, and a full set list."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

CONTENT_VERSION = 2


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
    version: int = 0  # Old saved evidence remains readable, and is refreshed once.
    highlights: list[str] = field(default_factory=list)
    preview_images: int = 0  # An image can contain several cards. Never call this a card count.
    list_status: str = ""


def normalized(value: str) -> str:
    text = unicodedata.normalize("NFKC", value)
    return re.sub(r"[\u200b-\u200d\ufeff]", "", text)


def product_root(soup: BeautifulSoup) -> Tag:
    root = soup.select_one("main, article, #main") or soup
    # Product help modals and related products describe OTHER sets. Their bonus,
    # price and pictures must never become evidence for the current product.
    for other in root.select(
        "aside, nav, footer, script, style, #recommend, .related-products, "
        ".relatedCol, .wtModalCol, .wtModalPointCol, .c-breadcrumb"
    ):
        other.decompose()
    return root


def usable_content(value: ContentEvidence) -> bool:
    """Unknown checkboxes alone are not a successful content extraction."""
    return (
        bool(
            value.complete
            or value.card_count
            or value.highlights
            or value.preview_images
            or value.rarity_details
            or any(text.startswith("あり") for text in value.features.values())
        )
        and not value.error
    )


def parse_content(html: str, url: str) -> ContentEvidence:
    root = product_root(BeautifulSoup(html, "lxml"))
    text = normalized(root.get_text(" ", strip=True))
    result = ContentEvidence(url=url, card_list_url=url, version=CONTENT_VERSION)
    info = (
        root.select_one(
            "#information, .product-information, .product-spec, .detailColStatus, "
            ".detailBoxList, section.detailCol, .p-product-detail__table"
        )
        or root
    )
    specification = normalized(info.get_text(" ", strip=True))
    # Prefer the base set specification over the separate bonus pack's count.
    for pattern in (
        r"(?:カード種類\s*[:：]?|種類数|収録カード)\s*全\s*(\d+)\s*種",
        r"全\s*(\d+)\s*種",
        r"レアリティ\s*(\d+)\s*種",
    ):
        if match := re.search(pattern, specification):
            result.total_cards = int(match[1])
            break
    # Both '1BOX: 5,280円' and '1BOX16パック入り: 5,280円' are official formats.
    box = re.search(
        r"1\s*(?:BOX|ボックス|ボックスセット|セット)"
        r"(?:\s*\d+\s*パック(?:入り)?)?\s*[:：]?\s*([\d,]+)\s*円",
        specification,
        re.I,
    )
    pack = re.search(
        r"1\s*パック(?:\s*\d+\s*枚(?:入り)?)?\s*[:：]?\s*([\d,]+)\s*円",
        specification,
    )
    packs = re.search(r"1\s*(?:BOX|ボックス)\s*[:：]?\s*(\d+)\s*パック", specification, re.I)
    if box:
        result.msrp = int(box[1].replace(",", ""))
    elif pack and packs:
        result.msrp = int(pack[1].replace(",", "")) * int(packs[1])
    # A standalone pack price with no documented BOX quantity stays unknown.
    checks = {
        "初回生産限定・初回BOX特典": r"初回(?:生産|限定|製造)|初版限定",
        "BOX同梱・購入特典（初回限定とは別）": (
            r"(?:ボックス|BOX)(?:同梱|購入)?特典|(?:ボックス|BOX)購入特典"
        ),
        "シリアル入り・枚数限定": r"シリアル(?:No\.?|ナンバー|番号)?|世界(?:で)?\d+枚限定",
        "グランドマスターレア": r"グランドマスターレア|GRANDMASTER RARE",
        "特殊イラスト・特殊仕様": (
            r"オーバーフレーム|新規(?:描き下ろし)?イラスト|アートワーク|パラレル"
        ),
        "作品固有の特殊レア": (
            r"アイコニック|エンチャンテッド|エピック|キュレーターズ[・･]ライブラリー"
            r"|スーパーパラレル|スペシャルカード|プリズマティックシークレット"
        ),
    }
    for label, pattern in checks.items():
        match = re.search(pattern, text, re.I)
        value = "不明（公式記載を確認できず）"
        if re.search(
            r"(?:" + pattern + r")(?:は|の)?(?:ありません|なし|収録されません)", text, re.I
        ):
            value = "なし（公式明記）"
        elif match:
            value = "あり: " + text[max(0, match.start() - 15) : match.end() + 90]
        result.features[label] = value
    # Preserve the product's actual description, not just generic expectation labels.
    for node in root.select("p, h2, h3, h4, dd, .detailBoxCont"):
        line = normalized(node.get_text(" ", strip=True))
        if (
            12 <= len(line) <= 450
            and re.search(
                r"アイコニック|エンチャンテッド|キュレーターズ|特典|新要素|初登場"
                r"|新カード|参戦|新テーマ|新規イラスト|描き下ろし|ヒロイン|レアリティ|種類数",
                line,
            )
            and line not in result.highlights
        ):
            result.highlights.append(line[:240])
    # Prefer descriptions over duplicated titles, preserving bonuses near the bottom.
    result.highlights = [line for line in result.highlights if not line.startswith("■")][:8]
    result.rarity_details = [
        line.strip()[:240]
        for line in re.findall(
            r"[^。]{0,60}(?:レア[^。]{0,30}\d+種|\d+枚限定|001[^。]{0,20}100)[^。]{0,50}",
            specification,
        )[:5]
    ]
    if serial := re.search(r"(?:001\s*[～~〜-]\s*100|(?:各|限定)\s*\d+\s*枚)", text):
        result.rarity_details.append(text[max(0, serial.start() - 35) : serial.end() + 40])
    previews = set()
    for img in root.select("img"):
        src = str(img.get("data-src") or img.get("src") or "")
        if re.search(r"(?:pic_card\d|/card/|/cardlist/card/|/cards/card/)", src):
            previews.add(urljoin(url, src).split("?")[0])
    result.preview_images = len(previews)
    for anchor in root.select("a[href]"):
        href = urljoin(url, str(anchor.get("href", "")))
        label = anchor.get_text(" ", strip=True)
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
    # Konami uses a GET form rather than a link for its product-filtered list.
    for form in root.select("form[action]"):
        action = urljoin(url, str(form.get("action")))
        pid = form.select_one('input[name="pid"][value]')
        if "yugiohdb/card_search.action" in action and pid:
            result.card_list_url = action + "?ope=1&pid=" + str(pid.get("value"))
            result.card_list_label = "商品ページの検索フォームで絞った収録カード一覧"
            break
    return result


def card_list_count(html: str) -> int:
    root = product_root(BeautifulSoup(html, "lxml"))
    root = root.select_one("#card_list, #cardlist, .card_list, .cardlist") or root
    ids: set[str] = set()
    for anchor in root.select("a[href], a[data-src]"):
        href = str(anchor.get("data-src") or anchor.get("href") or "")
        if match := re.search(r"(?:[?&]cid=|/card/)(\d+)", href):
            ids.add("cid:" + match[1])
    for img in root.select("img"):
        src = str(img.get("data-src") or img.get("src") or "")
        # Parallel art and duplicate desktop/mobile images do not add base kinds.
        if match := re.search(r"/(?:card|cards)/[^?]*?((?:OP|EB|PRB|FB|SB|GD|ST)\d{2}-\d{3})", src):
            ids.add(match[1])
    return len(ids)
