from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from tcg_monitor.classifier import canonical_product_key, classify_product
from tcg_monitor.config import source_with_runtime_parser_profile
from tcg_monitor.identity import is_provisional_product_name, release_title_token
from tcg_monitor.japanese_datetime import (
    parse_first_datetime,
    parse_period_start,
    period_is_deadline_only,
)
from tcg_monitor.models import (
    Alert,
    Config,
    LotteryCase,
    LotteryStartPolicy,
    OpportunityKind,
    Release,
    SourceConfig,
    SourceTier,
)
from tcg_monitor.parsers.common import title, visible_text


def _livepocket_profile(source: SourceConfig | str) -> tuple[str, str] | None:
    """Return retailer identity without requiring it in public Python code."""

    if isinstance(source, SourceConfig):
        source = source_with_runtime_parser_profile(source)
        options = source.parser_options
        if source.parser_kind == "livepocket":
            retailer_id = options.get("retailer_id")
            retailer_name = options.get("retailer_name")
            if isinstance(retailer_id, str) and isinstance(retailer_name, str):
                return retailer_id, retailer_name
    return None


def _yahoo_profile(source: SourceConfig | str) -> tuple[str, str, str] | None:
    """Return social account and retailer identity from runtime configuration data."""

    if isinstance(source, SourceConfig):
        source = source_with_runtime_parser_profile(source)
        options = source.parser_options
        if source.parser_kind == "yahoo_realtime":
            account = options.get("account")
            retailer_id = options.get("retailer_id")
            retailer_name = options.get("retailer_name")
            if all(
                isinstance(value, str) and value for value in (account, retailer_id, retailer_name)
            ):
                return str(account), str(retailer_id), str(retailer_name)
    return None


def _string_list_option(source: SourceConfig, name: str) -> tuple[str, ...]:
    source = source_with_runtime_parser_profile(source)
    raw = source.parser_options.get(name)
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(value, str) and value for value in raw):
        raise ValueError(f"bad parser option {name}: {source.id}")
    return tuple(raw)


def _status_datetime_option(
    source: SourceConfig,
    name: str,
    status_id: str,
) -> datetime | date | None:
    """Read a manually confirmed per-post date without hard-coding a retailer."""

    source = source_with_runtime_parser_profile(source)
    raw = source.parser_options.get(name)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"bad parser option {name}: {source.id}")
    value = raw.get(status_id)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"bad parser option {name}.{status_id}: {source.id}")
    try:
        return datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"bad parser option {name}.{status_id}: {source.id}") from exc


def _status_product_option(
    source: SourceConfig,
    status_id: str,
) -> tuple[str, str] | None:
    """Read a manually verified product when an official post is image-led."""

    source = source_with_runtime_parser_profile(source)
    raw = source.parser_options.get("confirmed_products")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"bad parser option confirmed_products: {source.id}")
    item = raw.get(status_id)
    if item is None:
        return None
    if not isinstance(item, dict):
        raise ValueError(f"bad parser option confirmed_products.{status_id}: {source.id}")
    product_name = item.get("product_name")
    product_category = item.get("product_category")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (product_name, product_category)
    ):
        raise ValueError(f"bad parser option confirmed_products.{status_id}: {source.id}")
    return str(product_name), str(product_category)


_SECONDARY_ROUNDUP_MARKERS = (
    "抽選受付中の店舗一覧",
    "受付中の店舗一覧",
    "抽選店舗一覧",
    "予約・抽選受付情報",
    "抽選受付情報まとめ",
    "抽選リスト",
)

# The user only wants lotteries that can be entered remotely and need no more
# than one physical visit to collect a win.  Social accounts also publish
# repost giveaways and store-only QR/advance-reservation lotteries, so reject
# those before product classification or OCR can turn them into alerts.
_DISALLOWED_REMOTE_APPLICATION_MARKERS = (
    "リポストキャンペーン",
    "フォロー&リポスト",
    "フォロー＆リポスト",
    "フォロー+リポスト",
    "フォロー＋リポスト",
    "引用リポスト",
    "リツイートキャンペーン",
    "フォロー&rt",
    "フォロー＆rt",
    "rt&フォロー",
    "rt＆フォロー",
    "フォローとrt",
    "rtで応募",
    "rtして応募",
    "rtキャンペーン",
)
_DISALLOWED_REMOTE_APPLICATION_PATTERNS = (
    re.compile(r"店(?:頭|内)(?:に|で|の|へ|にて)?.{0,40}掲示.{0,30}QRコード", re.IGNORECASE),
    re.compile(r"店(?:頭|内)(?:に|で|の|へ|にて)?.{0,30}QRコード(?:から|より)", re.IGNORECASE),
    re.compile(r"当選(?:者|された方).{0,80}店頭.{0,30}予約(?:を|が|手続)", re.IGNORECASE),
    re.compile(r"予約手付金", re.IGNORECASE),
)


def _requires_disallowed_application(post_text: str) -> bool:
    compact = re.sub(r"\s+", "", post_text).casefold()
    return any(marker in compact for marker in _DISALLOWED_REMOTE_APPLICATION_MARKERS) or any(
        pattern.search(compact) for pattern in _DISALLOWED_REMOTE_APPLICATION_PATTERNS
    )


_APPLICATION_LABEL = re.compile(
    r"(?:販売受付期間|予約受付期間|注文受付期間|販売期間|"
    r"抽選応募受付期間|抽選受付期間|抽選申込期間|抽選申し込み期間|抽選期間|"
    r"応募受付期間|エントリー受付期間|エントリー期間|申込開始|"
    r"申込受付期間|申し込み受付期間|受付期間|応募期間)"
    r"[：:]?(.{0,180})"
)
_X_STATUS_URL = re.compile(r"^https://(?:www\.)?(?:x|twitter)\.com/([^/?]+)/status/(\d+)", re.I)
_MIRROR_STATUS_URL = re.compile(
    r"^(?:https://(?:www\.|ww\.)?twstalker\.com)?/([^/?]+)/status/(\d+)", re.I
)
_AMAZON_PRODUCT_URL = re.compile(
    r"(?:https?://)?(?:www\.)?amazon\.co\.jp/(?:dp|gp/product)/([A-Z0-9]{10})",
    re.I,
)
_FURUICHI_ARTICLE_URL = re.compile(
    r"(?:https?://)?(?:www\.)?furu1\.net/news/news_information/([A-Za-z0-9_-]+)",
    re.I,
)
_ACTION_WORDS = (
    "抽選販売",
    "抽選受付",
    "抽選応募",
    "抽選予約を受付",
    "抽選予約開始",
    "購入権抽選",
    "エントリー受付",
    "エントリーを受付",
    "エントリーを開始",
    "エントリー開始",
    "応募受付",
    "受付を開始",
    "受付開始",
    "WEB受付",
    "抽選申込",
    "抽選申込み",
    "抽選申し込み",
    "エントリー受付",
    "エントリーを受付",
    "エントリーを開始",
    "エントリー開始",
)
_LOTTERY_APPLICATION_START = re.compile(
    r"抽選(?:申込(?:み)?|申し込み|応募|予約)(?:受付)?(?:を|が)?(?:開始|スタート)"
)
_CLOSED_OR_RESULT_WORDS = (
    "当選者発表",
    "当選者",
    "当選発表",
    "当選のご案内",
    "抽選当選",
    "当落発表",
    "抽選結果",
    "当選連絡",
    "当選通知",
    "当選メール",
    "当落連絡",
    "当落通知",
    "締切間近",
    "受付終了",
    "受け取り期間",
    "引取期限",
)
_OPEN_APPLICATION_WORDS = (
    "応募条件",
    "応募締切",
    "応募期限",
    "応募期間",
    "受付期間",
    "販売受付期間",
    "受付を開始",
    "受付開始",
    "抽選予約開始",
)
_POSTPONEMENT_WORDS = (
    "抽選販売延期",
    "抽選を延期",
    "抽選延期",
    "受付を延期",
    "受付延期",
    "実施を延期",
    "延期を発表",
    "抽選販売中止",
    "抽選を中止",
    "受付中止",
    "実施を中止",
    "販売見合わせ",
    "受付見合わせ",
    "日程を変更",
    "日程変更",
)
_NON_PRODUCT_HASHTAGS = {
    "ポケカ",
    "ポケカ抽選",
    "ポケモンカード",
    "ポケモンカードゲーム",
    "ワンピカード",
    "ワンピースカード",
    "ワンピースカードゲーム",
    "ONEPIECEカードゲーム",
    "ワンピカード抽選",
    "ドラゴンボールスーパーカードゲーム",
    "フュージョンワールド",
    "DBFW",
    "ドラゴ抽選",
    "遊戯王",
    "遊戯王OCG",
    "遊戯王カード",
    "ロルカナ",
    "ディズニーロルカナ",
    "ディズニー・ロルカナ",
    "抽選",
    "抽選販売",
    "商品情報",
    "販売情報",
    "予約",
    "トレカ",
    "トレカノ",
    "WonderGOO",
    "ワングー",
}
_NON_PRODUCT_LABELS = {re.sub(r"\s+", "", value).casefold() for value in _NON_PRODUCT_HASHTAGS}
_X_EPOCH_MS = 1_288_834_974_657
OcrReader = Callable[[list[str]], str]


def _game_id(text: str) -> str | None:
    folded = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()
    one_piece_words = (
        "ONEPIECEカード",
        "ワンピースカード",
        "ワンピカード",
    )
    if any(word.casefold() in folded for word in one_piece_words):
        return "one_piece_card"
    if any(word.casefold() in folded for word in ("ポケモンカード", "ポケカ")):
        return "pokemon_card"
    dragon_ball_words = (
        "フュージョンワールド",
        "fusionworld",
        "dbfw",
        "ドラゴンボールfw",
    )
    if any(word in folded for word in dragon_ball_words):
        return "dragon_ball_fusion_world"
    yu_gi_oh_words = (
        "遊戯王ocg",
        "遊戯王カード",
        "遊☆戯☆王",
        "遊戯王",
    )
    if any(word in folded for word in yu_gi_oh_words):
        return "yu_gi_oh"
    lorcana_words = (
        "ディズニー・ロルカナ",
        "ディズニーロルカナ",
        "lorcana",
        "ロルカナ",
    )
    if any(word in folded for word in lorcana_words):
        return "lorcana"
    gundam_words = (
        "ガンダムカードゲーム",
        "ガンダムカード",
        "gundamcardgame",
    )
    if any(word in folded for word in gundam_words):
        return "gundam_card"
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


def discover_livepocket_event_urls(
    html: str, url: str, source: SourceConfig, config: Config, limit: int = 12
) -> list[str]:
    """Find BOX lottery detail pages; never interpret list-page event dates."""
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href"))
        candidate = urljoin(url, href)
        if not re.fullmatch(r"https://(?:t\.)?livepocket\.jp/e/[A-Za-z0-9_-]+", candidate):
            continue
        heading = anchor.find(["h1", "h2", "h3", "h4"])
        anchor_text = (heading or anchor).get_text(" ", strip=True)
        if "抽選" not in anchor_text:
            continue
        game_id = _game_id(anchor_text)
        if not game_id or not source.supports(game_id):
            continue
        # フルコンプのように検索結果の題名が「発売新品商品」のみで、
        # BOX名を個別ページにしか書かない販売者もある。購入権の抽選は
        # 詳細ページまで追い、そこでBOXだけを厳密に選別する。
        has_box_hint = bool(_box_products(anchor_text, game_id, config))
        has_purchase_right_hint = "購入権" in anchor_text or "抽選販売" in anchor_text
        has_only_excluded_hint = (
            any(word in anchor_text for word in config.games[game_id].product_exclude_keywords)
            and not has_box_hint
        )
        if has_only_excluded_hint:
            continue
        if not (has_box_hint or has_purchase_right_hint) or candidate in seen:
            continue
        seen.add(candidate)
        found.append(candidate)
        if len(found) >= limit:
            break
    return found


def is_livepocket_search_page(url: str) -> bool:
    return "/event/search" in url


def is_livepocket_source(source: SourceConfig | str) -> bool:
    return _livepocket_profile(source) is not None


def is_hobby_station_news_page(source_id: str, url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").casefold().removeprefix("www.")
    return (
        source_id == "livepocket_hobby_station"
        and host == "hbst.net"
        and parts.path.rstrip("/") == "/category/news"
    )


_BOX_CATEGORIES = {
    "pokemon_card": ("強化拡張パック", "ハイクラスパック", "再拡張パック", "拡張パック"),
    "one_piece_card": ("エクストラブースター", "プレミアムブースター", "ブースターパック"),
    "dragon_ball_fusion_world": ("MANGA BOOSTER", "STORY BOOSTER", "ブースターパック"),
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


def _box_products(text: str, game_id: str, config: Config) -> list[tuple[str, str, str]]:
    """Extract only BOX products from a possibly mixed LivePocket sales page."""
    game = config.games[game_id]
    categories = "|".join(map(re.escape, _BOX_CATEGORIES[game_id]))
    found: dict[str, tuple[str, str, str]] = {}

    quoted_pattern = re.compile(
        rf"(?P<category>{categories})\s*[「『【\"“](?P<title>[^」』】\"”]{{2,100}})[」』】\"”]",
        re.I,
    )
    for match in quoted_pattern.finditer(text):
        category = match.group("category")
        title_text = match.group("title").strip()
        product_name = f"{category}「{title_text}」"
        trailing = text[match.end() : match.end() + 32]
        product_code = next(
            (
                code_match.group("code").upper()
                for pattern in game.product_code_patterns
                if (code_match := re.search(pattern, trailing, re.I))
            ),
            "",
        )
        if product_code:
            product_name += f" [{product_code}]"
        key = canonical_product_key(game, product_name)
        found[key] = (product_name, category, key)

    code_families = {
        "one_piece_card": r"(?:OP|EB|PRB)-\d{2}",
        "dragon_ball_fusion_world": r"(?:FB|SB|ST)\d{2}",
        "gundam_card": r"(?:GD|EB)\d{2}",
    }
    if code_family := code_families.get(game_id):
        code_pattern = re.compile(
            rf"(?P<category>{categories})\s*(?P<title>[^\n。]{{0,100}}?)"
            rf"[【\[](?P<code>{code_family})[】\]]",
            re.I,
        )
        for match in code_pattern.finditer(text):
            category = match.group("category")
            title_text = match.group("title").strip(" 　・:：")
            code = match.group("code").upper()
            product_name = f"{category}「{title_text}」[{code}]"
            found.setdefault(code, (product_name, category, code))

    # 単一商品のページで引用符がない場合だけ、既存の厳格な分類を使う。
    if not found:
        fallback_name = text.splitlines()[0][:120].strip() or "BOX抽選商品"
        classified = classify_product(game, fallback_name, text)
        if classified.is_box:
            found[classified.canonical_product_key] = (
                classified.product_name,
                classified.product_category,
                classified.canonical_product_key,
            )
    return list(found.values())


def _period_label_is_start(compact: str, match: re.Match[str]) -> bool:
    label = compact[match.start() : match.start(1)]
    return label.endswith(("開始", "開始日時"))


def _application_start(text: str, base_date: date | None = None) -> datetime | date | None:
    compact = re.sub(r"\s+", "", text)
    for match in _APPLICATION_LABEL.finditer(compact):
        parsed = parse_period_start(
            match.group(1),
            base_date,
            label_is_start=_period_label_is_start(compact, match),
        )
        if parsed.value:
            return parsed.value

    # Official social posts sometimes put the opening date before the action,
    # for example ``8/22より午前10時より ... 抽選申し込みを開始``.  The
    # label-first parser above cannot see that order.  Use the last date before
    # the action so an earlier product release date cannot win by accident.
    normalized = unicodedata.normalize("NFKC", text)
    compact_normalized = re.sub(r"\s+", "", normalized)
    for action in _LOTTERY_APPLICATION_START.finditer(compact_normalized):
        prefix = compact_normalized[max(0, action.start() - 220) : action.start()]
        date_matches = list(
            re.finditer(
                r"(?:(?:20\d{2})[年./])?\d{1,2}[月/.]\d{1,2}日?",
                prefix,
            )
        )
        if not date_matches:
            continue
        # Walk backwards past product release dates and select the closest date
        # whose *own* suffix says ``より/から``.  Some retailers write the
        # otherwise unusual ``8/1日より ... 8月22日発売 ... 抽選申込を開始``;
        # considering only the final date loses the real application start.
        start_match = next(
            (
                candidate
                for candidate in reversed(date_matches)
                if re.match(r"(?:日)?(?:より|から)", prefix[candidate.end() :])
            ),
            None,
        )
        if start_match is None:
            continue
        scope = prefix[start_match.start() :]
        start_value = parse_first_datetime(scope, base_date).value
        if not start_value:
            continue
        if isinstance(start_value, datetime):
            return start_value
        time_match = re.search(
            r"(?:(午前|午後|正午|昼))?(\d{1,2})時(?:(\d{1,2})分)?",
            scope,
        )
        if not time_match:
            return start_value
        marker, raw_hour, raw_minute = time_match.groups()
        hour = int(raw_hour)
        if marker == "午前" and hour == 12:
            hour = 0
        elif marker == "午後" and hour < 12:
            hour += 12
        elif marker in {"正午", "昼"}:
            hour = 12
        return datetime(
            start_value.year,
            start_value.month,
            start_value.day,
            hour,
            int(raw_minute or 0),
            tzinfo=ZoneInfo("Asia/Tokyo"),
        )
    return None


def _application_deadline(
    text: str,
    base_date: date | None = None,
) -> datetime | date | None:
    """Read an application closing date without treating it as a start date."""

    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    for marker in (
        "応募締切",
        "受付締切",
        "申込締切",
        "申し込み締切",
        "応募期限",
        "受付期限",
        "申込期限",
    ):
        if (index := compact.find(marker)) < 0:
            continue
        parsed = parse_first_datetime(
            compact[index + len(marker) : index + len(marker) + 100],
            base_date,
        ).value
        if parsed:
            return parsed

    # ``応募期間 本日から8月22日まで`` has no parseable start, but its
    # deadline is still exact and is essential when a delayed search result is
    # evaluated after the campaign has closed.
    date_token = re.compile(
        r"(?:(?:20\d{2})[/.年])?\d{1,2}[/.月]\d{1,2}日?"
        r"(?:[()][月火水木金土日][()])?"
        r"(?:\s*(?:(?:午前|午後|正午|昼))?\s*\d{1,2}時(?:\d{1,2}分?)?)?"
        r"(?:\s*\d{1,2}[:：]\d{2})?"
    )
    for match in _APPLICATION_LABEL.finditer(compact):
        scope = match.group(1)
        until = scope.find("まで")
        if until < 0:
            continue
        candidates = list(date_token.finditer(scope[:until]))
        if not candidates:
            continue
        parsed = parse_first_datetime(candidates[-1].group(), base_date).value
        if parsed:
            return parsed
    return None


def _detection_fallback_is_fresh(
    source: SourceConfig,
    config: Config,
    posted_on: date,
    detected_on: date,
) -> bool:
    """Bound guessed starts to newly published social posts.

    A source can opt into a longer window for a known, store-specific format;
    exact starts and deadlines are still parsed independently.
    """

    source = source_with_runtime_parser_profile(source)
    raw_limit = source.parser_options.get(
        "detection_fallback_max_age_days",
        config.system.get("detection_fallback_max_age_days", 7),
    )
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"bad detection_fallback_max_age_days: {source.id}") from exc
    if limit < 0:
        raise ValueError(f"bad detection_fallback_max_age_days: {source.id}")
    age = (detected_on - posted_on).days
    return 0 <= age <= limit


def _official_sale_start(
    text: str,
    base_date: date,
) -> datetime | date | None:
    """Read a date immediately before an official ``予約開始`` label.

    Product announcements commonly put the release date first and the order
    date on the next sentence (for example ``7/17発売。このあと6/25 0:00から
    予約開始``).  Scope parsing to the final sentence/cue so the release date
    cannot become the sale date.
    """

    normalized = unicodedata.normalize("NFKC", text)
    for match in re.finditer(
        r"予約(?:受付)?(?:を)?(?:開始|スタート)",
        normalized,
    ):
        prefix = normalized[: match.start()]
        scope_start = max(
            (prefix.rfind(marker) + len(marker) for marker in ("\n", "。", "!", "！")),
            default=0,
        )
        cue_start = max(
            (prefix.rfind(marker) for marker in ("このあと", "本日", "明日")),
            default=-1,
        )
        if cue_start >= scope_start:
            scope_start = cue_start
        if parsed := parse_period_start(prefix[scope_start:], base_date).value:
            return parsed
        if re.search(r"本日(?:から|より)?$", prefix[scope_start:].strip()):
            return base_date
    return None


def _notice_range_scope(text: str) -> str | None:
    """Return a loose OCR notice scope only when it contains a period marker."""
    compact = re.sub(r"\s+", "", text)
    match = re.search(r"抽選販売のお知らせ[：:]?(.{0,180})", compact)
    if not match or not any(marker in match.group(1) for marker in ("まで", "～", "〜")):
        return None
    return match.group(1)


def _notice_range_start(text: str, base_date: date | None = None) -> datetime | date | None:
    """Parse image notices where OCR lost the explicit application-period label."""
    scope = _notice_range_scope(text)
    if not scope:
        return None
    return parse_period_start(scope, base_date).value


def _deadline_only_application_period(text: str) -> bool:
    """Detect an application label or loose notice that publishes only its deadline."""
    compact = re.sub(r"\s+", "", text)
    for match in _APPLICATION_LABEL.finditer(compact):
        if period_is_deadline_only(
            match.group(1),
            label_is_start=_period_label_is_start(compact, match),
        ):
            return True
    scope = _notice_range_scope(text)
    return bool(scope and period_is_deadline_only(scope))


def parse_livepocket_event(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    page_title = title(html) or source.name
    text = visible_text(html)
    game_id = _game_id(f"{page_title} {text}")
    if not game_id or not source.supports(game_id):
        return [], [], []
    products = _box_products(f"{page_title}\n{text}", game_id, config)
    if not products:
        return [], [], []
    start_at = _application_start(text)
    if not start_at:
        return (
            [],
            [],
            [
                _alert(
                    source,
                    url,
                    page_title,
                    "livepocket_application_period_missing",
                    "BOX抽選の個別ページだが応募期間・販売受付期間を解析できません",
                    game_id,
                )
            ],
        )
    profile = _livepocket_profile(source)
    if profile is None:
        raise ValueError(f"livepocket parser profile is missing: {source.id}")
    retailer_id, retailer_name = profile
    cases = [
        LotteryCase(
            game_id,
            retailer_id,
            retailer_name,
            product_name,
            product_category,
            product_key,
            start_at,
            url,
            url,
            source.source_tier,
            "livepocket_detail_application_period",
            "high",
        ).with_id()
        for product_name, product_category, product_key in products
    ]
    return cases, [], []


def parse_curated_store_campaign(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Parse a narrowly configured store campaign from a secondary roundup.

    Every store name, account URL, section marker, and product identifier comes
    from the runtime configuration.  The generic parser therefore exposes
    the validation method without revealing which local campaign it protects.
    """

    options = source.parser_options
    required_strings = (
        "official_status_url",
        "section_start_marker",
        "section_end_marker",
        "game_id",
        "retailer_id",
        "retailer_name",
        "product_name",
        "product_category",
        "canonical_product_key",
    )
    missing = [
        name
        for name in required_strings
        if not isinstance(options.get(name), str) or not str(options[name]).strip()
    ]
    if missing:
        raise ValueError(
            f"curated campaign parser options are missing: {source.id}:" + ",".join(missing)
        )
    official_status_url = str(options["official_status_url"])
    game_id = str(options["game_id"])
    required_markers = _string_list_option(source, "required_product_markers")

    soup = BeautifulSoup(html, "lxml")
    has_official_status = any(
        isinstance(anchor, Tag)
        and str(anchor.get("href", "")).split("?", 1)[0].rstrip("/")
        == official_status_url.rstrip("/")
        for anchor in soup.find_all("a", href=True)
    )
    page_title = title(html) or source.name
    text = visible_text(html)
    if not has_official_status:
        return (
            [],
            [],
            [
                _alert(
                    source,
                    url,
                    page_title,
                    "curated_campaign_official_status_missing",
                    "補完記事から設定済み店舗の公式投稿リンクが消えました",
                    game_id,
                )
            ],
        )

    section_match = re.search(
        re.escape(str(options["section_start_marker"]))
        + r"(?P<section>.{0,2000}?)"
        + re.escape(str(options["section_end_marker"])),
        text,
        re.S,
    )
    section = section_match.group("section") if section_match else ""
    period_label = str(options.get("application_period_label") or "応募期間")
    period_match = re.search(
        re.escape(period_label) + r"[：:]?\s*(?P<start>20\d{2}年\d{1,2}月\d{1,2}日"
        r"(?:\([^)]*\))?)(?:\s*)[～〜~](?:\s*)"
        r"(?P<end>(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\))?)",
        section,
    )
    product_evidence = f"{page_title} {text}"
    if not period_match or any(
        marker.casefold() not in product_evidence.casefold() for marker in required_markers
    ):
        return (
            [],
            [],
            [
                _alert(
                    source,
                    url,
                    page_title,
                    "curated_campaign_fields_missing",
                    "設定済み店舗の対象BOXまたは応募期間を解析できません",
                    game_id,
                )
            ],
        )

    start_at = parse_first_datetime(period_match.group("start")).value
    start_date = start_at.date() if isinstance(start_at, datetime) else start_at
    end_at = parse_first_datetime(period_match.group("end"), start_date).value
    if start_at is None or end_at is None:
        return (
            [],
            [],
            [
                _alert(
                    source,
                    url,
                    page_title,
                    "curated_campaign_application_period_invalid",
                    "設定済み店舗の応募期間を日付へ変換できません",
                    game_id,
                )
            ],
        )

    case = LotteryCase(
        game_id=game_id,
        retailer_id=str(options["retailer_id"]),
        retailer_name=str(options["retailer_name"]),
        product_name=str(options["product_name"]),
        product_category=str(options["product_category"]),
        canonical_product_key=str(options["canonical_product_key"]),
        start_at=start_at,
        end_at=end_at,
        official_url=official_status_url,
        source_url=url,
        source_tier=source.source_tier,
        extraction_method="secondary_roundup_store_scoped_period",
        confidence="medium",
    ).with_id()
    return [case], [], []


def parse_hobby_station_news(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Parse each official Hobby Station lottery block without relying on LivePocket search."""
    soup = BeautifulSoup(html, "lxml")
    cases: list[LotteryCase] = []
    alerts: list[Alert] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        event_url = urljoin(url, str(anchor.get("href")))
        if not re.fullmatch(r"https://(?:t\.)?livepocket\.jp/e/[A-Za-z0-9_-]+", event_url):
            continue
        if event_url in seen_urls:
            continue
        seen_urls.add(event_url)
        block = anchor.find_parent("p")
        if not isinstance(block, Tag):
            continue
        block_text = block.get_text(" ", strip=True)
        if "抽選" not in block_text or "応募期間" not in block_text:
            continue
        game_id = _game_id(block_text)
        if not game_id or not source.supports(game_id):
            continue
        products = _box_products(block_text, game_id, config)
        if not products:
            continue
        start_at = _application_start(block_text)
        page_title = block_text[:120] or source.name
        if not start_at:
            alerts.append(
                _alert(
                    source,
                    event_url,
                    page_title,
                    "hobby_station_application_period_missing",
                    "ホビステ公式ニュースのBOX抽選だが応募期間を解析できません",
                    game_id,
                )
            )
            continue
        profile = _livepocket_profile(source)
        if profile is None:
            raise ValueError(f"livepocket parser profile is missing: {source.id}")
        retailer_id, retailer_name = profile
        cases.extend(
            LotteryCase(
                game_id,
                retailer_id,
                retailer_name,
                product_name,
                product_category,
                product_key,
                start_at,
                event_url,
                url,
                SourceTier.OFFICIAL,
                "hobby_station_official_application_period",
                "high",
            ).with_id()
            for product_name, product_category, product_key in products
        )
    return cases, [], alerts


def parse_hobby_station_source(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    if is_hobby_station_news_page(source.id, url):
        return parse_hobby_station_news(html, url, source, config)
    return parse_livepocket_event(html, url, source, config)


def _tweet_container(status_anchor: Tag) -> Tag | None:
    fallback: Tag | None = None
    for parent in status_anchor.parents:
        if not isinstance(parent, Tag):
            continue
        # X's official oEmbed endpoint returns a blockquote rather than the
        # div-based Yahoo/Twstalker markup used by the ordinary discovery path.
        if parent.name == "item":
            return parent
        if parent.name in {"blockquote", "article"} and parent.find("p"):
            return parent
        if parent.name != "div":
            continue
        class_attr = parent.get("class")
        classes = (
            " ".join(str(value) for value in class_attr)
            if isinstance(class_attr, list)
            else str(class_attr or "")
        )
        if "Tweet_TweetContainer" in classes:
            return parent
        if "activity-posts" in classes.split():
            return parent
        if fallback is None and parent.find("p") and parent.find("time"):
            fallback = parent
    return fallback


def _tweet_body(container: Tag) -> str:
    def is_body_class(value: str | list[str] | None) -> bool:
        classes = value if isinstance(value, list) else [value or ""]
        return "Tweet_body" in " ".join(classes)

    if container.name == "item":
        parts = [
            node.get_text(" ", strip=True)
            for node in container.find_all(["title", "description"], recursive=False)
        ]
        return " ".join(part for part in parts if part)

    mirror_body = container.select_one(".activity-descp > p")
    body = mirror_body or container.find(
        "p",
        class_=is_body_class,
    )
    return (body or container).get_text(" ", strip=True)


def _status_parts(href: str, expected_account: str) -> tuple[str, str] | None:
    """Accept only the configured official account on X or its profile mirror."""
    match = _X_STATUS_URL.match(href) or _MIRROR_STATUS_URL.match(href)
    if not match or match.group(1).casefold() != expected_account.casefold():
        return None
    return match.group(1), match.group(2)


def _official_status_url(account: str, status_id: str) -> str:
    return f"https://x.com/{account}/status/{status_id}"


def _social_status_containers(
    html: str,
    url: str,
    account: str,
) -> list[tuple[str, Tag]]:
    """Return official status containers from Yahoo, mirrors, or Bing RSS."""

    parts = urlsplit(url)
    is_rss = (
        parts.netloc.casefold().removeprefix("www.") == "bing.com"
        and "format=rss" in parts.query.casefold()
    )
    soup = BeautifulSoup(html, "xml" if is_rss else "lxml")
    records: list[tuple[str, Tag]] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if _status_parts(href, account) and (container := _tweet_container(anchor)):
            records.append((href, container))
    if is_rss:
        for item in soup.find_all("item"):
            link = item.find("link")
            href = link.get_text(strip=True) if link else ""
            if _status_parts(href, account):
                records.append((href, item))
    return records


def _known_release_for_text(
    text: str,
    source: SourceConfig,
    known_releases: list[Release] | None,
) -> Release | None:
    """Infer an image-only post's game from the already fetched official catalog."""
    if not known_releases:
        return None
    folded = re.sub(
        r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー]+",
        "",
        unicodedata.normalize("NFKC", text),
    ).casefold()
    matches = [
        release
        for release in known_releases
        if source.supports(release.game_id)
        and len(release_title_token(release.product_name)) >= 3
        and release_title_token(release.product_name) in folded
    ]
    return max(matches, key=lambda item: len(release_title_token(item.product_name)), default=None)


def _product_from_tweet(
    container: Tag, text: str, game_id: str,
    exclude_keywords: list[str] | None = None,
) -> tuple[str, str] | None:
    category_map = {
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
    categories = category_map[game_id]
    # Yahooの強調タグ境界では「抽選 販売」のように語中へ表示用空白が
    # 入る。すべての日本語を結合するとOCRの改行まで消えるため、解析の
    # 区切りに使う語だけを限定して正規化する。
    matching_text = re.sub(r"抽選[ \t\u3000]+販売", "抽選販売", text)
    matching_text = re.sub(r"抽選[ \t\u3000]+受付", "抽選受付", matching_text)
    category = next((value for value in categories if value in matching_text), "")
    code_patterns = {
        "one_piece_card": r"\b(?:OP|EB|PRB)-\d{2}\b",
        "dragon_ball_fusion_world": r"\b(?:FB|SB|ST)\d{2}\b",
        "gundam_card": r"\b(?:GD|EB)\d{2}\b",
    }
    product_code = (
        re.search(code_pattern, matching_text, re.I)
        if (code_pattern := code_patterns.get(game_id))
        else None
    )
    product_name = ""
    quote_pattern = r"[「『【《](?:#)?([^」』】》]{2,100})[」』】》]"
    category_pattern = "|".join(map(re.escape, categories))
    # 商品カテゴリーに直接続く名前を優先。先にデッキ商品が並ぶ混在投稿でも
    # 無関係な先頭の括弧を拡張パック名にしない。
    qualified = re.findall(rf"(?:{category_pattern})\s*{quote_pattern}", matching_text)
    for candidate in [*qualified, *re.findall(quote_pattern, matching_text)]:
        cleaned = candidate.strip(" #　")
        compact_candidate = re.sub(r"\s+", "", cleaned).casefold()
        if (
            cleaned
            and compact_candidate not in _NON_PRODUCT_LABELS
            and not is_provisional_product_name(cleaned)
            and not any(word in cleaned for word in (exclude_keywords or []))
        ):
            product_name = cleaned
            break
    if not product_name and category:
        trailing = re.search(
            rf"{re.escape(category)}\s*[「『【]?\s*(?:#)?(.{{2,60}}?)"
            r"(?=(?:の|を)?\s*(?:抽選販売|抽選受付|抽選応募|受付期間|申し込み|申込み)"
            r"|詳細は|[。\n])",
            matching_text,
        )
        if trailing:
            product_name = trailing.group(1).strip(" 「『【」』】#　")
    if not product_name:
        for anchor in container.find_all("a"):
            href = str(anchor.get("href") or "")
            if not href.startswith("/realtime/search?p=%23"):
                continue
            hashtag = anchor.get_text(" ", strip=True).lstrip("#").strip()
            if hashtag and hashtag not in _NON_PRODUCT_HASHTAGS and len(hashtag) >= 3:
                product_name = hashtag
                break
    if not product_name and product_code:
        product_name = product_code.group(0).upper()
    if not product_name:
        if category:
            product_name = f"{category}（商品名は画像参照）"
        elif re.search(r"(?i)\b1?BOX\b", text):
            product_name = "BOX（商品名は画像参照）"
        else:
            return None
    if category and category not in product_name:
        product_name = f"{category}「{product_name}」"
    if product_code and product_code.group(0).upper() not in product_name:
        product_name += f" [{product_code.group(0).upper()}]"
    return product_name, category or "BOX（投稿記載から推定）"


def _application_url(container: Tag, status_url: str) -> str:
    # Yahoo often leaves the real destination in an anchor label/title while
    # keeping t.co in href.  Recover durable official URLs before falling back
    # to the short link so Amazon ASINs and Furuichi articles deduplicate across
    # independent social and official discovery paths.
    for anchor in container.find_all("a", href=True):
        values = [
            str(anchor.get("href") or ""),
            anchor.get_text(" ", strip=True),
            str(anchor.get("title") or ""),
            str(anchor.get("data-url") or ""),
            str(anchor.get("data-expanded-url") or ""),
        ]
        candidate_text = " ".join(values)
        if match := _AMAZON_PRODUCT_URL.search(candidate_text):
            return f"https://www.amazon.co.jp/dp/{match.group(1).upper()}"
        if match := _FURUICHI_ARTICLE_URL.search(candidate_text):
            return "https://www.furu1.net/news/news_information/" + match.group(1)
    for anchor in container.find_all("a", href=True):
        href = str(anchor.get("href"))
        label = anchor.get_text(" ", strip=True)
        if href.startswith("https://t.co/") and not label.startswith("pic.x.com"):
            return href
    return status_url


def _tweet_image_urls(container: Tag) -> list[str]:
    urls: list[str] = []
    for image in container.find_all("img", src=True):
        src = str(image.get("src") or "")
        parts = urlsplit(src)
        if (
            parts.scheme == "https"
            and parts.netloc
            in {
                "rts-pctr.c.yimg.jp",
                "pbs.twimg.com",
            }
            and src not in urls
        ):
            urls.append(src)
    # A direct X media URL is longer-lived than Yahoo's temporary image proxy.
    # Keep both as fallbacks, but try the durable source first when available.
    urls.sort(key=lambda value: urlsplit(value).netloc != "pbs.twimg.com")
    return urls[:4]


def _post_date(status_id: str, timezone: str) -> date:
    timestamp_ms = (int(status_id) >> 22) + _X_EPOCH_MS
    return datetime.fromtimestamp(timestamp_ms / 1000, ZoneInfo(timezone)).date()


def _official_oembed_markup(raw: str, url: str, expected_account: str) -> str:
    """Extract and verify an official X post returned by Twitter oEmbed."""

    if urlsplit(url).netloc.casefold() not in {"publish.twitter.com", "publish.x.com"}:
        return raw
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("X oEmbed response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("X oEmbed response is not an object")
    status = _status_parts(str(payload.get("url") or ""), expected_account)
    author_url = str(payload.get("author_url") or "")
    author_path = urlsplit(author_url).path.strip("/").casefold()
    embedded_html = payload.get("html")
    if not status or author_path != expected_account.casefold():
        raise ValueError("X oEmbed response belongs to a different account")
    if not isinstance(embedded_html, str) or not embedded_html.strip():
        raise ValueError("X oEmbed response does not contain post markup")
    return embedded_html


def is_yahoo_realtime_source(source: SourceConfig | str) -> bool:
    return _yahoo_profile(source) is not None


def yahoo_realtime_page_loaded(
    html: str,
    source: SourceConfig | str,
    url: str = "",
) -> bool:
    """Confirm that Yahoo returned a parseable result or an explicit empty result."""

    if yahoo_realtime_has_matching_status(html, source, url):
        return True
    if not is_yahoo_realtime_source(source):
        return False
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    return any(
        marker in text
        for marker in (
            "一致する情報は見つかりませんでした",
            "検索結果はありません",
        )
    )


def yahoo_realtime_has_matching_status(
    html: str,
    source: SourceConfig | str,
    url: str = "",
) -> bool:
    """Return whether a Yahoo or mirror page contains the configured account."""

    profile = _yahoo_profile(source)
    if profile is None:
        return False
    account, _, _ = profile
    parse_url = (
        url
        if url
        else "https://www.bing.com/search?format=rss"
        if "<rss" in html[:500].casefold()
        else ""
    )
    return bool(_social_status_containers(html, parse_url, account))


def yahoo_repair_discovery_urls(
    source: SourceConfig | str,
    seen_cases: object,
    *,
    limit: int = 5,
) -> list[str]:
    """Revisit only prior Yahoo cases whose provisional product name needs repair."""
    profile = _yahoo_profile(source)
    if profile is None or not isinstance(seen_cases, dict):
        return []
    account, retailer_id, _ = profile
    status_ids: set[str] = set()
    for raw_record in seen_cases.values():
        if not isinstance(raw_record, dict) or raw_record.get("retailer_id") != retailer_id:
            continue
        product_name = str(raw_record.get("product_name") or "")
        if not is_provisional_product_name(product_name):
            continue
        status = _status_parts(str(raw_record.get("source_url") or ""), account)
        if status:
            status_ids.add(status[1])
    newest = sorted(status_ids, key=int, reverse=True)[:limit]
    return [
        (
            "https://search.yahoo.co.jp/realtime/search/tweet/"
            f"{status_id}?detail=1&ifr=tl_twdtl&rkf=1"
        )
        for status_id in newest
    ]


def _record_ocr_pending(
    pending: dict[str, object] | None,
    status_url: str,
    source: SourceConfig,
    retailer_name: str,
    error: str,
    attempt_token: str | None,
) -> int:
    if pending is None:
        return 1
    previous = pending.get(status_url)
    previous_record = previous if isinstance(previous, dict) else {}
    previous_attempts = int(previous_record.get("attempts", 0))
    attempts = (
        previous_attempts
        if attempt_token and previous_record.get("last_attempt_token") == attempt_token
        else previous_attempts + 1
    )
    now = datetime.now(UTC).isoformat()
    pending[status_url] = {
        "source_id": source.id,
        "retailer_name": retailer_name,
        "status_url": status_url,
        "attempts": attempts,
        "first_seen_at": previous_record.get("first_seen_at") or now,
        "last_seen_at": now,
        "last_error": error,
        "last_attempt_token": attempt_token,
    }
    return attempts


def parse_yahoo_realtime(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    detected_on: date | None = None,
    ocr_reader: OcrReader | None = None,
    ocr_cache: dict[str, str] | None = None,
    known_releases: list[Release] | None = None,
    ocr_pending: dict[str, object] | None = None,
    ocr_cache_meta: dict[str, object] | None = None,
    ocr_attempt_token: str | None = None,
    diagnostics: dict[str, int] | None = None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    def count(reason: str) -> None:
        if diagnostics is not None:
            diagnostics[reason] = diagnostics.get(reason, 0) + 1

    source = source_with_runtime_parser_profile(source)
    profile = _yahoo_profile(source)
    if profile is None:
        raise ValueError(f"Yahoo parser profile is missing: {source.id}")
    account, retailer_id, retailer_name = profile
    markup = _official_oembed_markup(html, url, account)
    detected = detected_on or datetime.now(ZoneInfo(config.timezone)).date()
    cases: dict[str, LotteryCase] = {}
    alerts: list[Alert] = []
    processed_statuses: set[str] = set()
    for href, container in _social_status_containers(markup, url, account):
        status = _status_parts(href, account)
        if not status:
            continue
        _, status_id = status
        if status_id in _string_list_option(source, "excluded_status_ids"):
            continue
        status_url = _official_status_url(account, status_id)
        if status_url in processed_statuses:
            continue
        processed_statuses.add(status_url)
        count("account_posts")
        post_text = _tweet_body(container)
        compact_text = re.sub(r"\s+", "", post_text)
        if _requires_disallowed_application(post_text):
            count("disallowed_application")
            continue
        required_mentions = _string_list_option(source, "required_retailer_mentions")
        if required_mentions and not any(
            mention.casefold() in compact_text.casefold() for mention in required_mentions
        ):
            count("retailer_not_matched")
            continue
        excluded_mentions = _string_list_option(source, "excluded_retailer_mentions")
        if any(
            mention.casefold() in compact_text.casefold() for mention in excluded_mentions
        ):
            count("excluded_retailer")
            continue
        postponement = next(
            (word for word in _POSTPONEMENT_WORDS if word in compact_text),
            None,
        )
        has_action = any(word in compact_text for word in _ACTION_WORDS) or bool(
            re.search(
                r"抽選で.{0,100}(?:購入|買える).{0,30}(?:権利|チャンス)",
                compact_text,
            )
        )
        amazon_invitation = (
            bool(source.parser_options.get("amazon_invitation"))
            and "招待リクエスト" in compact_text
            and any(
                marker in compact_text
                for marker in (
                    "受付開始",
                    "受付が開始",
                    "受付を開始",
                    "リクエスト開始",
                    "リクエスト受付",
                )
            )
        )
        official_lorcana_sale = (
            bool(source.parser_options.get("official_sale"))
            and "発売" in compact_text
            and bool(
                re.search(
                    r"予約(?:受付)?(?:を)?(?:開始|スタート)",
                    compact_text,
                )
            )
            and not any(marker in compact_text for marker in ("大会", "イベント", "トーナメント"))
        )
        if (
            not amazon_invitation
            and not official_lorcana_sale
            and ("抽選" not in compact_text or not (has_action or postponement))
        ):
            count("not_application_announcement")
            continue
        if any(word in compact_text for word in ("大会", "参加抽選", "当選発表のみ")):
            count("tournament_or_result")
            continue
        posted_on = _post_date(status_id, config.timezone)
        if (detected - posted_on).days > int(config.system.get("implausible_past_days", 45)):
            count("old_post")
            continue
        known_release = _known_release_for_text(post_text, source, known_releases)
        game_id = _game_id(post_text) or (known_release.game_id if known_release else None)
        if postponement:
            if not game_id or not source.supports(game_id):
                continue
            postponed_product = _product_from_tweet(container, post_text, game_id)
            product_label = postponed_product[0] if postponed_product else "対象BOX"
            alerts.append(
                _alert(
                    source,
                    status_url,
                    retailer_name,
                    "lottery_postponed_or_cancelled",
                    (
                        f"{product_label}の抽選販売について「{postponement}」を検出。"
                        "新たな日程は公式サイト・アプリで確認してください"
                    ),
                    game_id,
                )
            )
            continue
        # 二次情報の店舗一覧は、本文に店舗名が含まれていても各店の新規開始告知
        # ではない。個別店舗の告知だけを候補にし、まとめ投稿から案件を作らない。
        if source.source_tier == SourceTier.SECONDARY and any(
            marker in compact_text for marker in _SECONDARY_ROUNDUP_MARKERS
        ):
            continue
        uses_detection_next_day = (
            source.lottery_start_policy == LotteryStartPolicy.FIRST_DETECTION_NEXT_DAY
        )
        uses_first_detection = source.lottery_start_policy == LotteryStartPolicy.FIRST_DETECTION
        uses_detection_policy = uses_detection_next_day or uses_first_detection
        start_at = None if uses_detection_policy else _application_start(post_text, posted_on)
        if official_lorcana_sale and not start_at:
            start_at = _official_sale_start(post_text, posted_on)
        deadline_without_start = (
            False if uses_detection_policy else _deadline_only_application_period(post_text)
        )
        extraction_method = "yahoo_realtime_body_application_period"
        confidence = "high"
        if source.source_tier == SourceTier.SECONDARY:
            extraction_method = "yahoo_realtime_secondary_body_application_period"
            confidence = "medium"
        if amazon_invitation:
            extraction_method = "yahoo_realtime_amazon_invitation_seen"
            confidence = "medium"
        if official_lorcana_sale:
            extraction_method = "yahoo_realtime_official_sale_period"
            confidence = "high"
        images = _tweet_image_urls(container)
        ocr_text = ""
        ocr_error = ""
        product = _product_from_tweet(container, post_text, game_id) if game_id else None

        # 店舗Xは本文に商品名だけを書き、ゲーム名・BOX分類・応募期間を
        # 添付画像へ寄せることがある。ゲーム判定より先に必要時OCRを実行し、
        # 本文に「ポケカ」「ワンピ」がないという理由で静かに捨てない。
        if images and (not game_id or not product or not start_at):
            if ocr_cache is not None:
                ocr_text = ocr_cache.get(status_url, "")
                if ocr_text and ocr_cache_meta is not None:
                    ocr_cache_meta[status_url] = {"updated_at": datetime.now(UTC).isoformat()}
            if not ocr_text and ocr_reader:
                try:
                    ocr_text = ocr_reader(images).strip()[:12_000]
                except Exception as exc:
                    ocr_error = f"添付画像OCRに失敗: {type(exc).__name__}: {str(exc)[:160]}"
                if not ocr_text and not ocr_error:
                    ocr_error = "添付画像OCRから文字を取得できません"
                if ocr_text and ocr_cache is not None:
                    ocr_cache[status_url] = ocr_text
                    if ocr_cache_meta is not None:
                        ocr_cache_meta[status_url] = {"updated_at": datetime.now(UTC).isoformat()}
            # A non-empty cached or newly read OCR result means the OCR step
            # itself recovered. Clear its pending failure before later
            # product filters can intentionally exclude the post.
            if ocr_text and ocr_pending is not None:
                ocr_pending.pop(status_url, None)
        combined_text = f"{post_text}\n{ocr_text}" if ocr_text else post_text
        combined_compact = re.sub(r"\s+", "", combined_text)
        ocr_compact = re.sub(r"\s+", "", ocr_text)
        application_end = _status_datetime_option(
            source,
            "confirmed_application_ends",
            status_id,
        ) or _application_deadline(combined_text, posted_on)
        if application_end is not None:
            application_end_date = (
                application_end.date()
                if isinstance(application_end, datetime)
                else application_end
            )
            # Search and profile mirrors can surface an old post for the first
            # time after its application has already closed.  It is historical
            # evidence, not a newly opened lottery.
            if application_end_date < detected:
                count("application_ended")
                if ocr_pending is not None:
                    ocr_pending.pop(status_url, None)
                continue
        ocr_start = None
        if ocr_text and not uses_detection_policy:
            ocr_start = _application_start(ocr_text, posted_on) or _notice_range_start(
                ocr_text, posted_on
            )
        ocr_has_current_or_future_open_period = False
        if ocr_start:
            ocr_start_date = ocr_start.date() if isinstance(ocr_start, datetime) else ocr_start
            ocr_has_current_or_future_open_period = ocr_start_date >= posted_on and any(
                word in ocr_compact for word in _OPEN_APPLICATION_WORDS
            )

        # 結果専用画像を新規受付にしない一方、公式の開始告知が本文では
        # 「詳細は画像」のみで、画像の注意事項に「当選者」も含む投稿は救う。
        # 画像の受付開始日が投稿日以降なら開始告知として扱い、投稿日より
        # 前なら過去の受付期間を載せた結果投稿として従来どおり除外する。
        if any(word in combined_compact for word in _CLOSED_OR_RESULT_WORDS) and not (
            any(word in compact_text for word in _OPEN_APPLICATION_WORDS)
            or ocr_has_current_or_future_open_period
        ):
            if ocr_pending is not None:
                ocr_pending.pop(status_url, None)
            continue
        game_id = game_id or _game_id(combined_text)
        if not game_id:
            # 本番では公式商品カタログを先に渡している。そこにも本文/OCRにも
            # 一致しない抽選でも、OCRそのものが失敗した投稿は保留する。
            # 同じ投稿で失敗が繰り返された時だけ監視異常へ昇格する。
            if ocr_error:
                attempts = _record_ocr_pending(
                    ocr_pending,
                    status_url,
                    source,
                    retailer_name,
                    ocr_error,
                    ocr_attempt_token,
                )
                threshold = int(config.system.get("ocr_failure_alert_threshold", 2))
                if attempts >= max(2, threshold):
                    alerts.append(
                        _alert(
                            source,
                            status_url,
                            retailer_name,
                            "yahoo_image_ocr_repeated_failure",
                            f"{ocr_error}（連続{attempts}回。保留候補を手動確認してください）",
                        )
                    )
                continue
            # OCRが成功した、または画像がない状態で公式商品一覧にも一致しない
            # 投稿は、従来どおり他TCGとして静かに除外する。
            if known_releases is not None:
                if ocr_pending is not None:
                    ocr_pending.pop(status_url, None)
                continue
            alerts.append(
                _alert(
                    source,
                    status_url,
                    retailer_name,
                    "yahoo_image_ocr_failed" if ocr_error else "yahoo_lottery_post_without_game",
                    ocr_error
                    or (
                        "公式アカウントの抽選受付投稿を検出したが、"
                        "本文・画像からゲームを判定できません"
                    ),
                )
            )
            continue
        if not source.supports(game_id):
            continue

        game = config.games[game_id]
        confirmed_product = _status_product_option(source, status_id)
        has_excluded_product = any(word in combined_text for word in game.product_exclude_keywords)
        has_box_signal = any(word in combined_text for word in game.box_product_keywords) or bool(
            re.search(r"(?i)\b1?BOX\b", combined_text)
        )
        strict_product_exclusions = bool(
            source.parser_options.get("strict_product_exclusions", False)
        )
        # 遊戯王は商品名そのものがシリーズ区分を兼ねる。低相場シリーズの
        # 投稿に「1BOX」があっても、BOX証拠で除外を打ち消さない。
        if game_id == "yu_gi_oh" and has_excluded_product:
            continue
        if (
            has_excluded_product
            and (strict_product_exclusions or (not confirmed_product and not has_box_signal))
        ):
            count("excluded_product")
            continue

        product = confirmed_product or _product_from_tweet(
            container, combined_text, game_id, game.product_exclude_keywords,
        )
        if (
            not confirmed_product
            and known_release
            and known_release.game_id == game_id
            and (
                not product
                or is_provisional_product_name(product[0])
            )
        ):
            # A social post may spell only the official title (without
            # ``ブースターパック`` or ``BOX``), while image OCR may recover
            # only the generic word ``1BOX``.  Reuse the already fetched maker
            # catalog instead of keeping or silently discarding a provisional
            # product name.
            product = (
                known_release.product_name,
                known_release.product_category,
            )
        if (
            not product
            and source.id == "yahoo_realtime_dmm_onepiece_secondary"
            and game_id == "one_piece_card"
            and "DMM通販" in combined_compact
        ):
            # The DMM roundup account sometimes lists only product titles after a
            # generic ONE PIECE heading. Preserve the campaign alert even when
            # no category or product code survives Yahoo's text extraction.
            product = (
                "ONE PIECEカードゲーム DMM通販 抽選対象BOX",
                "BOX（商品名は公式応募ページ参照）",
            )
        if ocr_text and not uses_detection_next_day:
            deadline_without_start = deadline_without_start or _deadline_only_application_period(
                ocr_text
            )
            if ocr_start:
                start_at = ocr_start
                extraction_method = (
                    "yahoo_realtime_amazon_invitation_seen"
                    if amazon_invitation
                    else "yahoo_realtime_image_ocr_application_period"
                )
                confidence = "medium"
        if not product:
            if ocr_error:
                attempts = _record_ocr_pending(
                    ocr_pending,
                    status_url,
                    source,
                    retailer_name,
                    ocr_error,
                    ocr_attempt_token,
                )
                threshold = int(config.system.get("ocr_failure_alert_threshold", 2))
                if attempts >= max(2, threshold):
                    alerts.append(
                        _alert(
                            source,
                            status_url,
                            retailer_name,
                            "yahoo_image_ocr_repeated_failure",
                            f"{ocr_error}（連続{attempts}回。BOX商品名を手動確認してください）",
                            game_id,
                        )
                    )
            elif source.id == "yahoo_realtime_hobbylink_japan":
                # HLJ deliberately keeps product names on its official support
                # article and posts only a short "受付開始／詳細はこちら" notice
                # to X. The direct official article source parses the products,
                # so this is expected—not a broken social parser.
                if ocr_pending is not None:
                    ocr_pending.pop(status_url, None)
            elif source.source_tier == SourceTier.SECONDARY:
                # 二次情報アカウントの曖昧な投稿は監視異常ではない。商品名と
                # 開始日時を確定できる個別投稿だけを案件化する。
                if ocr_pending is not None:
                    ocr_pending.pop(status_url, None)
            else:
                alerts.append(
                    _alert(
                        source,
                        status_url,
                        retailer_name,
                        "yahoo_lottery_post_without_product",
                        "公式アカウントの抽選受付投稿を検出したがBOX商品名を解析できません",
                        game_id,
                    )
                )
            continue
        product_name, product_category = product
        if any(word in product_name for word in game.product_exclude_keywords):
            count("excluded_product")
            continue
        opportunity_kind = OpportunityKind.LOTTERY
        if official_lorcana_sale and start_at:
            opportunity_kind = OpportunityKind.DIRECT_SALE
            extraction_method = (
                "yahoo_realtime_official_sale_image_ocr_period"
                if ocr_start
                else "yahoo_realtime_official_sale_period"
            )
            confidence = "medium" if ocr_start else "high"
        if uses_detection_next_day:
            # This opt-in policy is for sources whose images mix deadlines,
            # winner announcements, release dates, and purchase windows.
            # Ignore candidate start dates and use a stable first-detection
            # fallback, while an exact application deadline still blocks an
            # already-closed campaign above.
            if not _detection_fallback_is_fresh(source, config, posted_on, detected):
                continue
            start_at = detected + timedelta(days=1)
            extraction_method = "yahoo_realtime_detected_next_day"
            confidence = "low"
        elif uses_first_detection:
            if not _detection_fallback_is_fresh(source, config, posted_on, detected):
                continue
            start_at = detected
            extraction_method = "yahoo_realtime_detected_open"
            confidence = "low"
        if not start_at:
            if official_lorcana_sale:
                # An announcement without a machine-readable date is useful as
                # a timely official signal, but must not create a guessed
                # Calendar entry.  The post date is stable and prevents an old
                # search result from appearing newly open on every run.
                start_at = posted_on
                opportunity_kind = OpportunityKind.DIRECT_SALE_SEEN
                extraction_method = "yahoo_realtime_official_sale_seen"
                confidence = "medium"
            elif amazon_invitation:
                start_at = posted_on
                extraction_method = "yahoo_realtime_amazon_invitation_seen"
                confidence = "medium"
            may_use_announcement_date = bool(
                source.parser_options.get("use_announcement_date")
            ) and any(word in compact_text for word in ("受付開始", "受付を開始"))
            if not start_at and deadline_without_start and not may_use_announcement_date:
                count("missing_application_start")
                # A secondary search intentionally sees older roundup posts too.
                # Deadline-only items are incomplete candidates, not monitor faults.
                if source.source_tier == SourceTier.SECONDARY:
                    continue
                alerts.append(
                    _alert(
                        source,
                        status_url,
                        retailer_name,
                        "application_deadline_without_start",
                        (
                            "受付期間に締切日時しかなく開始日時を確定できないため、"
                            "Google Calendarへ登録しません"
                        ),
                        game_id,
                    )
                )
                continue
            # Usually secondary reports must publish an exact start. These two
            # retailer-specific announcement feeds consistently post at opening
            # time, so their post date is a bounded medium-confidence fallback.
            if not start_at and source.source_tier == SourceTier.SECONDARY:
                if not may_use_announcement_date:
                    continue
                start_at = posted_on
                extraction_method = "yahoo_realtime_secondary_announcement_date"
                confidence = "medium"
            elif not start_at:
                if not _detection_fallback_is_fresh(source, config, posted_on, detected):
                    continue
                start_at = detected
                extraction_method = "yahoo_realtime_detected_open"
                confidence = "low"
        configured_confirmation_url = source.parser_options.get("official_confirmation_url")
        application_url = (
            str(configured_confirmation_url)
            if configured_confirmation_url
            else _application_url(container, status_url)
        )
        case = LotteryCase(
            game_id,
            retailer_id,
            retailer_name,
            product_name,
            product_category,
            canonical_product_key(game, product_name),
            start_at,
            application_url,
            status_url,
            source.source_tier,
            extraction_method,
            confidence,
            opportunity_kind=opportunity_kind,
            end_at=application_end,
        ).with_id()
        cases[case.case_id] = case
        if ocr_pending is not None:
            ocr_pending.pop(status_url, None)
    return list(cases.values()), [], alerts


def preserve_first_detection_start(
    case: LotteryCase, previous: dict[str, object] | None
) -> LotteryCase:
    """Keep a first-detection date that must not follow later page updates."""
    fallback_methods = {
        "yahoo_realtime_detected_open",
        "yahoo_realtime_detected_next_day",
        "yahoo_realtime_amazon_invitation_seen",
        "yahoo_realtime_official_sale_seen",
        "tsutaya_line_official_form_first_seen",
        "snkrdunk_open_invitation_seen",
        "takaratomy_mall_first_seen_available",
    }
    if case.extraction_method not in fallback_methods or not previous:
        return case
    raw_start = previous.get("start_at")
    if isinstance(raw_start, (date, datetime)):
        return replace(case, start_at=raw_start)
    if not raw_start:
        return case
    try:
        saved_start = (
            datetime.fromisoformat(str(raw_start))
            if "T" in str(raw_start) or " " in str(raw_start)
            else date.fromisoformat(str(raw_start))
        )
    except ValueError:
        return case
    return replace(case, start_at=saved_start)


__all__ = [
    "discover_livepocket_event_urls",
    "is_livepocket_search_page",
    "is_livepocket_source",
    "is_yahoo_realtime_source",
    "parse_livepocket_event",
    "parse_yahoo_realtime",
    "preserve_first_detection_start",
    "yahoo_realtime_has_matching_status",
    "yahoo_realtime_page_loaded",
    "yahoo_repair_discovery_urls",
]
