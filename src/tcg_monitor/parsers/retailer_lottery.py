from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from tcg_monitor.classifier import classify_product
from tcg_monitor.config import source_with_runtime_parser_profile
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig
from tcg_monitor.parsers.common import title, visible_text

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
    "gundam_card": (
        "ガンダムカードゲーム",
        "ガンダムカード",
        "GUNDAM CARD GAME",
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
    "gundam_card": (
        "エクストラブースターパック",
        "エクストラブースター",
        "ブースターパック",
    ),
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


def _index_url(source: SourceConfig | str) -> str | None:
    if isinstance(source, SourceConfig):
        source = source_with_runtime_parser_profile(source)
    if isinstance(source, SourceConfig) and source.parser_kind == "retailer_lottery":
        configured = source.parser_options.get("index_url")
        if isinstance(configured, str) and configured:
            return configured
    return None


def is_retailer_lottery_source(source: SourceConfig | str) -> bool:
    if isinstance(source, SourceConfig):
        source = source_with_runtime_parser_profile(source)
        # Some retailers expose both a normal product index and a stable
        # campaign page. The latter intentionally does not equal ``index_url``,
        # but it must still use this parser.
        return source.parser_kind == "retailer_lottery"
    return _index_url(source) is not None


def is_retailer_lottery_index(source: SourceConfig | str, url: str) -> bool:
    expected = _index_url(source)
    return expected is not None and url.rstrip("/") == expected.rstrip("/")


def retailer_lottery_index_error(
    html: str,
    source: SourceConfig | str,
) -> str | None:
    """Return a health reason for known retailer error/maintenance shells."""

    source_id = source.id if isinstance(source, SourceConfig) else source
    if source_id != "famima_online_lottery":
        return None
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    folded = text.casefold()
    error_markers = (
        "maintenance/error",
        "メンテナンス中",
        "ただいまご利用いただけません",
        "エラーが発生",
        "海外からのアクセスは受け付けておりません",
        "日本国内からご利用",
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
        parts.extend(str(image.get(attribute) or "") for attribute in ("alt", "title"))
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


def _allowed_detail_url(source: SourceConfig | str, candidate: str) -> bool:
    parts = urlsplit(candidate)
    host = parts.netloc.casefold()
    path = parts.path
    if isinstance(source, SourceConfig) and source.parser_kind == "retailer_lottery":
        options = source.parser_options
        expected_host = str(options.get("detail_host") or "").casefold()
        path_prefix = str(options.get("detail_path_prefix") or "")
        path_suffix = str(options.get("detail_path_suffix") or "")
        if expected_host:
            return (
                host == expected_host
                and (not path_prefix or path.startswith(path_prefix))
                and (not path_suffix or path.endswith(path_suffix))
            )
    source_id = source.id if isinstance(source, SourceConfig) else source
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
        return host == "support.hlj.co.jp" and path.startswith("/hc/ja/articles/")
    if source_id == "tokyo_otaku_mode_lottery":
        return host == "ja.otakumode.com" and path.startswith("/blogs/news/")
    return False


def discover_retailer_lottery_urls(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    limit: int = 20,
) -> list[str]:
    """Follow only supported TCG BOX candidates from official retailer indexes."""

    source = source_with_runtime_parser_profile(source)
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        candidate = urljoin(url, str(anchor.get("href") or ""))
        if not _allowed_detail_url(source, candidate):
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
        target_context_markers = source.parser_options.get("target_context_markers", [])
        required_context_markers = source.parser_options.get("required_context_markers", [])
        if target_context_markers:
            if not isinstance(target_context_markers, list) or not all(
                isinstance(marker, str) and marker for marker in target_context_markers
            ):
                raise ValueError(f"bad target_context_markers: {source.id}")
            if not any(store in context for store in target_context_markers):
                continue
            if not isinstance(required_context_markers, list) or not all(
                isinstance(marker, str) and marker for marker in required_context_markers
            ):
                raise ValueError(f"bad required_context_markers: {source.id}")
            if not all(marker in context for marker in required_context_markers):
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
        leading_range_end = period_without_heading_marks.startswith(
            ("～", "〜", "~")
        ) and not label.endswith(("開始", "開始日時"))
        deadline_only = (
            (
                "まで" in period
                and not any(marker in period for marker in ("から", "より", "～", "〜", "~"))
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
            _index_url(source) or source.discovery_urls[0],
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
    base_date = published_at.date() if isinstance(published_at, datetime) else published_at
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

    retailer = _retailer(source, text)
    if retailer is None:
        raise ValueError(f"retailer parser profile is missing: {source.id}")
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
            game_id and any(category in combined for category in _BOX_CATEGORIES[game_id])
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
    start_at = explicit_start or (_article_published_at(soup) if article_open else None)
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

    retailer = _retailer(source, text)
    if retailer is None:
        raise ValueError(f"retailer parser profile is missing: {source.id}")
    retailer_id, retailer_name = retailer
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
    categories = "|".join(sorted(map(re.escape, _BOX_CATEGORIES[game_id]), key=len, reverse=True))
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
    code = re.search(code_pattern, combined, re.IGNORECASE) if code_pattern else None
    category = re.search(categories, combined, re.IGNORECASE)
    if code and category:
        return f"{category.group(0)} [{code.group(0).upper()}]"
    return page_title[:160].strip()


def _retailer(source: SourceConfig, text: str) -> tuple[str, str] | None:
    source = source_with_runtime_parser_profile(source)
    retailer_id = source.parser_options.get("retailer_id")
    retailer_name = source.parser_options.get("retailer_name")
    if isinstance(retailer_id, str) and isinstance(retailer_name, str):
        return retailer_id, retailer_name
    configured = source.parser_options.get("retailers")
    if configured is not None:
        if not isinstance(configured, list):
            raise ValueError(f"bad retailer parser options: {source.id}")
        for raw in configured:
            if not isinstance(raw, dict):
                raise ValueError(f"bad retailer parser option: {source.id}")
            marker = raw.get("marker")
            retailer_id = raw.get("retailer_id")
            retailer_name = raw.get("retailer_name")
            if (
                all(
                    isinstance(value, str) and value
                    for value in (marker, retailer_id, retailer_name)
                )
                and str(marker) in text
            ):
                return str(retailer_id), str(retailer_name)
        return None
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


def _parse_rakuten_detail(
    html: str, url: str, source: SourceConfig, config: Config,
    diagnostics: dict[str, int] | None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Pair the product heading with its labelled period, never a footer campaign.

    The lottery landing page became an index. Its /rb/ pages contain the actual
    period, separate from release and winner-purchase dates and sitewide copy.
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    headings = [node.get_text(" ", strip=True) for node in soup.find_all("h1")]
    headings.append(title(html))
    product = next((name for name in headings if _game_id(name, source)), "")
    game_id = _game_id(product, source)
    if not game_id:
        return [], [], []
    classified = classify_product(config.games[game_id], product, product)
    if not classified.is_box:
        if diagnostics is not None:
            diagnostics["excluded_product"] = 1
        return [], [], []
    if diagnostics is not None:
        diagnostics["validated_product"] = 1
    # Scope to the explicit application field. Never consume purchase/result dates.
    match = re.search(r"抽選受付期間\s*[：:]\s*(.{1,160}?)(?=当選者販売期間|発送予定日|$)", text)
    if not match:
        return [], [], [_alert(source, url, product, "retailer_application_period_missing",
                              "楽天公式BOX商品ページで抽選受付期間を確認できません", game_id)]
    parts = re.split(r"\s*[〜～~]\s*", match.group(1), maxsplit=1)
    if len(parts) != 2:
        return [], [], [_alert(source, url, product, "retailer_application_period_missing",
                              "楽天公式BOX抽選の開始・終了を一意に解析できません", game_id)]
    start_at = parse_first_datetime(parts[0]).value
    base_date = start_at.date() if isinstance(start_at, datetime) else start_at
    end_at = parse_first_datetime(parts[1], base_date).value
    if start_at is None or end_at is None:
        return [], [], [_alert(source, url, product, "retailer_application_period_missing",
                              "楽天公式BOX抽選の開始・終了を一意に解析できません", game_id)]
    start_date = start_at.date() if isinstance(start_at, datetime) else start_at
    end_date = end_at.date() if isinstance(end_at, datetime) else end_at
    if end_date < start_date:
        return [], [], [_alert(source, url, product, "retailer_application_period_missing",
                              "楽天公式BOX抽選の終了日が開始日より前です", game_id)]
    if diagnostics is not None:
        diagnostics["validated_application_period"] = 1
    now = datetime.now(ZoneInfo(config.timezone))
    ended = end_at < now if isinstance(end_at, datetime) else end_at < now.date()
    if ended:
        if diagnostics is not None:
            diagnostics["application_ended"] = 1
        return [], [], []
    case = LotteryCase(
        game_id, "rakuten_books", "楽天ブックス", classified.product_name,
        classified.product_category, classified.canonical_product_key,
        start_at, url, url, source.source_tier, "rakuten_detail_application_period", "high",
        end_at=end_at,
    ).with_id()
    return [case], [], []


def parse_retailer_lottery_detail(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    diagnostics: dict[str, int] | None = None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    source = source_with_runtime_parser_profile(source)
    if source.id == "rakuten_books":
        return _parse_rakuten_detail(html, url, source, config, diagnostics)
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
