from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig
from tcg_monitor.parsers.common import title, visible_text

_INDEX_URLS = {
    "namco_onepiece_official_shop_miyagi": (
        "https://parks2.bandainamco-am.co.jp/category/EL/"
    ),
    "famima_online_lottery": (
        "https://famima-online.family.co.jp/search?receiveType=1"
    ),
    "dmm_hobby_lottery": (
        "https://www.dmm.com/mono/hobby/-/list/=/article=directory/id=5027/"
    ),
    "hobby_search_lottery": "https://www.1999.co.jp/list/3352/7/1",
    "edion_online_lottery": "https://www.edion.com/",
    "itoyokado_online_lottery": (
        "https://iyec.itoyokado.co.jp/shop/e/eE4reslot/"
    ),
    "hobbylink_japan_lottery": (
        "https://support.hlj.co.jp/hc/ja/sections/"
        "203939188-%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B"
    ),
    "tokyo_otaku_mode_lottery": "https://ja.otakumode.com/blogs/news",
}

_RETAILERS = {
    "famima_online_lottery": ("famima_online", "ファミマオンライン"),
    "dmm_hobby_lottery": ("dmm_tsuhan", "DMM通販"),
    "hobby_search_lottery": ("hobby_search", "ホビーサーチ"),
    "edion_online_lottery": ("edion_online", "エディオンネットショップ"),
    "itoyokado_online_lottery": (
        "itoyokado_online",
        "イトーヨーカドーネット通販",
    ),
    "hobbylink_japan_lottery": (
        "hobbylink_japan",
        "ホビーリンク・ジャパン",
    ),
    "tokyo_otaku_mode_lottery": (
        "tokyo_otaku_mode",
        "Tokyo Otaku Mode",
    ),
}

_GAME_WORDS = {
    "pokemon_card": ("ポケモンカードゲーム", "ポケモンカード", "ポケカ"),
    "one_piece_card": (
        "ONE PIECEカードゲーム",
        "ONE PIECE カードゲーム",
        "ワンピースカード",
        "ワンピカード",
    ),
    "dragon_ball_fusion_world": (
        "ドラゴンボールスーパーカードゲーム",
        "フュージョンワールド",
        "DBFW",
    ),
    "yu_gi_oh": (
        "遊戯王OCG",
        "遊戯王カード",
        "遊☆戯☆王",
        "遊戯王",
    ),
    "lorcana": (
        "ディズニー・ロルカナ",
        "ディズニーロルカナ",
        "LORCANA",
        "ロルカナ",
    ),
}

_BOX_CATEGORIES = {
    "pokemon_card": (
        "強化拡張パック",
        "ハイクラスパック",
        "再拡張パック",
        "拡張パック",
    ),
    "one_piece_card": (
        "エクストラブースター",
        "プレミアムブースター",
        "ブースターパック",
    ),
    "dragon_ball_fusion_world": (
        "MANGA BOOSTER",
        "STORY BOOSTER",
        "ブースターパック",
    ),
    "yu_gi_oh": (
        "ORIGINAL ARTWORK COLLECTION",
        "RARITY COLLECTION",
        "TACTICAL-TRY PACK",
        "REVOLUTION BOOSTER",
        "LIMITED PACK",
        "PREMIUM PACK",
        "スペシャルパック",
        "コンセプトパック",
        "基本パック",
        "ブースターパック",
    ),
    "lorcana": ("ブースターパック",),
}

_DEFAULT_START_LABELS = (
    "抽選申し込み期間",
    "抽選申込期間",
    "抽選応募受付期間",
    "抽選受付期間",
    "応募受付期間",
    "エントリー受付期間",
    "エントリー期間",
    "申込開始",
    "応募期間",
)


def is_retailer_lottery_source(source_id: str) -> bool:
    return source_id in _INDEX_URLS


def is_retailer_lottery_index(source_id: str, url: str) -> bool:
    expected = _INDEX_URLS.get(source_id)
    return expected is not None and url.rstrip("/") == expected.rstrip("/")


def retailer_lottery_index_error(
    html: str,
    source_id: str,
) -> str | None:
    """Return a health reason for known retailer error/maintenance shells."""

    if source_id != "famima_online_lottery":
        return None
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    folded = text.casefold()
    error_markers = (
        "maintenance/error",
        "メンテナンス中",
        "ただいまご利用いただけません",
        "エラーが発生",
        "access denied",
    )
    if any(marker.casefold() in folded for marker in error_markers):
        return "ファミマオンラインがメンテナンス・地域制限のエラーページを返しました"
    return None


def _game_id(text: str, source: SourceConfig) -> str | None:
    compact = re.sub(r"\s+", "", text).casefold()
    for game_id, words in _GAME_WORDS.items():
        if source.supports(game_id) and any(
            re.sub(r"\s+", "", word).casefold() in compact for word in words
        ):
            return game_id
    return None


def _anchor_context(anchor: Tag) -> str:
    parts = [anchor.get_text(" ", strip=True)]
    for image in anchor.find_all("img"):
        parts.extend(
            str(image.get(attribute) or "")
            for attribute in ("alt", "title")
        )
    parent = anchor.parent
    for _ in range(3):
        if not isinstance(parent, Tag):
            break
        parent_text = parent.get_text(" ", strip=True)
        if parent_text and len(parent_text) <= 1_200:
            parts.append(parent_text)
            if parent.name in {"article", "li"} or "抽選" in parent_text:
                break
        parent = parent.parent
    return " ".join(parts)


def _allowed_detail_url(source_id: str, candidate: str) -> bool:
    parts = urlsplit(candidate)
    host = parts.netloc.casefold()
    path = parts.path
    if source_id == "namco_onepiece_official_shop_miyagi":
        return (
            host == "parks2.bandainamco-am.co.jp"
            and path.startswith("/category/EL/")
            and path.endswith(".html")
        )
    if source_id == "famima_online_lottery":
        return (
            host == "famima-online.family.co.jp"
            and path not in {"/", "/search"}
            and "/maintenance/" not in path
        )
    if source_id == "dmm_hobby_lottery":
        return host in {"www.dmm.com", "dmm.com"} and "/detail/" in path
    if source_id == "hobby_search_lottery":
        return host in {"www.1999.co.jp", "1999.co.jp"} and bool(
            re.fullmatch(r"/\d{6,}", path.rstrip("/"))
        )
    if source_id == "edion_online_lottery":
        return (
            host in {"www.edion.com", "edion.com", "edion-cp.com"}
            and candidate.rstrip("/") != "https://www.edion.com"
        )
    if source_id == "itoyokado_online_lottery":
        return host == "iyec.itoyokado.co.jp" and "/shop/g/g" in path
    if source_id == "hobbylink_japan_lottery":
        return (
            host == "support.hlj.co.jp"
            and path.startswith("/hc/ja/articles/")
        )
    if source_id == "tokyo_otaku_mode_lottery":
        return (
            host == "ja.otakumode.com"
            and path.startswith("/blogs/news/")
        )
    return False


def discover_retailer_lottery_urls(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    limit: int = 20,
) -> list[str]:
    """Follow only supported TCG BOX candidates from official retailer indexes."""

    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        candidate = urljoin(url, str(anchor.get("href") or ""))
        if not _allowed_detail_url(source.id, candidate):
            continue
        context = (
            anchor.get_text(" ", strip=True)
            if source.id == "hobbylink_japan_lottery"
            else _anchor_context(anchor)
        )
        if source.id == "tokyo_otaku_mode_lottery":
            # The index title is generic and the newest excerpt can exceed the
            # context-size guard. Follow official lottery articles first, then
            # classify the full article by game and BOX product.
            if "抽選" not in anchor.get_text(" ", strip=True):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            found.append(candidate)
            if len(found) >= limit:
                break
            continue
        game_id = _game_id(context, source)
        if not game_id:
            continue
        game = config.games[game_id]
        has_box = any(word in context for word in game.box_product_keywords) or bool(
            re.search(r"(?i)\b1?BOX\b", context)
        )
        # HLJ's official index names only the game. The linked article carries
        # the individual products, so follow that article and classify each
        # product there.
        if not has_box and source.id != "hobbylink_japan_lottery":
            continue
        if source.id == "namco_onepiece_official_shop_miyagi":
            if not any(store in context for store in ("仙台店", "宮城名取店")):
                continue
            if "抽選" not in context or "購入権" not in context:
                continue
        elif "抽選" not in context:
            # The Ito-Yokado and Famima index headings can carry the lottery
            # label outside each product card. Follow the BOX detail, then
            # require an explicit lottery/application period on that page.
            index_text = soup.get_text(" ", strip=True)
            if "抽選" not in index_text:
                continue
        if candidate in seen:
            continue
        seen.add(candidate)
        found.append(candidate)
        if len(found) >= limit:
            break
    return found


def _application_start(
    text: str,
    source: SourceConfig,
    base_date: date | None = None,
) -> datetime | date | None:
    compact = re.sub(r"\s+", "", text)
    labels = tuple(source.start_labels) or _DEFAULT_START_LABELS
    for label in labels:
        match = re.search(rf"{re.escape(label)}[：:]?(.{{0,180}})", compact)
        if not match:
            continue
        period = match.group(1)
        # Some official pages publish only a deadline under a "受付期間"
        # heading. Treating that lone date as the opening date creates a late,
        # incorrect notification.
        period_without_heading_marks = period.lstrip()
        heading_marks = (":", "：", "〗", "】", "〕", "］", "》", "）", "」", "』")
        while period_without_heading_marks.startswith(heading_marks):
            period_without_heading_marks = period_without_heading_marks[1:].lstrip()
        leading_range_end = (
            period_without_heading_marks.startswith(("～", "〜", "~"))
            and not label.endswith(("開始", "開始日時"))
        )
        deadline_only = (
            (
                "まで" in period
                and not any(
                    marker in period for marker in ("から", "より", "～", "〜", "~")
                )
            )
            or leading_range_end
        ) and not label.endswith(("開始", "開始日時"))
        if deadline_only:
            continue
        parsed = parse_first_datetime(period, base_date)
        if parsed.value:
            return parsed.value
    return None


def _hobbylink_application_url(soup: BeautifulSoup, article_url: str) -> str:
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        candidate = urljoin(article_url, str(anchor.get("href") or ""))
        host = urlsplit(candidate).netloc.casefold()
        label = anchor.get_text(" ", strip=True)
        if "応募フォーム" in label or host in {"forms.gle", "docs.google.com"}:
            return candidate
    return article_url


def _hobbylink_products(
    soup: BeautifulSoup,
    source: SourceConfig,
    config: Config,
) -> list[tuple[str, str, str, str]]:
    """Extract each BOX product link from a mixed HLJ lottery article."""

    products: dict[str, tuple[str, str, str, str]] = {}
    article_text = soup.get_text(" ", strip=True)
    page_game_id = _game_id(article_text, source)
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        product_name = anchor.get_text(" ", strip=True)
        game_id = _game_id(product_name, source) or page_game_id
        if not game_id:
            continue
        product_url = urljoin(
            _INDEX_URLS["hobbylink_japan_lottery"],
            str(anchor.get("href") or ""),
        )
        if urlsplit(product_url).netloc.casefold() not in {
            "www.hlj.co.jp",
            "hlj.co.jp",
        }:
            continue
        classified = classify_product(
            config.games[game_id],
            product_name,
            product_name,
            product_url,
        )
        if not classified.is_box:
            continue
        products[classified.canonical_product_key] = (
            game_id,
            classified.product_name,
            classified.product_category,
            classified.canonical_product_key,
        )
    return list(products.values())


def _parse_hobbylink_detail(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    soup = BeautifulSoup(html, "lxml")
    page_title = title(html) or source.name
    text = visible_text(html)
    if "抽選販売" not in f"{page_title} {text}":
        return [], [], []
    products = _hobbylink_products(soup, source, config)
    if not products:
        return [], [], []

    published_at = parse_first_datetime(text).value
    base_date = (
        published_at.date()
        if isinstance(published_at, datetime)
        else published_at
    )
    start_at = _application_start(text, source, base_date) or published_at
    if not start_at:
        return (
            [],
            [],
            [
                _alert(
                    source,
                    url,
                    page_title,
                    "retailer_application_period_missing",
                    "公式のBOX抽選ページだが受付開始日を解析できません",
                )
            ],
        )

    retailer = _RETAILERS["hobbylink_japan_lottery"]
    application_url = _hobbylink_application_url(soup, url)
    cases = [
        LotteryCase(
            game_id,
            retailer[0],
            retailer[1],
            product_name,
            product_category,
            canonical_product_key,
            start_at,
            application_url,
            url,
            source.source_tier,
            (
                "retailer_detail_application_period"
                if _application_start(text, source, base_date)
                else "retailer_article_published_open"
            ),
            "high" if _application_start(text, source, base_date) else "medium",
        ).with_id()
        for game_id, product_name, product_category, canonical_product_key in products
    ]
    return cases, [], []


def _tokyo_otaku_mode_products(
    soup: BeautifulSoup,
    source: SourceConfig,
    config: Config,
) -> list[tuple[str, str, str, str]]:
    """Extract each supported BOX named in a Tokyo Otaku Mode article."""

    products: dict[str, tuple[str, str, str, str]] = {}
    content_blocks = soup.find_all(("h1", "h2", "h3", "p", "li"))
    for block in content_blocks:
        if not isinstance(block, Tag):
            continue
        line = re.sub(r"\s+", " ", block.get_text(" ", strip=True)).strip(" ・-")
        game_id = _game_id(line, source)
        if not game_id:
            continue
        categories = "|".join(
            sorted(
                map(re.escape, _BOX_CATEGORIES[game_id]),
                key=len,
                reverse=True,
            )
        )
        category = re.search(categories, line, re.IGNORECASE)
        if not category:
            continue
        product_name = line[category.start() :]
        product_name = re.split(
            r"(?:〖?商品詳細〗?|価格[：:]|税込\s*\d)",
            product_name,
            maxsplit=1,
        )[0].strip()
        if len(product_name) > 160:
            product_name = product_name[:160].rstrip()
        classified = classify_product(
            config.games[game_id],
            product_name,
            line,
        )
        if not classified.is_box:
            continue
        products[classified.canonical_product_key] = (
            game_id,
            classified.product_name,
            classified.product_category,
            classified.canonical_product_key,
        )
    return list(products.values())


def _article_published_at(
    soup: BeautifulSoup,
) -> datetime | date | None:
    """Read the article date without falling through to an application deadline."""

    for time_tag in soup.find_all("time"):
        if not isinstance(time_tag, Tag):
            continue
        parsed = parse_first_datetime(time_tag.get_text(" ", strip=True)).value
        if parsed:
            return parsed
        raw_datetime = str(time_tag.get("datetime") or "")
        if match := re.match(r"(?P<year>20\d{2})-(?P<month>\d{2})-(?P<day>\d{2})", raw_datetime):
            return date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
    return None


def _parse_tokyo_otaku_mode_detail(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    soup = BeautifulSoup(html, "lxml")
    page_title = title(html) or source.name
    text = visible_text(html)
    combined = f"{page_title} {text}"
    if "抽選" not in combined:
        return [], [], []

    products = _tokyo_otaku_mode_products(soup, source, config)
    if not products:
        game_id = _game_id(combined, source)
        has_box_category = bool(
            game_id
            and any(
                category in combined
                for category in _BOX_CATEGORIES[game_id]
            )
        )
        if game_id and has_box_category:
            return (
                [],
                [],
                [
                    _alert(
                        source,
                        url,
                        page_title,
                        "retailer_box_product_missing",
                        "公式のBOX抽選記事だが商品名を解析できません",
                        game_id,
                    )
                ],
            )
        return [], [], []

    explicit_start = _application_start(text, source)
    article_open = any(
        wording in combined
        for wording in (
            "抽選応募を開始",
            "応募受付を開始",
            "抽選受付を開始",
        )
    )
    start_at = explicit_start or (
        _article_published_at(soup) if article_open else None
    )
    if not start_at:
        return (
            [],
            [],
            [
                _alert(
                    source,
                    url,
                    page_title,
                    "retailer_application_period_missing",
                    "公式のBOX抽選記事だが受付開始日時を解析できません",
                    products[0][0],
                )
            ],
        )

    retailer_id, retailer_name = _RETAILERS["tokyo_otaku_mode_lottery"]
    application_url = _hobbylink_application_url(soup, url)
    extraction_method = (
        "retailer_detail_application_period"
        if explicit_start
        else "retailer_article_published_open"
    )
    confidence = "high" if explicit_start else "medium"
    cases = [
        LotteryCase(
            game_id,
            retailer_id,
            retailer_name,
            product_name,
            product_category,
            canonical_product_key,
            start_at,
            application_url,
            url,
            source.source_tier,
            extraction_method,
            confidence,
        ).with_id()
        for game_id, product_name, product_category, canonical_product_key in products
    ]
    return cases, [], []


def _product_name(
    page_title: str,
    text: str,
    game_id: str,
) -> str:
    combined = f"{page_title}\n{text}"
    categories = "|".join(
        sorted(map(re.escape, _BOX_CATEGORIES[game_id]), key=len, reverse=True)
    )
    quoted = re.search(
        rf"(?P<category>{categories})\s*[「『【](?P<name>[^」』】]{{2,100}})[」』】]",
        combined,
        re.IGNORECASE,
    )
    if quoted:
        return f"{quoted.group('category')}「{quoted.group('name').strip()}」"

    code_patterns = {
        "one_piece_card": r"\b(?:OP|EB|PRB)-\d{2}\b",
        "dragon_ball_fusion_world": r"\b(?:FB|SB|ST)\d{2}\b",
    }
    code_pattern = code_patterns.get(game_id)
    code = (
        re.search(code_pattern, combined, re.IGNORECASE)
        if code_pattern
        else None
    )
    category = re.search(categories, combined, re.IGNORECASE)
    if code and category:
        return f"{category.group(0)} [{code.group(0).upper()}]"
    return page_title[:160].strip()


def _retailer(source: SourceConfig, text: str) -> tuple[str, str] | None:
    if source.id != "namco_onepiece_official_shop_miyagi":
        return _RETAILERS.get(source.id)
    if "宮城名取店" in text:
        return (
            "onepiece_official_shop_miyagi_natori",
            "ONE PIECEカードゲーム公式ショップ 宮城名取店",
        )
    if "仙台店" in text:
        return (
            "onepiece_official_shop_sendai",
            "ONE PIECEカードゲーム公式ショップ 仙台店",
        )
    return None


def _alert(
    source: SourceConfig,
    url: str,
    page_title: str,
    reason: str,
    summary: str,
    game_id: str | None = None,
) -> Alert:
    return Alert(
        game_id,
        source.id,
        url,
        page_title,
        [word for word in ("抽選", "応募", "受付") if word in summary],
        reason,
        summary,
        None,
        url,
    ).with_fingerprint()


def parse_retailer_lottery_detail(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    if source.id == "hobbylink_japan_lottery":
        return _parse_hobbylink_detail(html, url, source, config)
    if source.id == "tokyo_otaku_mode_lottery":
        return _parse_tokyo_otaku_mode_detail(html, url, source, config)

    page_title = title(html) or source.name
    text = visible_text(html)
    combined = f"{page_title} {text}"
    game_id = _game_id(combined, source)
    if not game_id or "抽選" not in combined:
        return [], [], []

    product_name = _product_name(page_title, text, game_id)
    classified = classify_product(
        config.games[game_id],
        product_name,
        product_name,
        url,
    )
    if not classified.is_box:
        return [], [], []

    retailer = _retailer(source, combined)
    if not retailer:
        return [], [], []
    start_at = _application_start(text, source)
    extraction_method = "retailer_detail_application_period"
    confidence = "high"
    if not start_at and source.id == "hobby_search_lottery":
        active_markers = (
            "抽選に応募する",
            "抽選受付中",
            "抽選販売",
        )
        if not any(marker in combined for marker in active_markers):
            return [], [], []
        # ホビーサーチは応募中だけ商品ページに抽選導線を表示するが、
        # 受付開始日時そのものは公開しない場合がある。初回検知日を
        # 仮の開始日として通知し、締切や発売日を開始日に流用しない。
        start_at = datetime.now(ZoneInfo(config.timezone)).date()
        extraction_method = "hobby_search_active_lottery_detected"
        confidence = "medium"
    if not start_at:
        return (
            [],
            [],
            [
                _alert(
                    source,
                    url,
                    page_title,
                    "retailer_application_period_missing",
                    "公式のBOX抽選ページだが応募開始日時を解析できません",
                    game_id,
                )
            ],
        )

    retailer_id, retailer_name = retailer
    case = LotteryCase(
        game_id,
        retailer_id,
        retailer_name,
        classified.product_name,
        classified.product_category,
        classified.canonical_product_key,
        start_at,
        url,
        url,
        source.source_tier,
        extraction_method,
        confidence,
    ).with_id()
    return [case], [], []


__all__ = [
    "discover_retailer_lottery_urls",
    "is_retailer_lottery_index",
    "is_retailer_lottery_source",
    "parse_retailer_lottery_detail",
    "retailer_lottery_index_error",
]
