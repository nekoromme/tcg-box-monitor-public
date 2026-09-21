from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, date, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from tcg_monitor.additional_products import (
    additional_game,
    additional_matches,
    additional_tuples,
)
from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import (
    normalize_text,
    parse_first_datetime,
    parse_period_start,
)
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig
from tcg_monitor.parsers.common import title, visible_text

FURUICHI_SOURCE = "furuichi_official_lottery"
_INDEX_PATH = "/news/news_information.html"
_DETAIL_PATH = re.compile(r"^/news/news_information/[A-Za-z0-9_-]+/?$")
_IMAGE_PATH_PREFIX = "/storage/news/news_information/"
_DEFAULT_START_LABELS = (
    "抽選応募受付期間",
    "抽選受付期間",
    "応募受付期間",
    "抽選応募期間",
    "応募期間",
    "受付期間",
)
_GAME_WORDS = {
    "pokemon_card": ("ポケモンカードゲーム", "ポケモンカード", "ポケカ"),
    "one_piece_card": (
        "ONE PIECEカードゲーム",
        "ONE PIECEカード",
        "ワンピースカード",
        "ワンピカード",
    ),
    "dragon_ball_fusion_world": (
        "ドラゴンボールスーパーカードゲーム",
        "フュージョンワールド",
        "DBFW",
    ),
    "yu_gi_oh": ("遊戯王OCG", "遊戯王カード", "遊☆戯☆王", "遊戯王"),
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

OcrReader = Callable[[list[str]], str]


def _host(value: str) -> str:
    return value.casefold().removeprefix("www.")


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    # 装飾の星は画像OCRで※などに化ける。漢字3文字は必須にして、
    # 他の作品名まで曖昧一致させず、装飾と文字間の空白だけを吸収する。
    return re.sub(r"遊[\s☆★※]*戯[\s☆★※]*王", "遊戯王", value)


def _game_word_pattern(word: str) -> str:
    return r"\s*".join(re.escape(char) for char in _normalized(word) if not char.isspace())


def _clean_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def is_furuichi_source(source_id: str) -> bool:
    return source_id == FURUICHI_SOURCE


def is_furuichi_news_index(source_id: str, url: str) -> bool:
    parts = urlsplit(url)
    return (
        is_furuichi_source(source_id)
        and _host(parts.netloc) == "furu1.net"
        and parts.path.rstrip("/") == _INDEX_PATH
    )


def _game_id(text: str, source: SourceConfig) -> str | None:
    compact = re.sub(r"\s+", "", _normalized(text)).casefold()
    for game_id, words in _GAME_WORDS.items():
        if source.supports(game_id) and any(
            re.sub(r"\s+", "", _normalized(word)).casefold() in compact for word in words
        ):
            return game_id
    return None


def _game_ids(text: str, source: SourceConfig) -> list[str]:
    compact = re.sub(r"\s+", "", _normalized(text)).casefold()
    return [
        game_id
        for game_id, words in _GAME_WORDS.items()
        if source.supports(game_id)
        and any(
            re.sub(r"\s+", "", _normalized(word)).casefold() in compact for word in words
        )
    ]


def _product_candidates(
    text: str,
    source: SourceConfig,
    config: Config,
) -> list[tuple[str, str, str, str]]:
    """Extract each supported BOX from a mixed-game Furuichi notice image."""

    normalized = _normalized(text).replace("\r", "\n")
    occurrences: list[tuple[int, int, str]] = []
    for game_id, words in _GAME_WORDS.items():
        if not source.supports(game_id):
            continue
        for word in sorted(words, key=len, reverse=True):
            occurrences.extend(
                (match.start(), match.end(), game_id)
                for match in re.finditer(_game_word_pattern(word), normalized, re.I)
            )
    occurrences.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    non_overlapping: list[tuple[int, int, str]] = []
    for occurrence in occurrences:
        if non_overlapping and occurrence[0] < non_overlapping[-1][1]:
            continue
        non_overlapping.append(occurrence)

    products = [(gid, name, category, key)
                for gid, game in config.games.items() if source.supports(gid)
                for name, category, key in additional_tuples(game, normalized)]
    seen: set[tuple[str, str]] = set()
    stop_markers = (
        "抽選応募受付期間",
        "抽選受付期間",
        "応募受付期間",
        "受付締切",
        "応募締切",
        "発売日",
        "価格",
        "当選発表",
        "抽選受付について",
        "抽選販売受付について",
        "について",
    )
    for index, (start, _, game_id) in enumerate(non_overlapping):
        end = (
            non_overlapping[index + 1][0]
            if index + 1 < len(non_overlapping)
            else min(len(normalized), start + 500)
        )
        candidate = re.sub(r"\s+", " ", normalized[start:end]).strip()
        marker_positions = [
            position
            for marker in stop_markers
            if (position := candidate.find(marker)) > 0
        ]
        if marker_positions:
            candidate = candidate[: min(marker_positions)].strip()
        candidate = re.split(
            r"20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*発売予定",
            candidate,
            maxsplit=1,
        )[0].strip()
        candidate = re.split(r"[\(（]\d+[\)）]", candidate, maxsplit=1)[0].strip()
        candidate = candidate.strip(" 　「」『』【】[]()（）|｜/\n")[:220]
        game = config.games[game_id]
        if additional_matches(game, candidate):
            continue  # 上で抽出済み。内容物のパック名を別商品にしない。
        classified = classify_product(game, candidate, candidate)
        product_category = classified.product_category
        canonical_product_key = classified.canonical_product_key
        if not classified.is_target:
            # Tesseract can turn "ブースターパック [FB11]" into
            # "ブースタッやク [FB11l/".  A Fusion World booster code
            # plus the surviving booster stem is still specific BOX evidence.
            code_match = re.search(r"(?i)(?:FB|SB|ST)\d{2}", candidate)
            if (
                game_id != "dragon_ball_fusion_world"
                or not code_match
                or "ブースタ" not in candidate
            ):
                continue
            code = code_match.group(0).upper()
            candidate = re.sub(
                r"ブースタ[^\s]{0,8}ク",
                "ブースターパック",
                candidate,
                count=1,
            )
            candidate = re.sub(
                rf"(?i)\[?{re.escape(code)}[A-Za-z/\]]*",
                f"[{code}]",
                candidate,
                count=1,
            ).replace("BRICHTNESS", "BRIGHTNESS")
            product_category = "ブースターパック"
            canonical_product_key = code
        identity = (game_id, canonical_product_key)
        if identity in seen:
            continue
        seen.add(identity)
        products.append(
            (
                game_id,
                candidate,
                product_category,
                canonical_product_key,
            )
        )
    return products


def _only_explicitly_excluded_products(
    text: str,
    game_ids: list[str],
    config: Config,
) -> bool:
    has_box = any(additional_matches(config.games[gid], text) for gid in game_ids) or any(
        keyword in text
        for game_id in game_ids
        for keyword in config.games[game_id].box_product_keywords
    )
    has_excluded = any(
        keyword in text
        for game_id in game_ids
        for keyword in config.games[game_id].product_exclude_keywords
    )
    return has_excluded and not has_box


def _recover_product_lines(text: str, article_game_ids: list[str], config: Config) -> str:
    """作品名を誤読した商品行を、見出し＋固有の商品証拠で補う。"""
    lines: list[str] = []
    # 注意書きや購入期間の再掲は新しい商品として拾わない。
    product_text = re.split(r"について|受付方法|応募時の注意", text, maxsplit=1)[0]
    for raw_line in product_text.splitlines():
        line = _normalized(raw_line)
        matches: set[str] = set()
        for game_id, game in config.games.items():
            unique_keywords = [
                keyword for keyword in game.box_product_keywords
                if not any(
                    keyword in other.box_product_keywords
                    for other_id, other in config.games.items() if other_id != game_id
                )
            ]
            if any(re.search(_game_word_pattern(word), line, re.I) for word in unique_keywords):
                matches.add(game_id)
            if any(re.search(pattern, line, re.I) for pattern in game.product_code_patterns):
                matches.add(game_id)
        # 「ブースターパック」「BOX」だけでは作品を決めない。
        # 見出しにも載る1作品に一意に決まる場合だけ補完する。
        if len(matches) == 1 and (game_id := next(iter(matches))) in article_game_ids:
            words = _GAME_WORDS[game_id]
            other_game_named = any(
                re.search(_game_word_pattern(word), line, re.I)
                for other_id, other_words in _GAME_WORDS.items() if other_id != game_id
                for word in other_words
            )
            if not other_game_named and not any(
                re.search(_game_word_pattern(word), line, re.I) for word in words
            ):
                line = f"{words[0]} {line}"
        lines.append(line)
    # 日付解析には元の全文を使う。この戻り値は商品判定専用。
    return "\n".join(lines)


def _anchor_context(anchor: Tag) -> str:
    values = [anchor.get_text(" ", strip=True)]
    for image in anchor.find_all("img"):
        values.extend(
            str(image.get(attribute) or "")
            for attribute in ("alt", "title")
        )
    parent = anchor.parent
    for _ in range(3):
        if not isinstance(parent, Tag) or parent.name in {"main", "body", "html"}:
            break
        parent_text = parent.get_text(" ", strip=True)
        if parent_text and len(parent_text) <= 1_500:
            values.append(parent_text)
            if parent.name in {"article", "li"}:
                break
        parent = parent.parent
    return re.sub(r"\s+", " ", " ".join(values)).strip()


def discover_furuichi_lottery_urls(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    limit: int = 20,
) -> list[str]:
    """Follow supported TCG lottery articles; their BOX names may be images."""

    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        candidate = _clean_url(urljoin(url, str(anchor.get("href") or "")))
        parts = urlsplit(candidate)
        if _host(parts.netloc) != "furu1.net" or not _DETAIL_PATH.fullmatch(
            parts.path
        ):
            continue
        context = _normalized(_anchor_context(anchor))
        if "抽選" not in context:
            continue
        game_ids = _game_ids(context, source)
        if selected_game := additional_game(context, source, config):
            game_ids = list(dict.fromkeys([*game_ids, selected_game]))
        if not game_ids or _only_explicitly_excluded_products(
            context, game_ids, config
        ):
            continue
        if candidate in found:
            continue
        found.append(candidate)
        if len(found) >= limit:
            break
    return found


def furuichi_index_has_target_lottery(
    html: str,
    source: SourceConfig,
    config: Config,
) -> bool:
    """Tell the pipeline when a relevant index entry failed URL discovery."""

    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.find_all("a"):
        if not isinstance(anchor, Tag):
            continue
        context = _normalized(_anchor_context(anchor))
        game_ids = _game_ids(context, source)
        if selected_game := additional_game(context, source, config):
            game_ids = list(dict.fromkeys([*game_ids, selected_game]))
        if (
            game_ids
            and "抽選" in context
            and not _only_explicitly_excluded_products(context, game_ids, config)
        ):
            return True
    return False


def _article_image_urls(soup: BeautifulSoup, article_url: str) -> list[str]:
    urls: list[str] = []
    for image in soup.find_all("img"):
        if not isinstance(image, Tag):
            continue
        for attribute in ("src", "data-src", "data-original"):
            raw = str(image.get(attribute) or "").strip()
            if not raw:
                continue
            candidate = urljoin(article_url, raw)
            parts = urlsplit(candidate)
            if (
                parts.scheme == "https"
                and _host(parts.netloc) == "furu1.net"
                and parts.path.startswith(_IMAGE_PATH_PREFIX)
                and candidate not in urls
            ):
                urls.append(candidate)
    return urls[:4]


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
    if re.match(r"\s*\d{1,2}日", remainder):
        expanded = f"{base_date.year}年{base_date.month}月{remainder.lstrip()}"
        return parse_first_datetime(expanded, base_date).value
    return None


def _labelled_period(
    text: str,
    labels: list[str] | tuple[str, ...],
) -> tuple[datetime | date | None, datetime | date | None]:
    compact = re.sub(r"\s+", "", normalize_text(_normalized(text)))
    for label in sorted({item for item in labels if item}, key=len, reverse=True):
        normalized_label = re.sub(r"\s+", "", normalize_text(_normalized(label)))
        search_from = 0
        while (index := compact.find(normalized_label, search_from)) >= 0:
            scope_start = index + len(normalized_label)
            scope = compact[scope_start : scope_start + 360]
            parsed = parse_period_start(
                scope,
                label_is_start=normalized_label.endswith(("開始", "開始日時")),
            )
            if parsed.value:
                return parsed.value, _range_end(scope, parsed.value)
            search_from = scope_start
    return None, None


def _deadline(text: str, base_date: date) -> datetime | date | None:
    compact = re.sub(r"\s+", "", normalize_text(_normalized(text)))
    for marker in ("受付締切", "応募締切", "受付期限", "応募期限"):
        if (index := compact.find(marker)) >= 0 and (
            parsed := parse_first_datetime(
                compact[index + len(marker) : index + len(marker) + 180],
                base_date,
            ).value
        ):
            return parsed
    for label in _DEFAULT_START_LABELS:
        if (index := compact.find(label)) < 0:
            continue
        scope = compact[index + len(label) : index + len(label) + 360]
        range_match = re.search(r"(?:~|→)(.{1,220})", scope)
        if range_match and (
            parsed := parse_first_datetime(range_match.group(1), base_date).value
        ):
            return parsed
        if "まで" in scope:
            values = list(re.finditer(r"(?:20\d{2}[年/.])?\d{1,2}[月/.]\d{1,2}日?", scope))
            if values:
                candidate = scope[values[-1].start() : scope.find("まで") + 2]
                return parse_first_datetime(candidate, base_date).value
    return None


def _published_date(soup: BeautifulSoup, text: str) -> date | None:
    candidates: list[str] = []
    for selector, attribute in (
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ("time[datetime]", "datetime"),
    ):
        node = soup.select_one(selector)
        if isinstance(node, Tag):
            candidates.append(str(node.get(attribute) or ""))
    candidates.append(text[:1_000])
    for candidate in candidates:
        try:
            iso_value = datetime.fromisoformat(candidate.strip().replace("Z", "+00:00"))
        except ValueError:
            iso_value = None
        if iso_value is not None:
            return iso_value.date()
        parsed = parse_first_datetime(_normalized(candidate)).value
        if isinstance(parsed, datetime):
            return parsed.date()
        if isinstance(parsed, date):
            return parsed
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
        ["抽選", "応募期間", "画像OCR"],
        reason,
        summary,
        None,
        url,
    ).with_fingerprint()


def parse_furuichi_lottery_detail(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    *,
    detected_on: date | None = None,
    ocr_reader: OcrReader | None = None,
    ocr_cache: dict[str, str] | None = None,
    ocr_cache_meta: dict[str, object] | None = None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Parse Furuichi's official image-based BOX lottery announcement."""

    soup = BeautifulSoup(html, "lxml")
    heading = soup.find(["h1", "h2"])
    page_title = _normalized(
        heading.get_text(" ", strip=True)
        if isinstance(heading, Tag)
        else title(html) or source.name
    )
    page_text = _normalized(visible_text(html))
    initial_text = f"{page_title}\n{page_text}"
    article_game_ids = _game_ids(initial_text, source)
    if selected_game := additional_game(initial_text, source, config):
        article_game_ids = list(dict.fromkeys([*article_game_ids, selected_game]))
    if not article_game_ids or "抽選" not in page_title + page_text:
        return [], [], []

    products = _product_candidates(page_title, source, config)

    labels = tuple(source.start_labels) or _DEFAULT_START_LABELS
    start_at, end_at = _labelled_period(page_text, labels)
    extraction_method = "furuichi_official_application_period"
    confidence = "high"
    ocr_text = ""
    images = _article_image_urls(soup, url)

    def invalidate_ocr() -> None:
        # 「文字を取得できた」と「商品・期間を解析できた」は別。
        # 解析失敗の文章を永久に再利用せず、次の監視で画像を読み直す。
        if ocr_cache is not None:
            ocr_cache.pop(url, None)
        if ocr_cache_meta is not None:
            ocr_cache_meta.pop(url, None)

    if images and (not start_at or not products):
        cached_meta = ocr_cache_meta.get(url) if ocr_cache_meta is not None else None
        if isinstance(cached_meta, dict) and cached_meta.get("image_urls") not in (None, images):
            invalidate_ocr()
        if ocr_cache is not None:
            ocr_text = str(ocr_cache.get(url) or "").strip()
        if not ocr_text and ocr_reader is not None:
            try:
                ocr_text = ocr_reader(images).strip()[:12_000]
            except Exception as exc:
                return [], [], [
                    _alert(
                        source,
                        url,
                        page_title,
                        "furuichi_image_ocr_failed",
                        (
                            "ふるいち公式BOX抽選記事の画像OCRに失敗: "
                            f"{type(exc).__name__}: {str(exc)[:160]}"
                        ),
                        article_game_ids[0],
                    )
                ]
            if ocr_text and ocr_cache is not None:
                ocr_cache[url] = ocr_text
        if ocr_text and ocr_cache_meta is not None:
            ocr_cache_meta[url] = {
                "updated_at": datetime.now(UTC).isoformat(),
                "image_urls": images,
            }
        if ocr_text:
            if not start_at:
                start_at, end_at = _labelled_period(ocr_text, labels)
                extraction_method = "furuichi_official_image_application_period"
                confidence = "medium"
            products = _product_candidates(
                f"{page_title}\n{_recover_product_lines(ocr_text, article_game_ids, config)}",
                source, config,
            )

    detected = detected_on or datetime.now(ZoneInfo(config.timezone)).date()
    combined_text = f"{page_text}\n{ocr_text}" if ocr_text else page_text
    if not start_at:
        deadline = _deadline(combined_text, detected)
        deadline_date = (
            deadline.date() if isinstance(deadline, datetime) else deadline
        )
        if deadline and deadline_date and detected <= deadline_date:
            start_at = _published_date(soup, page_text) or detected
            end_at = deadline
            extraction_method = "furuichi_official_open_detected"
            confidence = "low"
        else:
            invalidate_ocr()
            reason = (
                "furuichi_lottery_image_missing"
                if not images
                else "furuichi_application_period_missing"
            )
            summary = (
                "ふるいち公式BOX抽選記事に応募期間画像がありません"
                if not images
                else "ふるいち公式BOX抽選画像から応募開始・締切を解析できません"
            )
            return [], [], [
                _alert(source, url, page_title, reason, summary, article_game_ids[0])
            ]

    if not products:
        invalidate_ocr()
        if _only_explicitly_excluded_products(combined_text, article_game_ids, config):
            return [], [], []
        return [], [], [
            _alert(
                source,
                url,
                page_title,
                "furuichi_box_products_missing",
                "ふるいち公式抽選画像から対象BOXを解析できません",
                article_game_ids[0],
            )
        ]

    cases = [
        LotteryCase(
            game_id,
            "furuichi",
            "古本市場・ふるいち",
            product_name,
            product_category,
            canonical_product_key,
            start_at,
            url,
            url,
            source.source_tier,
            extraction_method,
            confidence,
            end_at=end_at,
        ).with_id()
        for game_id, product_name, product_category, canonical_product_key in products
    ]
    # 混載告知で1作品だけ成功しても、他の作品の失敗を隠さない。
    parsed_games = {case.game_id for case in cases}
    missing_games = [
        game_id for game_id in article_game_ids
        if game_id not in parsed_games
        and not _only_explicitly_excluded_products(combined_text, [game_id], config)
    ]
    alerts = []
    if missing_games:
        invalidate_ocr()
        alerts = [
            _alert(
                source, url, page_title, "furuichi_box_products_missing",
                f"ふるいち公式抽選画像から{config.games[game_id].name}の商品を解析できません",
                game_id,
            )
            for game_id in missing_games
        ]
    return cases, [], alerts


__all__ = [
    "FURUICHI_SOURCE",
    "discover_furuichi_lottery_urls",
    "furuichi_index_has_target_lottery",
    "is_furuichi_news_index",
    "is_furuichi_source",
    "parse_furuichi_lottery_detail",
]
