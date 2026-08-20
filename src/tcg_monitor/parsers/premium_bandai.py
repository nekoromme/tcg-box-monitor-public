from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig

_HEADINGS = {"h2", "h3", "h4", "h5", "h6"}


def _premium_bandai_section(soup: BeautifulSoup) -> tuple[str, list[Tag], list[str]] | None:
    for heading in soup.find_all(list(_HEADINGS)):
        if "プレミアムバンダイ" not in heading.get_text(" ", strip=True):
            continue
        level = int(heading.name[1])
        text_parts: list[str] = []
        tags: list[Tag] = []
        links: list[str] = []
        for node in heading.next_elements:
            if node is heading:
                continue
            if isinstance(node, Tag) and node.name in _HEADINGS and int(node.name[1]) <= level:
                break
            if isinstance(node, Tag):
                if node.name in {"li", "p", "tr"}:
                    tags.append(node)
                if node.name == "a" and node.get("href"):
                    links.append(str(node.get("href")))
            elif isinstance(node, NavigableString) and node.strip():
                text_parts.append(str(node).strip())
        return " ".join(text_parts), tags, links
    return None


def _products(
    tags: list[Tag], section_text: str, source_url: str, config: Config
) -> list[tuple[str, str, str]]:
    game = config.games["one_piece_card"]
    candidates: list[str] = []
    for tag in tags:
        value = re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()
        if value and value not in candidates:
            candidates.append(value)
    if not candidates:
        candidates = [section_text]

    products: dict[str, tuple[str, str, str]] = {}
    for value in candidates:
        if not any(word in value for word in game.include_keywords):
            continue
        has_box_code = bool(re.search(r"\b(?:OP|EB|PRB)-\d{2}\b", value, re.I))
        classified = classify_product(
            game,
            value,
            value + (" 1BOX" if has_box_code else ""),
            source_url,
        )
        if not classified.is_box:
            continue
        products[classified.canonical_product_key] = (
            value[:180],
            next((word for word in game.box_product_keywords if word in value), "BOX"),
            classified.canonical_product_key,
        )
    return list(products.values())


def parse_nyuka_now_premium_bandai(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Read the Premium Bandai block that also lists lotteries of older BOXes."""
    soup = BeautifulSoup(html, "lxml")
    section = _premium_bandai_section(soup)
    if not section:
        alert = Alert(
            "one_piece_card",
            source.id,
            url,
            source.name,
            ["プレミアムバンダイ"],
            "premium_bandai_section_missing",
            "プレミアムバンダイの抽選欄が見つかりません",
            None,
            url,
        ).with_fingerprint()
        return [], [], [alert]

    section_text, tags, links = section
    start_match = re.search(r"開始日\s*[：:]?\s*(.{0,100})", section_text)
    parsed = parse_first_datetime(start_match.group(1)) if start_match else None
    start_at: date | datetime | None = parsed.value if parsed else None
    products = _products(tags, section_text, url, config)
    alerts: list[Alert] = []
    if not start_at:
        alerts.append(
            Alert(
                "one_piece_card",
                source.id,
                url,
                source.name,
                ["開始日"],
                "premium_bandai_start_missing",
                "プレミアムバンダイ抽選の開始日時を解析できません",
                None,
                url,
            ).with_fingerprint()
        )
    if not products:
        alerts.append(
            Alert(
                "one_piece_card",
                source.id,
                url,
                source.name,
                ["BOX"],
                "premium_bandai_products_missing",
                "プレミアムバンダイ抽選の対象BOXを解析できません",
                None,
                url,
            ).with_fingerprint()
        )
    if not start_at or not products:
        return [], [], alerts

    official_url = next(
        (urljoin(url, link) for link in links if "p-bandai.jp/" in link),
        url,
    )
    cases = [
        LotteryCase(
            "one_piece_card",
            "premium_bandai",
            "プレミアムバンダイ",
            product_name,
            product_category,
            product_key,
            start_at,
            official_url,
            url,
            source.source_tier,
            "nyuka_now_premium_bandai_start",
            "medium",
        ).with_id()
        for product_name, product_category, product_key in products
    ]
    return cases, [], alerts


def _fullcomp_sections(
    soup: BeautifulSoup,
) -> list[tuple[str, list[Tag], list[str]]]:
    sections: list[tuple[str, list[Tag], list[str]]] = []
    for heading in soup.find_all(list(_HEADINGS)):
        if "フルコンプ" not in heading.get_text(" ", strip=True):
            continue
        level = int(heading.name[1])
        text_parts: list[str] = []
        tags: list[Tag] = []
        links: list[str] = []
        for node in heading.next_elements:
            if node is heading:
                continue
            if isinstance(node, Tag) and node.name in _HEADINGS and int(node.name[1]) <= level:
                break
            if isinstance(node, Tag):
                if node.name in {"li", "p", "tr"}:
                    tags.append(node)
                if node.name == "a" and node.get("href"):
                    links.append(str(node.get("href")))
            elif isinstance(node, NavigableString) and node.strip():
                text_parts.append(str(node).strip())
        sections.append((" ".join(text_parts), tags, links))
    return sections


def _fullcomp_product_candidates(tags: list[Tag]) -> list[str]:
    candidates: list[str] = []
    for tag in tags:
        if tag.name != "tr":
            continue
        heading = tag.find("th")
        value = tag.find("td")
        if not heading or not value or "対象商品" not in heading.get_text(" ", strip=True):
            continue
        items = value.find_all("li")
        raw_values = (
            [item.get_text(" ", strip=True) for item in items]
            if items
            else [value.get_text(" ", strip=True)]
        )
        for raw in raw_values:
            cleaned = re.sub(r"\s+", " ", raw).strip()
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
    return candidates


def _supported_game_id(text: str, source: SourceConfig) -> str | None:
    folded = text.casefold()
    if any(
        marker.casefold() in folded
        for marker in (
            "ONE PIECEカード",
            "ONEPIECEカード",
            "ワンピースカード",
            "ワンピカード",
        )
    ) and source.supports("one_piece_card"):
        return "one_piece_card"
    if any(
        marker in text
        for marker in (
            "ドラゴンボールスーパーカードゲーム",
            "フュージョンワールド",
            "DBFW",
        )
    ) and source.supports("dragon_ball_fusion_world"):
        return "dragon_ball_fusion_world"
    if any(marker in text for marker in ("ポケモンカード", "ポケカ")) and source.supports(
        "pokemon_card"
    ):
        return "pokemon_card"
    return None


def parse_nyuka_now_fullcomp(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Parse Fullcomp blocks whose application URL is an official LivePocket event."""
    soup = BeautifulSoup(html, "lxml")
    cases: list[LotteryCase] = []
    alerts: list[Alert] = []
    for section_text, tags, links in _fullcomp_sections(soup):
        official_url = next(
            (
                urljoin(url, link)
                for link in links
                if re.fullmatch(
                    r"https://(?:t\.)?livepocket\.jp/e/[A-Za-z0-9_-]+",
                    urljoin(url, link),
                )
            ),
            None,
        )
        if not official_url:
            continue
        candidates = _fullcomp_product_candidates(tags)
        start_match = re.search(r"開始日\s*[：:]?\s*(.{0,100})", section_text)
        parsed = parse_first_datetime(start_match.group(1)) if start_match else None
        start_at: date | datetime | None = parsed.value if parsed else None
        if not start_at:
            alerts.append(
                Alert(
                    None,
                    source.id,
                    official_url,
                    source.name,
                    ["開始日"],
                    "fullcomp_application_start_missing",
                    "フルコンプLivePocket抽選欄の開始日時を解析できません",
                    None,
                    official_url,
                ).with_fingerprint()
            )
            continue

        parsed_products = 0
        for candidate in candidates:
            game_id = _supported_game_id(candidate, source)
            if not game_id:
                continue
            game = config.games[game_id]
            if any(word in candidate for word in game.product_exclude_keywords):
                continue
            classified = classify_product(game, candidate, f"{candidate} 1BOX")
            if not classified.is_box:
                continue
            parsed_products += 1
            category = next(
                (word for word in game.box_product_keywords if word in candidate),
                "BOX",
            )
            cases.append(
                LotteryCase(
                    game_id,
                    "fullcomp",
                    "フルコンプ",
                    candidate[:180],
                    category,
                    classified.canonical_product_key,
                    start_at,
                    official_url,
                    url,
                    source.source_tier,
                    "nyuka_now_fullcomp_application_start",
                    "medium",
                ).with_id()
            )
        all_excluded = candidates and all(
            any(
                word in candidate
                for game_id in source.parse_game_ids
                for word in config.games[game_id].product_exclude_keywords
            )
            for candidate in candidates
        )
        if candidates and not parsed_products and not all_excluded:
            alerts.append(
                Alert(
                    None,
                    source.id,
                    official_url,
                    source.name,
                    ["対象商品"],
                    "fullcomp_products_missing",
                    "フルコンプLivePocket抽選欄の対象BOXを解析できません",
                    None,
                    official_url,
                ).with_fingerprint()
            )
    return cases, [], alerts


_CURRENT_LOTTERY_SCOPE_MARKERS = (
    "抽選・予約応募受付中",
    "近日受付開始予定",
)
_PRIORITY_RETAILERS = (
    (
        "シーガル",
        "seagull_sendai",
        "シーガル各店",
        "https://seagull.membercard.jp/lottery",
        "seagull.membercard.jp",
        "pokemon_card",
        "https://nyuka-now.com/archives/2459",
    ),
    (
        "エディオン・トレカキャピタル",
        "edion_online",
        "エディオン",
        "https://www.edion.com/",
        "edion-cp.com",
        "pokemon_card",
        "https://nyuka-now.com/archives/2459",
    ),
    (
        "DMM通販",
        "dmm_tsuhan",
        "DMM通販",
        "https://www.dmm.com/mono/hobby/-/list/=/article=keyword/id=308378/",
        "dmm.com",
        "one_piece_card",
        "https://nyuka-now.com/archives/97393",
    ),
)


def _priority_retailer_sections(
    soup: BeautifulSoup,
    url: str,
) -> list[tuple[str, str, str, str, str, list[Tag], list[str]]]:
    """Read only active/upcoming retailer blocks from the matching summary."""

    sections: list[
        tuple[str, str, str, str, str, list[Tag], list[str]]
    ] = []
    for heading in soup.find_all(list(_HEADINGS)):
        heading_text = heading.get_text(" ", strip=True)
        spec = next(
            (
                item
                for item in _PRIORITY_RETAILERS
                if item[0] in heading_text
                and url.rstrip("/") == item[6].rstrip("/")
            ),
            None,
        )
        if not spec:
            continue

        scope = heading.find_previous("h2")
        scope_text = scope.get_text(" ", strip=True) if isinstance(scope, Tag) else ""
        if not any(marker in scope_text for marker in _CURRENT_LOTTERY_SCOPE_MARKERS):
            continue

        level = int(heading.name[1])
        text_parts: list[str] = []
        tags: list[Tag] = []
        links: list[str] = []
        for node in heading.next_elements:
            if node is heading:
                continue
            if isinstance(node, Tag) and node.name in _HEADINGS and int(node.name[1]) <= level:
                break
            if isinstance(node, Tag):
                if node.name in {"li", "p", "tr"}:
                    tags.append(node)
                if node.name == "a" and node.get("href"):
                    links.append(urljoin("https://nyuka-now.com/", str(node.get("href"))))
            elif isinstance(node, NavigableString) and node.strip():
                text_parts.append(str(node).strip())

        (
            _,
            retailer_id,
            retailer_name,
            fallback_url,
            official_host,
            game_id,
            _summary_url,
        ) = spec
        official_url = next(
            (link for link in links if official_host in link),
            fallback_url,
        )
        sections.append(
            (
                game_id,
                retailer_id,
                retailer_name,
                official_url,
                " ".join(text_parts),
                tags,
                links,
            )
        )
    return sections


def _parse_nyuka_now_priority_retailers(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Recover retailer campaigns whose official index is login-only or unstable."""

    soup = BeautifulSoup(html, "lxml")
    cases: list[LotteryCase] = []
    alerts: list[Alert] = []
    for (
        game_id,
        retailer_id,
        retailer_name,
        official_url,
        section_text,
        tags,
        _,
    ) in _priority_retailer_sections(soup, url):
        game = config.games[game_id]
        candidates = _fullcomp_product_candidates(tags)
        start_match = re.search(r"開始日\s*[：:]?\s*(.{0,100})", section_text)
        parsed = parse_first_datetime(start_match.group(1)) if start_match else None
        start_at: date | datetime | None = parsed.value if parsed else None
        if not start_at:
            alerts.append(
                Alert(
                    game_id,
                    source.id,
                    official_url,
                    source.name,
                    ["開始日"],
                    "priority_retailer_start_missing",
                    f"{retailer_name}の抽選開始日時を解析できません",
                    None,
                    official_url,
                ).with_fingerprint()
            )
            continue

        parsed_products = 0
        for candidate in candidates:
            if not any(word in candidate for word in game.include_keywords):
                continue
            if any(word in candidate for word in game.product_exclude_keywords):
                continue
            # The campaign URL is shared by several products. Supplying it to
            # the classifier would collapse every product into its URL slug.
            classified = classify_product(
                game,
                candidate,
                f"{candidate} 1BOX",
            )
            if not classified.is_box:
                continue
            parsed_products += 1
            category = next(
                (word for word in game.box_product_keywords if word in candidate),
                "BOX",
            )
            cases.append(
                LotteryCase(
                    game_id,
                    retailer_id,
                    retailer_name,
                    candidate[:180],
                    category,
                    classified.canonical_product_key,
                    start_at,
                    official_url,
                    url,
                    source.source_tier,
                    "nyuka_now_priority_retailer_application_start",
                    "medium",
                ).with_id()
            )

        all_excluded = candidates and all(
            any(word in candidate for word in game.product_exclude_keywords)
            for candidate in candidates
        )
        if candidates and not parsed_products and not all_excluded:
            alerts.append(
                Alert(
                    game_id,
                    source.id,
                    official_url,
                    source.name,
                    ["対象商品"],
                    "priority_retailer_products_missing",
                    f"{retailer_name}の対象BOXを解析できません",
                    None,
                    official_url,
                ).with_fingerprint()
            )
    return cases, [], alerts


def parse_nyuka_now_lottery_summary(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Combine Fullcomp fallback with priority retailer recovery in one fetch."""

    fullcomp_cases, fullcomp_releases, fullcomp_alerts = parse_nyuka_now_fullcomp(
        html, url, source, config
    )
    priority_cases, priority_releases, priority_alerts = (
        _parse_nyuka_now_priority_retailers(html, url, source, config)
    )
    return (
        [*fullcomp_cases, *priority_cases],
        [*fullcomp_releases, *priority_releases],
        [*fullcomp_alerts, *priority_alerts],
    )


__all__ = [
    "parse_nyuka_now_fullcomp",
    "parse_nyuka_now_lottery_summary",
    "parse_nyuka_now_premium_bandai",
]
