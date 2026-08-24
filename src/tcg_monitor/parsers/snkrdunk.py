from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from tcg_monitor.classifier import classify_product
from tcg_monitor.config import source_with_runtime_parser_profile
from tcg_monitor.japanese_datetime import parse_first_datetime, parse_period_start
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig

_HEADINGS = {"h2", "h3", "h4", "h5", "h6"}
_START_LABEL = re.compile(
    r"(?:予約[・/]?)?(?:抽選販売)?(?:応募|抽選)?(?:受付|受け付け)?期間"
    r"|抽選受付|応募受付|受付開始"
)
_RANGE_MARKER = re.compile(r"[~〜～]|から")
_CATEGORIES = {
    "pokemon_card": ("強化拡張パック", "ハイクラスパック", "再拡張パック", "拡張パック"),
    "one_piece_card": ("エクストラブースター", "プレミアムブースター", "ブースターパック"),
}


def is_snkrdunk_schedule_page(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find("h1")
    return bool(heading and "発売スケジュール" in heading.get_text(" ", strip=True))


def _schedule_article_text_is_relevant(source: SourceConfig, anchor_text: str) -> bool:
    game_terms = (
        ("ポケカ", "ポケモンカード")
        if source.id == "snkrdunk_pokemon"
        else ("ワンピースカード", "ワンピカード")
    )
    if not any(term in anchor_text for term in game_terms):
        return False
    excluded = ("スターター", "デッキ", "相場", "当たり")
    if any(term in anchor_text for term in excluded):
        return False
    is_lottery_article = "抽選" in anchor_text and "予約" in anchor_text
    is_pokemon_resale_article = (
        source.id == "snkrdunk_pokemon"
        and "再販はいつ" in anchor_text
        and "再販入荷情報" in anchor_text
    )
    return is_lottery_article or is_pokemon_resale_article


def _canonical_snkrdunk_article_url(url: str, href: str) -> str | None:
    candidate = urljoin(url, href)
    parsed = urlparse(candidate)
    if parsed.netloc.casefold().removeprefix("www.") != "snkrdunk.com":
        return None
    match = re.fullmatch(r"/articles/(\d+)/?", parsed.path)
    if not match:
        return None
    # The site adds presentation-only parameters such as ?slide=right.  They
    # must not create a second identity or make a valid article undiscoverable.
    return f"https://snkrdunk.com/articles/{match.group(1)}/"


def discover_snkrdunk_article_urls(
    html: str, url: str, source: SourceConfig, limit: int = 3
) -> list[str]:
    """Find the newest relevant per-product articles from the evergreen schedule."""
    soup = BeautifulSoup(html, "lxml")
    found: dict[int, str] = {}
    for anchor in soup.find_all("a", href=True):
        anchor_text = anchor.get_text(" ", strip=True)
        if not _schedule_article_text_is_relevant(source, anchor_text):
            continue
        candidate = _canonical_snkrdunk_article_url(url, str(anchor.get("href")))
        if candidate is None:
            continue
        match = re.search(r"/articles/(\d+)/$", candidate)
        if match:
            found[int(match.group(1))] = candidate
    return [found[key] for key in sorted(found, reverse=True)[:limit]]


def is_snkrdunk_schedule_healthy_without_candidates(
    html: str,
    source: SourceConfig,
) -> bool:
    """Distinguish an idle schedule from a schedule whose markup became unreadable."""

    soup = BeautifulSoup(html, "lxml")
    categories = _CATEGORIES[
        "pokemon_card" if source.id == "snkrdunk_pokemon" else "one_piece_card"
    ]
    has_product_section = any(
        isinstance(heading, Tag)
        and heading.name in _HEADINGS
        and any(category in heading.get_text(" ", strip=True) for category in categories)
        for heading in soup.find_all(_HEADINGS)
    )
    if not has_product_section:
        return False

    # If a reservation/lottery title is visible but its URL cannot be parsed,
    # that is a real markup change and must remain an alert.
    return not any(
        _schedule_article_text_is_relevant(source, anchor.get_text(" ", strip=True))
        for anchor in soup.find_all("a", href=True)
    )


def _retailer(value: str, source: SourceConfig) -> tuple[str, str] | None:
    source = source_with_runtime_parser_profile(source)
    folded = value.casefold()
    profiles = source.parser_options.get("retailers", [])
    if not isinstance(profiles, list):
        raise ValueError(f"bad retailer profiles: {source.id}")
    for raw in profiles:
        if not isinstance(raw, dict):
            raise ValueError(f"bad retailer profile: {source.id}")
        retailer_id = raw.get("retailer_id")
        retailer_name = raw.get("retailer_name")
        aliases = raw.get("aliases")
        if not (
            isinstance(retailer_id, str)
            and isinstance(retailer_name, str)
            and isinstance(aliases, list)
            and all(isinstance(alias, str) and alias for alias in aliases)
        ):
            raise ValueError(f"bad retailer profile: {source.id}")
        if any(alias.casefold() in folded for alias in aliases):
            return retailer_id, retailer_name
    return None


def _section(heading: Tag) -> tuple[str, list[str]]:
    level = int(heading.name[1])
    text_parts: list[str] = [heading.get_text(" ", strip=True)]
    links: list[str] = []
    for node in heading.next_elements:
        if node is heading:
            continue
        if isinstance(node, Tag) and node.name in _HEADINGS and int(node.name[1]) <= level:
            break
        if isinstance(node, Tag) and node.name == "a" and node.get("href"):
            links.append(str(node.get("href")))
        if isinstance(node, NavigableString) and node.strip():
            text_parts.append(str(node).strip())
    return " ".join(text_parts), links


def _official_link(links: list[str], fallback: str) -> str:
    for link in links:
        parsed = urlparse(link)
        if parsed.scheme in {"http", "https"} and "snkrdunk.com" not in parsed.netloc:
            return link
    return fallback


def _article_game(source: SourceConfig) -> str:
    return "pokemon_card" if source.id == "snkrdunk_pokemon" else "one_piece_card"


def _heading_product_title(heading_text: str) -> str:
    """Read the product title from a per-product lottery or resale heading."""

    without_game_prefix = re.sub(
        r"^[【〖\[].*?[】〗\]]\s*",
        "",
        heading_text,
        count=1,
    )
    for pattern in (
        r"(?P<title>.+?)の予約(?:[・／/]|や)抽選情報",
        r"(?P<title>.+?)の再販はいつ",
    ):
        if match := re.search(pattern, without_game_prefix):
            return match.group("title").strip()
    return ""


def _product(html: str, game_id: str, config: Config) -> tuple[str, str, str] | None:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find("h1")
    heading_text = heading.get_text(" ", strip=True) if heading else ""
    all_text = soup.get_text(" ", strip=True)
    categories = sorted(_CATEGORIES[game_id], key=len, reverse=True)
    category = next((value for value in categories if value in heading_text), "")

    # The page footer contains unrelated article cards.  Previously the first
    # BOX category found anywhere on the page was combined with the longest
    # quoted phrase near the article, which could invent a product such as
    # "ハイクラスパック『ポケットモンスター ルビー・サファイア』".
    # A per-product article already names the product in h1, so bind the
    # category only to that exact title in the article body/product table.
    product_title = _heading_product_title(heading_text)
    if product_title:
        title_variants = [product_title]
        if alias := re.fullmatch(r"(?P<main>.+?)[(（](?P<alias>[^)）]+)[)）]", product_title):
            title_variants.extend(
                value.strip()
                for value in (alias.group("main"), alias.group("alias"))
                if value.strip()
            )
        categories_pattern = "|".join(map(re.escape, categories))
        for title_variant in dict.fromkeys(title_variants):
            flexible_title = r"\s*".join(
                re.escape(part) for part in re.split(r"\s+", title_variant) if part
            )
            exact_product = re.search(
                rf"(?P<category>{categories_pattern})\s*"
                rf"[「『\"“]?\s*{flexible_title}\s*[」』\"”]?",
                all_text,
                re.IGNORECASE,
            )
            if not exact_product:
                continue
            category = exact_product.group("category")
            product_name = f"{category}「{title_variant}」"
            classified = classify_product(config.games[game_id], product_name, product_name)
            if classified.is_box:
                return (
                    product_name,
                    category,
                    classified.canonical_product_key,
                )
        # A titled per-product article that cannot bind its own title to a BOX
        # category is a structure change. Never fall back to unrelated quotes
        # or article cards elsewhere on the page.
        return None

    if not category:
        category = next((value for value in categories if value in all_text), "")
    if not category:
        return None

    # SNKRDUNK's h1 is usually "商品名の予約・抽選情報" and omits the
    # category.  Breadcrumbs and the first paragraph contain the full
    # "拡張パック「商品名」" form, so inspect both regions.
    nearby = f"{heading_text} {all_text[:1200]}"
    match = re.search(
        rf"{re.escape(category)}[^「『\"“]{{0,30}}[「『\"“]([^」』\"”]{{2,80}})[」』\"”]",
        nearby,
    )
    if not match:
        candidates = re.findall(r"[「『\"“]([^」』\"”]{2,80})[」』\"”]", nearby)
        candidates = [
            item
            for item in candidates
            if not any(
                word in item for word in ("ポケモンカード", "ワンピースカード", "抽選", "予約")
            )
        ]
        product_title = max(candidates, key=len) if candidates else ""
    else:
        product_title = match.group(1).strip()
    if not product_title:
        return None

    product_name = f"{category}「{product_title}」"
    classified = classify_product(config.games[game_id], product_name, product_name)
    if not classified.is_box:
        return None
    return product_name, category, classified.canonical_product_key


def _date_from_text(value: str) -> date | None:
    parsed = parse_first_datetime(value)
    if isinstance(parsed.value, datetime):
        return parsed.value.date()
    if isinstance(parsed.value, date):
        return parsed.value
    return None


def _release_date(soup: BeautifulSoup) -> date | None:
    """Read an actual product release date, never an article update or TOC date."""
    # Prefer an explicit ``発売日`` label.  SNKRDUNK currently separates a table's
    # ``th`` and ``td`` into different text nodes, so parsing one flattened line is
    # not sufficient.  Limit the lookup to the label's small structural container;
    # otherwise an unrelated article card in the footer can lend its date to this BOX.
    for label in soup.find_all(string=re.compile(r"^\s*発売日(?:\s*[:：|]|\s+|\s*$)")):
        label_text = str(label).strip()
        if "発売日はいつ" in label_text:
            continue
        node = label.parent
        candidates: list[str] = []
        if isinstance(node, Tag):
            candidates.append(node.get_text(" ", strip=True))
            row = node.find_parent("tr")
            if row is not None:
                candidates.insert(0, row.get_text(" ", strip=True))
            elif isinstance(node.parent, Tag) and node.parent.name in {"p", "li", "dl"}:
                candidates.insert(0, node.parent.get_text(" ", strip=True))
        for candidate in candidates:
            if value := _date_from_text(candidate):
                return value

    # The explanatory sentence often splits the date and ``発売となる`` across
    # nested tags.  Join only the section headed "発売日はいつ？" instead of
    # scanning the whole document.  Whole-document scanning was the direct cause
    # of the repeated 30th CELEBRATION false alert: a footer card such as
    # "8/22発売予定" was mistaken for this product's date.
    for heading in soup.find_all(list(_HEADINGS)):
        heading_text = heading.get_text(" ", strip=True)
        if "発売日はいつ" not in heading_text:
            continue
        section_text, _ = _section(heading)
        if value := _date_from_text(section_text):
            return value

    title_node = soup.find("h1")
    title_text = title_node.get_text(" ", strip=True) if title_node else ""
    if "発売" in title_text:
        return _date_from_text(title_text)
    return None


def _article_updated_date(soup: BeautifulSoup) -> date | None:
    """Read the editorial update date used as an open-invitation seen date."""

    lines = [line.strip() for line in soup.get_text("\n", strip=True).splitlines() if line.strip()]
    for line in lines[:80]:
        compact = re.sub(r"\s+", "", line)
        if not re.fullmatch(r"20\d{2}年\d{1,2}月\d{1,2}日更新", compact):
            continue
        if value := _date_from_text(compact):
            return value
    return None


def _year_adjusted(value: datetime | date, release_date: date | None) -> datetime | date:
    value_date = value.date() if isinstance(value, datetime) else value
    if not release_date or value_date <= release_date + timedelta(days=90):
        return value
    # A January release commonly has its application period in December of the
    # previous year.  Japanese secondary articles often omit that year.
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value


def _starts(text: str, release_date: date | None) -> list[datetime | date]:
    matches = list(_START_LABEL.finditer(text))
    scopes: list[str]
    if matches:
        scopes = [
            text[match.end() : matches[index + 1].start() if index + 1 < len(matches) else None][
                :220
            ]
            for index, match in enumerate(matches)
        ]
    elif _RANGE_MARKER.search(text):
        scopes = [text[:220]]
    else:
        scopes = []

    output: list[datetime | date] = []
    base = release_date or datetime.now().date()
    for scope in scopes:
        parsed = parse_period_start(scope, base)
        if parsed.value:
            value = _year_adjusted(parsed.value, release_date)
            if value not in output:
                output.append(value)
    return output


def _start_is_intentionally_unpublished(retailer_id: str, block_text: str) -> bool:
    """Return true for known open-ended or pre-announcement listings.

    Rows marked "受付前" or "判明次第" are promises of future information,
    not parser failures. Amazon's open invitation is handled separately as a
    currently available application whose exact opening time is unpublished.
    """
    compact = re.sub(r"\s+", "", block_text)
    return any(
        marker in compact
        for marker in (
            "受付前",
            "判明次第",
            "日時未定",
            "抽選期間-",
            "抽選期間：-",
        )
    )


def parse_snkrdunk(
    html: str, url: str, source: SourceConfig, config: Config
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    soup = BeautifulSoup(html, "lxml")
    game_id = _article_game(source)
    product = _product(html, game_id, config)
    if not product:
        return (
            [],
            [],
            [
                Alert(
                    game_id,
                    source.id,
                    url,
                    soup.title.get_text(" ", strip=True) if soup.title else source.name,
                    ["BOX", "発売日"],
                    "new_target_article_without_product",
                    "対象BOXの商品名を解析できません",
                    None,
                    url,
                ).with_fingerprint()
            ],
        )

    product_name, product_category, product_key = product
    release_date = _release_date(soup)
    releases: list[Release] = []
    if release_date:
        releases.append(
            Release(
                game_id,
                product_name,
                product_category,
                product_key,
                release_date,
                None,
                url,
                url,
                source.source_tier,
                "snkrdunk_release_label",
                "medium",
            ).with_id()
        )

    blocks: list[tuple[str, str, list[str]]] = []
    for heading in soup.find_all(list(_HEADINGS)):
        heading_text = heading.get_text(" ", strip=True)
        if _retailer(heading_text, source):
            section_text, links = _section(heading)
            blocks.append((heading_text, section_text, links))
    for row in soup.find_all("tr"):
        row_text = row.get_text(" ", strip=True)
        if _retailer(row_text, source):
            blocks.append(
                (
                    row_text,
                    row_text,
                    [str(anchor.get("href")) for anchor in row.find_all("a", href=True)],
                )
            )

    cases_by_id: dict[str, LotteryCase] = {}
    alerts: list[Alert] = []
    alerted_retailers: set[str] = set()
    open_invitation_retailers: set[str] = set()
    for heading_text, block_text, links in blocks:
        retailer = _retailer(heading_text, source)
        if not retailer:
            continue
        retailer_id, retailer_name = retailer
        if _start_is_intentionally_unpublished(retailer_id, block_text):
            continue
        starts = _starts(block_text, release_date)
        if not starts:
            compact_block = re.sub(r"\s+", "", block_text)
            if (
                retailer_id == "amazon_jp"
                and "招待リクエスト" in compact_block
                and retailer_id not in open_invitation_retailers
            ):
                # Amazon does not expose an invitation opening timestamp.  Use
                # the article's explicit update date as the first confirmed
                # availability date and label it as such in user notifications.
                seen_on = _article_updated_date(soup) or datetime.now().date()
                case = LotteryCase(
                    game_id,
                    retailer_id,
                    retailer_name,
                    product_name,
                    product_category,
                    product_key,
                    seen_on,
                    _official_link(links, url),
                    url,
                    source.source_tier,
                    "snkrdunk_open_invitation_seen",
                    "low",
                ).with_id()
                cases_by_id[case.case_id] = case
                open_invitation_retailers.add(retailer_id)
                continue
            relevant = any(word in block_text for word in ("抽選", "応募", "受付", "招待"))
            if relevant and retailer_id not in alerted_retailers:
                alerts.append(
                    Alert(
                        game_id,
                        source.id,
                        url,
                        heading_text,
                        [word for word in ("抽選", "応募", "受付", "招待") if word in block_text],
                        "retailer_lottery_block_without_start",
                        f"{retailer_name}の受付告知から正確な開始日時を解析できません",
                        None,
                        url,
                    ).with_fingerprint()
                )
                alerted_retailers.add(retailer_id)
            continue
        official_url = _official_link(links, url)
        for start in starts:
            case = LotteryCase(
                game_id,
                retailer_id,
                retailer_name,
                product_name,
                product_category,
                product_key,
                start,
                official_url,
                url,
                source.source_tier,
                "snkrdunk_retailer_heading",
                "medium",
            ).with_id()
            cases_by_id[case.case_id] = case
    return list(cases_by_id.values()), releases, alerts


__all__ = [
    "discover_snkrdunk_article_urls",
    "is_snkrdunk_schedule_page",
    "is_snkrdunk_schedule_healthy_without_candidates",
    "parse_snkrdunk",
]
