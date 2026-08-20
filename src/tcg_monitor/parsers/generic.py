from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import parse_first_datetime, parse_period_start
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig
from tcg_monitor.parsers.common import title, visible_text

RETAILERS = {
    "geo": "ゲオ",
    "pokemon_center_online": "ポケモンセンターオンライン",
    "rakuten_books": "楽天ブックス",
    "yodobashi": "ヨドバシカメラ",
    "kids_republic": "キッズリパブリック",
    "aeon_style_online": "イオンスタイルオンライン",
    "premium_bandai": "プレミアムバンダイ",
}
_GEO_NEWS_DETAIL = re.compile(r"^https://geo-online\.co\.jp/news/\d+/?$")
_ONEPIECE_TOPICS_SOURCES = {"onepiece_official_topics", "premium_bandai_onepiece"}
_ONEPIECE_LOTTERY_START_MARKERS = (
    "抽選販売の受付を開始",
    "抽選販売を開始",
    "抽選販売の受注受付を開始",
    "抽選販売を実施",
)


def is_geo_news_index(source_id: str, url: str) -> bool:
    return source_id == "geo" and url.rstrip("/") == "https://geo-online.co.jp/news"


def discover_geo_news_urls(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    limit: int = 20,
) -> list[str]:
    """Follow relevant GEO index links so dates are parsed from the full article."""

    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        candidate = urljoin(url, str(anchor.get("href")))
        if not _GEO_NEWS_DETAIL.fullmatch(candidate) or candidate in seen:
            continue
        anchor_text = anchor.get_text(" ", strip=True)
        supported_games = [
            config.games[game_id]
            for game_id in source.supported_games
            if game_id in config.games and source.supports(game_id)
        ]
        has_game = any(
            keyword in anchor_text
            for game in supported_games
            for keyword in game.include_keywords
        )
        has_box = any(
            keyword in anchor_text
            for game in supported_games
            for keyword in game.box_product_keywords
        ) or bool(re.search(r"(?i)\b1?BOX\b", anchor_text))
        has_lottery = any(
            keyword in anchor_text
            for keyword in config.common_terms.get("lottery_keywords", [])
        )
        if not (has_game and has_box and has_lottery):
            continue
        seen.add(candidate)
        found.append(candidate)
        if len(found) >= limit:
            break
    return found


def _blocks(html: str) -> list[str]:
    chunks = re.split(r"</(?:article|section|li|tr|div)>", html, flags=re.I)
    values = [visible_text(chunk) for chunk in chunks if len(visible_text(chunk)) > 15]
    return values[:80] or [visible_text(html)]


def _page_blocks(html: str, url: str, source: SourceConfig) -> list[str]:
    """Keep structured article bodies together so products and periods stay paired."""

    keep_article_together = (
        source.id == "geo" and bool(_GEO_NEWS_DETAIL.fullmatch(url))
    ) or source.id == "dragonball_official_store"
    if not keep_article_together:
        return _blocks(html)
    soup = BeautifulSoup(html, "lxml")
    for selector in ("main article", "main", "article"):
        node = soup.select_one(selector)
        if not isinstance(node, Tag):
            continue
        article_text = visible_text(str(node))
        if len(article_text) > 15:
            return [article_text]
    return _blocks(html)


def _lottery_start(
    block: str, source: SourceConfig, config: Config
) -> datetime | date | None:
    """Parse a date only when it is explicitly attached to an application-start label.

    Retailer article titles commonly put the product release date before words such as
    "抽選販売". Treating the first date in the whole block as the application start creates
    a plausible-looking but incorrect Calendar event. Source-specific labels are preferred,
    with common labels kept as a fallback for sources whose configuration is sparse.
    """

    labels = sorted(
        {
            str(label).strip()
            for label in (
                *source.start_labels,
                *config.common_terms.get("start_labels", []),
            )
            if str(label).strip()
        },
        key=len,
        reverse=True,
    )
    negative_labels = [
        str(label)
        for label in config.common_terms.get("negative_date_labels", [])
        if str(label)
    ]

    for label in labels:
        search_from = 0
        while (label_index := block.find(label, search_from)) >= 0:
            scope_start = label_index + len(label)
            scope = block[scope_start : scope_start + 240]

            # Do not cross into an explicitly different date field. For example,
            # "応募受付期間は後日案内。発売日 8月22日" has no published start date.
            boundaries = [scope.find(item) for item in negative_labels]
            boundaries = [position for position in boundaries if position >= 0]
            if boundaries:
                scope = scope[: min(boundaries)]

            parsed = parse_period_start(
                scope,
                label_is_start=label.endswith(("開始", "開始日時")),
            )
            if parsed.value:
                return parsed.value
            search_from = scope_start
    return None


def parse_onepiece_topics(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Parse only explicit Premium Bandai lottery-start entries from the TOPICS index.

    The index contains years of historical posts. Treating its whole body as one lottery
    article turns unrelated publication dates into starts and creates a permanent alert.
    Each matching entry is therefore scoped to its own link and must explicitly say that
    lottery sales started.
    """
    soup = BeautifulSoup(html, "lxml")
    game = config.games["one_piece_card"]
    cases_by_id: dict[str, LotteryCase] = {}
    alerts: list[Alert] = []
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        entry = anchor.get_text(" ", strip=True)
        if "抽選販売" not in entry or not any(
            marker in entry for marker in _ONEPIECE_LOTTERY_START_MARKERS
        ):
            continue
        classified = classify_product(game, entry[:120], entry, url)
        if not classified.is_box:
            continue
        parsed = parse_first_datetime(entry)
        official_url = urljoin(url, str(anchor.get("href")))
        if not parsed.value:
            alerts.append(
                Alert(
                    "one_piece_card",
                    source.id,
                    official_url,
                    entry[:160] or source.name,
                    ["抽選販売", "受付開始"],
                    "lottery_text_without_start",
                    "受付開始を明記した個別項目の日付を解析できません",
                    None,
                    official_url,
                ).with_fingerprint()
            )
            continue
        case = LotteryCase(
            "one_piece_card",
            "premium_bandai",
            "プレミアムバンダイ",
            classified.product_name,
            classified.product_category,
            classified.canonical_product_key,
            parsed.value,
            official_url,
            url,
            source.source_tier,
            "onepiece_topics_explicit_lottery_start",
            "high",
        ).with_id()
        cases_by_id[case.case_id] = case
    return list(cases_by_id.values()), [], alerts


def parse_generic(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    text = visible_text(html)
    releases: list[Release] = []
    cases: list[LotteryCase] = []
    alerts: list[Alert] = []
    pending_missing_start: list[tuple[str, Alert]] = []
    successful_lottery_games: set[str] = set()
    page_title = title(html) or source.name
    if not text:
        return (
            [],
            [],
            [
                Alert(
                    None, source.id, url, page_title, [], "empty_body", "本文が空です", None, url
                ).with_fingerprint()
            ],
        )
    supported_game_count = sum(source.supports(game_id) for game_id in config.games)
    for game_id, game in config.games.items():
        if not source.supports(game_id):
            continue
        has_game_identity = any(keyword in text for keyword in game.include_keywords) or any(
            re.search(pattern, text, re.I) for pattern in game.product_code_patterns
        )
        has_box_keyword = any(keyword in text for keyword in game.box_product_keywords)
        if not has_game_identity and (supported_game_count > 1 or not has_box_keyword):
            continue
        for block in _page_blocks(html, url, source):
            classified = classify_product(
                game, page_title if len(block) > 400 else block[:80], block, url
            )
            if not classified.is_box:
                continue
            parsed = parse_first_datetime(block)
            if "release_discovery" in source.purposes or source.id.endswith("products"):
                release_date: date | None = None
                if isinstance(parsed.value, datetime):
                    release_date = parsed.value.date()
                elif isinstance(parsed.value, date):
                    release_date = parsed.value
                if release_date or parsed.month_only:
                    releases.append(
                        Release(
                            game_id,
                            classified.product_name,
                            classified.product_category,
                            classified.canonical_product_key,
                            release_date,
                            parsed.month_only,
                            url,
                            url,
                            source.source_tier,
                            "generic_release" if release_date else "generic_release_month",
                            "high" if release_date else "medium",
                        ).with_id()
                    )
            if any(keyword in block for keyword in config.common_terms.get("lottery_keywords", [])):
                start_at = _lottery_start(block, source, config)
                if start_at:
                    case = LotteryCase(
                        game_id,
                        source.id,
                        RETAILERS.get(source.id, source.name),
                        classified.product_name,
                        classified.product_category,
                        classified.canonical_product_key,
                        start_at,
                        url,
                        url,
                        source.source_tier,
                        "generic_lottery_label",
                        "high" if source.source_tier.value.startswith("official") else "medium",
                    ).with_id()
                    cases.append(case)
                    successful_lottery_games.add(game_id)
                else:
                    pending_missing_start.append(
                        (
                            game_id,
                            Alert(
                                game_id,
                                source.id,
                                url,
                                page_title,
                                ["抽選", "応募"],
                                "lottery_text_without_start",
                                "抽選語はあるが開始日時を一意に抽出できません",
                                None,
                                url,
                            ).with_fingerprint(),
                        )
                    )
    alerts.extend(
        alert
        for game_id, alert in pending_missing_start
        if game_id not in successful_lottery_games
    )
    return cases, releases, alerts
