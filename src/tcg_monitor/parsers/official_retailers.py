from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import (
    normalize_text,
    parse_first_datetime,
    parse_period_start,
)
from tcg_monitor.models import (
    Alert,
    Config,
    LotteryCase,
    OpportunityKind,
    Release,
    SourceConfig,
)
from tcg_monitor.parsers.common import title, visible_text

KONAMI_STYLE_SOURCE = "konami_style_yugioh"
TAKARATOMY_MALL_SOURCE = "takaratomy_mall_lorcana"
ONEPIECE_SHOP_SOURCE = "onepiece_official_shop_news"
PREMIUM_BANDAI_DB_SOURCE = "premium_bandai_dragonball"

_SOURCE_IDS = {
    KONAMI_STYLE_SOURCE,
    TAKARATOMY_MALL_SOURCE,
    ONEPIECE_SHOP_SOURCE,
    PREMIUM_BANDAI_DB_SOURCE,
}
_ONEPIECE_NEWS = re.compile(
    r"^/official_shop/onepiece-cardgame/news/(?:important|information)/\d+\.html$",
    re.I,
)
_P_BANDAI_ITEM = re.compile(r"^/item/item-\d+/?$", re.I)
_TAKARATOMY_ITEM = re.compile(r"^/shop/g/g[A-Za-z0-9]+/?$", re.I)

_PENDING_DETAIL_MARKERS = (
    "詳細は後日",
    "準備が整い次第",
    "応募開始日は後日",
    "抽選開始日は後日",
    "事前抽選を予定",
)


def is_official_retailer_source(source_id: str) -> bool:
    return source_id in _SOURCE_IDS


def is_official_retailer_index(source_id: str, url: str) -> bool:
    """Return whether ``url`` is the list page for one added maker store."""

    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    if source_id == KONAMI_STYLE_SOURCE:
        return (
            parts.netloc.casefold() in {"www.konamistyle.jp", "konamistyle.jp"}
            and path == "/products/list.php"
        )
    if source_id == TAKARATOMY_MALL_SOURCE:
        return parts.netloc.casefold() == "takaratomymall.jp" and path in {
            "/shop/c/cLorcana",
            "/shop/goods/search.aspx",
        }
    if source_id == ONEPIECE_SHOP_SOURCE:
        return (
            parts.netloc.casefold() == "bandainamco-am.co.jp"
            and path == "/official_shop/onepiece-cardgame"
        )
    if source_id == PREMIUM_BANDAI_DB_SOURCE:
        return parts.netloc.casefold() == "p-bandai.jp" and path == "/brand/b0062"
    return False


def _anchor_context(anchor: Tag) -> str:
    """Read a product card without accidentally swallowing the whole list page."""

    values = [anchor.get_text(" ", strip=True)]
    for image in anchor.find_all("img"):
        values.extend(
            str(image.get(attribute) or "")
            for attribute in ("alt", "title")
        )
    parent = anchor.parent
    for _ in range(3):
        if not isinstance(parent, Tag):
            break
        if parent.name in {"main", "body", "html"}:
            break
        parent_text = parent.get_text(" ", strip=True)
        if parent_text and len(parent_text) <= 1_500:
            values.append(parent_text)
            if parent.name in {"article", "li"}:
                break
        parent = parent.parent
    return re.sub(r"\s+", " ", " ".join(values)).strip()


def _clean_candidate(source_id: str, value: str) -> str:
    """Drop tracking queries while retaining KONAMI's identifying product ID."""

    parts = urlsplit(value)
    if source_id == KONAMI_STYLE_SOURCE:
        product_id = parse_qs(parts.query).get("product_id", [])
        query = urlencode({"product_id": product_id[0]}) if product_id else ""
    else:
        query = ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _konami_candidate(candidate: str, context: str, config: Config) -> bool:
    parts = urlsplit(candidate)
    product_id = parse_qs(parts.query).get("product_id", [])
    game = config.games["yu_gi_oh"]
    has_box_shape = any(word in context for word in game.box_product_keywords) or bool(
        re.search(r"(?i)(?:\b1?BOX\b|\b\d+\s*Pack\b|\(\d+Pack\))", context)
    )
    return (
        parts.netloc.casefold() in {"www.konamistyle.jp", "konamistyle.jp"}
        and parts.path == "/products/detail.php"
        and bool(product_id and product_id[0].isdigit())
        and any(word in context for word in ("遊戯王OCG", "遊☆戯☆王", "遊戯王"))
        and has_box_shape
        and not any(
            word in context
            for word in game.product_exclude_keywords
        )
    )


def _takaratomy_candidate(candidate: str, context: str) -> bool:
    parts = urlsplit(candidate)
    compact = re.sub(r"\s+", "", context).casefold()
    has_game = "ロルカナ" in compact or "lorcana" in compact
    has_box = any(word.casefold() in compact for word in ("BOX販売", "DP-BOX", "1BOX"))
    excluded = any(
        word.casefold() in compact
        for word in ("カートン", "はじめるセット", "構築済みデッキ")
    )
    return (
        parts.netloc.casefold() == "takaratomymall.jp"
        and bool(_TAKARATOMY_ITEM.fullmatch(parts.path))
        and has_game
        and has_box
        and not excluded
    )


def _onepiece_candidate(candidate: str, context: str) -> bool:
    parts = urlsplit(candidate)
    return (
        parts.netloc.casefold() == "bandainamco-am.co.jp"
        and bool(_ONEPIECE_NEWS.fullmatch(parts.path))
        and "抽選" in context
        and (
            "ブースターパック" in context
            or bool(re.search(r"\b(?:OP|EB|PRB)-\d{2}\b", context, re.I))
        )
    )


def _premium_bandai_candidate(candidate: str, context: str) -> bool:
    parts = urlsplit(candidate)
    has_game = any(
        word in context
        for word in (
            "ドラゴンボールスーパーカードゲーム",
            "フュージョンワールド",
            "DBFW",
        )
    )
    has_box = any(
        word in context
        for word in ("ブースターパック", "MANGA BOOSTER", "STORY BOOSTER")
    )
    return (
        parts.netloc.casefold() == "p-bandai.jp"
        and bool(_P_BANDAI_ITEM.fullmatch(parts.path))
        and has_game
        and has_box
    )


def discover_official_retailer_urls(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    limit: int = 20,
) -> list[str]:
    """Find only public, relevant detail pages from each official store list."""

    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    source_limit = min(
        limit,
        {
            KONAMI_STYLE_SOURCE: 12,
            TAKARATOMY_MALL_SOURCE: 16,
            ONEPIECE_SHOP_SOURCE: 12,
            PREMIUM_BANDAI_DB_SOURCE: 12,
        }.get(source.id, limit),
    )
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        candidate = _clean_candidate(
            source.id,
            urljoin(url, str(anchor.get("href") or "")),
        )
        context = _anchor_context(anchor)
        allowed = False
        if source.id == KONAMI_STYLE_SOURCE:
            allowed = _konami_candidate(candidate, context, config)
        elif source.id == TAKARATOMY_MALL_SOURCE:
            allowed = _takaratomy_candidate(candidate, context)
        elif source.id == ONEPIECE_SHOP_SOURCE:
            allowed = _onepiece_candidate(candidate, context)
        elif source.id == PREMIUM_BANDAI_DB_SOURCE:
            allowed = _premium_bandai_candidate(candidate, context)
        if allowed and candidate not in found:
            found.append(candidate)
        if len(found) >= source_limit:
            break
    return found


def official_retailer_index_should_have_links(source_id: str, html: str) -> bool:
    """Avoid alarms when a news/lottery list legitimately has no active campaign."""

    if source_id in {KONAMI_STYLE_SOURCE, TAKARATOMY_MALL_SOURCE}:
        # These are permanent product catalogs and should always expose BOX links.
        return True
    text = visible_text(html)
    if source_id == ONEPIECE_SHOP_SOURCE:
        return "抽選" in text and "ブースターパック" in text
    if source_id == PREMIUM_BANDAI_DB_SOURCE:
        return (
            "抽選" in text
            and any(word in text for word in ("フュージョンワールド", "DBFW"))
            and "ブースターパック" in text
        )
    return False


def _product_page(html: str, fallback: str) -> tuple[BeautifulSoup, str, str]:
    """Return the heading and text at/after it, excluding unrelated page banners."""

    soup = BeautifulSoup(html, "lxml")
    heading = soup.find("h1")
    product_name = (
        heading.get_text(" ", strip=True)
        if isinstance(heading, Tag)
        else title(html) or fallback
    )
    if isinstance(heading, Tag):
        text_parts = [product_name]
        text_length = len(product_name)
        for node in heading.next_elements:
            if isinstance(node, Tag) and node.name == "footer":
                break
            if not isinstance(node, NavigableString) or not node.strip():
                continue
            parent = node.parent
            if isinstance(parent, Tag) and parent.name in {"script", "style", "noscript"}:
                continue
            value = str(node).strip()
            text_parts.append(value)
            text_length += len(value)
            if text_length >= 20_000:
                break
        product_text = re.sub(r"\s+", " ", " ".join(text_parts)).strip()
    else:
        product_text = visible_text(html)
    return soup, re.sub(r"\s+", " ", product_name).strip(), product_text


def _range_end(scope: str, start_at: datetime | date) -> datetime | date | None:
    normalized = normalize_text(scope)
    match = re.search(r"(?:~|→)(.{1,220})", normalized)
    if not match:
        return None
    base_date = start_at.date() if isinstance(start_at, datetime) else start_at
    remainder = match.group(1)
    parsed = parse_first_datetime(remainder, base_date).value
    if parsed:
        return parsed
    # Official Bandai articles commonly shorten
    # ``8月12日 10:00 ～ 16日 23:59``.  The shared parser intentionally does
    # not guess a missing month, but inside one explicit range the start month
    # is unambiguous.
    if re.match(r"\s*\d{1,2}日", remainder):
        expanded = f"{base_date.year}年{base_date.month}月{remainder.lstrip()}"
        return parse_first_datetime(expanded, base_date).value
    return None


def _labelled_period(
    text: str,
    labels: list[str] | tuple[str, ...],
) -> tuple[datetime | date | None, datetime | date | None]:
    """Parse the first complete period attached to an explicit start label."""

    for label in sorted({item for item in labels if item}, key=len, reverse=True):
        search_from = 0
        while (index := text.find(label, search_from)) >= 0:
            scope_start = index + len(label)
            scope = text[scope_start : scope_start + 360]
            parsed = parse_period_start(
                scope,
                label_is_start=label.endswith(("開始", "開始日時")),
            )
            if parsed.value:
                return parsed.value, _range_end(scope, parsed.value)
            search_from = scope_start
    return None, None


def _application_link(soup: BeautifulSoup, article_url: str) -> str:
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        candidate = _clean_candidate(
            ONEPIECE_SHOP_SOURCE,
            urljoin(article_url, str(anchor.get("href") or "")),
        )
        if urlsplit(candidate).netloc.casefold() == "parks2.bandainamco-am.co.jp":
            return candidate
    return article_url


def _missing_start_alert(
    game_id: str,
    source: SourceConfig,
    url: str,
    product_name: str,
    summary: str,
) -> Alert:
    return Alert(
        game_id,
        source.id,
        url,
        product_name,
        ["受付期間", "開始"],
        "official_store_start_missing",
        summary,
        None,
        url,
    ).with_fingerprint()


def parse_onepiece_official_shop(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    soup, product_name, product_text = _product_page(html, source.name)
    product_name = re.sub(r"(?:事前)?抽選について.*$", "", product_name).strip(" 『』")
    classified = classify_product(
        config.games["one_piece_card"],
        product_name,
        product_text,
        url,
    )
    if not classified.is_box or "抽選" not in product_text:
        return [], [], []

    start_at, end_at = _labelled_period(product_text, source.start_labels)
    if not start_at:
        if any(marker in product_text for marker in _PENDING_DETAIL_MARKERS):
            return [], [], []
        return [], [], [
            _missing_start_alert(
                "one_piece_card",
                source,
                url,
                product_name,
                "公式ショップのBOX抽選記事から申込開始日時を解析できません",
            )
        ]

    case = LotteryCase(
        "one_piece_card",
        "onepiece_official_shop",
        "ONE PIECEカードゲーム公式ショップ",
        product_name,
        classified.product_category,
        classified.canonical_product_key,
        start_at,
        _application_link(soup, url),
        url,
        source.source_tier,
        "onepiece_official_shop_labelled_period",
        "high",
        opportunity_kind=OpportunityKind.LOTTERY,
        end_at=end_at,
    ).with_id()
    return [case], [], []


def parse_konami_style(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    _, product_name, product_text = _product_page(html, source.name)
    product_name = re.sub(r"^【[^】]*(?:お届け|抽選販売分)[^】]*】\s*", "", product_name)
    classification_text = product_text.replace("ボックス", "BOX")
    classified = classify_product(
        config.games["yu_gi_oh"],
        product_name,
        classification_text,
        url,
    )
    if not classified.is_box:
        return [], [], []

    is_lottery = "抽選" in product_text and any(
        word in product_text for word in ("抽選販売", "抽選申込", "先着順ではありません")
    )
    is_direct_sale = any(
        word in product_text
        for word in ("受注生産", "注文受付期間", "予約受付期間")
    )
    if not is_lottery and not is_direct_sale:
        return [], [], []

    start_at, end_at = _labelled_period(product_text, source.start_labels)
    if not start_at:
        return [], [], [
            _missing_start_alert(
                "yu_gi_oh",
                source,
                url,
                product_name,
                "KONAMI STYLEの対象BOXから申込・注文開始日時を解析できません",
            )
        ]

    kind = OpportunityKind.LOTTERY if is_lottery else OpportunityKind.DIRECT_SALE
    case = LotteryCase(
        "yu_gi_oh",
        "konami_style",
        "KONAMI STYLE",
        product_name,
        classified.product_category,
        classified.canonical_product_key,
        start_at,
        url,
        url,
        source.source_tier,
        "konami_style_labelled_period",
        "high",
        opportunity_kind=kind,
        end_at=end_at,
    ).with_id()
    return [case], [], []


def parse_takaratomy_mall(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    today: date | None = None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    _, product_name, product_text = _product_page(html, source.name)
    compact_name = re.sub(r"\s+", "", product_name)
    if not any(word in compact_name for word in ("BOX販売", "DP-BOX", "1BOX")):
        return [], [], []
    if any(word in compact_name for word in ("カートン", "はじめるセット")):
        return [], [], []

    classified = classify_product(
        config.games["lorcana"],
        product_name,
        product_text,
    )
    if not classified.is_box:
        return [], [], []

    is_lottery = "抽選販売" in product_text
    explicit_sale = any(
        word in product_text
        for word in ("予約受付期間", "販売期間", "注文受付期間", "販売開始", "予約開始")
    )
    if is_lottery or explicit_sale:
        start_at, end_at = _labelled_period(product_text, source.start_labels)
        if not start_at:
            return [], [], [
                _missing_start_alert(
                    "lorcana",
                    source,
                    url,
                    product_name,
                    "タカラトミーモールの対象BOXから販売開始日時を解析できません",
                )
            ]
        kind = OpportunityKind.LOTTERY if is_lottery else OpportunityKind.DIRECT_SALE
        method = "takaratomy_mall_labelled_period"
        confidence = "high"
    else:
        # A generic purchase-benefit campaign can appear above every product.  It
        # is deliberately outside ``product_text`` and must never become the BOX
        # sale date.  With no product-specific period, notify only when the BOX
        # itself is visibly purchasable.
        available = any(
            marker in product_text
            for marker in ("カートに入れる", "予約受付中", "○在庫あり", "在庫あり")
        ) and "×在庫なし" not in product_text
        if not available:
            return [], [], []
        start_at = today or datetime.now(ZoneInfo(config.timezone)).date()
        end_at = None
        kind = OpportunityKind.DIRECT_SALE_SEEN
        method = "takaratomy_mall_first_seen_available"
        confidence = "medium"

    case = LotteryCase(
        "lorcana",
        "takaratomy_mall",
        "タカラトミーモール",
        product_name,
        classified.product_category,
        classified.canonical_product_key,
        start_at,
        url,
        url,
        source.source_tier,
        method,
        confidence,
        opportunity_kind=kind,
        end_at=end_at,
    ).with_id()
    return [case], [], []


def parse_premium_bandai_dragonball(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    _, product_name, product_text = _product_page(html, source.name)
    product_name = re.sub(r"^【抽選販売】\s*", "", product_name)
    classified = classify_product(
        config.games["dragon_ball_fusion_world"],
        product_name,
        product_text,
        url,
    )
    if not classified.is_box or "抽選販売" not in product_text:
        return [], [], []

    start_at, end_at = _labelled_period(product_text, source.start_labels)
    if not start_at:
        return [], [], [
            _missing_start_alert(
                "dragon_ball_fusion_world",
                source,
                url,
                product_name,
                "プレミアムバンダイの対象BOXから抽選受付開始日時を解析できません",
            )
        ]

    case = LotteryCase(
        "dragon_ball_fusion_world",
        "premium_bandai",
        "プレミアムバンダイ",
        product_name,
        classified.product_category,
        classified.canonical_product_key,
        start_at,
        url,
        url,
        source.source_tier,
        "premium_bandai_labelled_period",
        "high",
        opportunity_kind=OpportunityKind.LOTTERY,
        end_at=end_at,
    ).with_id()
    return [case], [], []


def parse_official_retailer_detail(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    if source.id == KONAMI_STYLE_SOURCE:
        return parse_konami_style(html, url, source, config)
    if source.id == TAKARATOMY_MALL_SOURCE:
        return parse_takaratomy_mall(html, url, source, config)
    if source.id == ONEPIECE_SHOP_SOURCE:
        return parse_onepiece_official_shop(html, url, source, config)
    if source.id == PREMIUM_BANDAI_DB_SOURCE:
        return parse_premium_bandai_dragonball(html, url, source, config)
    raise ValueError(f"unsupported official retailer source: {source.id}")


__all__ = [
    "KONAMI_STYLE_SOURCE",
    "ONEPIECE_SHOP_SOURCE",
    "PREMIUM_BANDAI_DB_SOURCE",
    "TAKARATOMY_MALL_SOURCE",
    "discover_official_retailer_urls",
    "is_official_retailer_index",
    "is_official_retailer_source",
    "official_retailer_index_should_have_links",
    "parse_konami_style",
    "parse_official_retailer_detail",
    "parse_onepiece_official_shop",
    "parse_premium_bandai_dragonball",
    "parse_takaratomy_mall",
]
