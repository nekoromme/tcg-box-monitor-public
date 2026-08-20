from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, date, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

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
)
_GAME_WORDS = {
    "pokemon_card": ("ポケモンカードゲーム", "ポケモンカード", "ポケカ"),
    "one_piece_card": (
        "ONE PIECEカードゲーム",
        "ONE PIECEカード",
        "ワンピースカード",
        "ワンピカード",
    ),
}

OcrReader = Callable[[list[str]], str]


def _host(value: str) -> str:
    return value.casefold().removeprefix("www.")


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


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
            re.sub(r"\s+", "", word).casefold() in compact for word in words
        ):
            return game_id
    return None


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
    """Follow only supported TCG BOX lottery articles from Furuichi news."""

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
        game_id = _game_id(context, source)
        if not game_id:
            continue
        classified = classify_product(
            config.games[game_id],
            context,
            context,
            candidate,
        )
        if not classified.is_box or candidate in found:
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
        game_id = _game_id(context, source)
        if (
            game_id
            and "抽選" in context
            and classify_product(
                config.games[game_id],
                context,
                context,
            ).is_box
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
    game_id = _game_id(f"{page_title}\n{page_text}", source)
    if not game_id or "抽選" not in page_title + page_text:
        return [], [], []

    product_name = re.sub(
        r"(?:の)?抽選(?:販売)?受付について.*$",
        "",
        page_title,
    ).strip(" |｜")
    classified = classify_product(
        config.games[game_id],
        product_name,
        page_text,
        url,
    )
    if not classified.is_box:
        return [], [], []

    labels = tuple(source.start_labels) or _DEFAULT_START_LABELS
    start_at, end_at = _labelled_period(page_text, labels)
    extraction_method = "furuichi_official_application_period"
    confidence = "high"
    ocr_text = ""
    images = _article_image_urls(soup, url)
    if not start_at and images:
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
                        game_id,
                    )
                ]
            if ocr_text and ocr_cache is not None:
                ocr_cache[url] = ocr_text
        if ocr_text and ocr_cache_meta is not None:
            ocr_cache_meta[url] = {"updated_at": datetime.now(UTC).isoformat()}
        if ocr_text:
            start_at, end_at = _labelled_period(ocr_text, labels)
            extraction_method = "furuichi_official_image_application_period"
            confidence = "medium"

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
                _alert(source, url, page_title, reason, summary, game_id)
            ]

    case = LotteryCase(
        game_id,
        "furuichi",
        "古本市場・ふるいち",
        product_name,
        classified.product_category,
        classified.canonical_product_key,
        start_at,
        url,
        url,
        source.source_tier,
        extraction_method,
        confidence,
        end_at=end_at,
    ).with_id()
    return [case], [], []


__all__ = [
    "FURUICHI_SOURCE",
    "discover_furuichi_lottery_urls",
    "furuichi_index_has_target_lottery",
    "is_furuichi_news_index",
    "is_furuichi_source",
    "parse_furuichi_lottery_detail",
]
