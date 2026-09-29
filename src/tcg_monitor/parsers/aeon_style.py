"""AEON entry sales: keep each product and its own application period together."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import normalize_text, parse_first_datetime, parse_period_start
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig


def _period(text: str, today: date) -> tuple[datetime | date, datetime | date] | None:
    """Require both endpoints; a deadline alone must never become a start."""
    text = normalize_text(text)
    parts = re.split(r"~|から", text, maxsplit=1)
    if len(parts) != 2:
        return None
    start = parse_period_start(text, base_date=today).value
    if not start:
        return None
    base = start.date() if isinstance(start, datetime) else start
    end = parse_first_datetime(parts[1], base).value
    if not end:
        return None
    start_day = start.date() if isinstance(start, datetime) else start
    end_day = end.date() if isinstance(end, datetime) else end
    return (start, end) if end_day >= start_day else None


def _case(source: SourceConfig, url: str, official: str, product: dict[str, Any],
          period: tuple[datetime | date, datetime | date], config: Config) -> LotteryCase | None:
    game_id = product["game_id"]
    if not source.supports(game_id):
        return None
    start, end = period
    now = datetime.now(ZoneInfo(config.timezone))
    if (isinstance(end, datetime) and end < now) or (
        not isinstance(end, datetime) and end < now.date()
    ):
        return None
    return LotteryCase(
        game_id, "aeon_style_online", "イオンスタイルオンライン",
        product["product_name"], product["product_category"], product["canonical_product_key"],
        start, official, url, source.source_tier, "aeon_entry_product_period",
        "medium" if source.source_tier.value == "secondary" else "high", end_at=end,
    ).with_id()


def parse_aeon_entry(html: str, url: str, source: SourceConfig, config: Config
                     ) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    soup = BeautifulSoup(html, "lxml")
    cases, alerts = [], []
    today = datetime.now(ZoneInfo(config.timezone)).date()
    if "エントリー販売" not in soup.get_text():
        raise ValueError("AEON entry page missing; possible access-check or changed page")
    for heading in soup.find_all("h2"):
        name = heading.get_text(" ", strip=True)
        # Only the pack-count suffix is removed, never arbitrary deck/set exclusions.
        name = re.sub(r"\s*[0-9０-９]+パックセット\s*$", "", name)
        product = None
        for game_id, game in config.games.items():
            if not source.supports(game_id) or not any(k in name for k in game.include_keywords):
                continue
            category = next((k for k in sorted(game.box_product_keywords, key=len, reverse=True)
                             if k in name), None)
            if not category:
                continue
            tail = name.split(category, 1)[1].strip()
            if not tail:
                continue
            code = re.search(r"[\[【]((?:OP|EB|PRB)-\d{2}|(?:FB|SB)\d{2})[\]】]", tail)
            short = tail[:code.start()].strip() if code else tail
            short = short.strip("「」『』")
            normalized = f"{category}「{short}」" + (f" [{code[1]}]" if code else "")
            classified = classify_product(game, normalized, normalized)
            if classified.is_target:
                product = dict(game_id=game_id, product_name=normalized,
                               product_category=classified.product_category,
                               canonical_product_key=classified.canonical_product_key)
            break
        if product is None:
            continue
        # Walk text nodes only, stopping before the next product heading.
        texts = []
        for node in heading.next_elements:
            if isinstance(node, Tag) and node.name in {"h1", "h2"}:
                break
            if isinstance(node, NavigableString):
                texts.append(str(node))
        text = " ".join(texts)
        match = re.search(r"エントリー(?:受付)?期間\s*(.{1,160})", text, re.S)
        period = _period(match[1], today) if match else None
        if period is None:
            alerts.append(Alert(product["game_id"], source.id, url, name, ["エントリー期間"],
                                "aeon_entry_period_missing", "商品別の受付期間を確認できません",
                                None, url).with_fingerprint())
        elif case := _case(source, url, url, product, period, config):
            cases.append(case)
    return cases, [], alerts


def parse_aeon_summary(html: str, url: str, source: SourceConfig, config: Config
                       ) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Read only AEON's table, never neighboring retailers or the article date.

    Short names are accepted only from the configured, officially verified product
    catalog. Unknown names raise an alert instead of inventing a BOX identity.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    cases, alerts = [], []
    found_section = False
    for heading in soup.find_all(["h2", "h3"]):
        if not heading.get_text(" ", strip=True).startswith("イオンスタイルオンライン"):
            continue
        found_section = True
        if "終了" in heading.get_text():
            continue
        table = None
        for node in heading.next_siblings:
            if isinstance(node, Tag) and node.name in {"h2", "h3"}:
                break
            if isinstance(node, Tag) and node.name == "table":
                table = node
                break
        if table is None:
            raise ValueError("AEON summary table missing")
        fields = {}
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) == 2:
                fields[cells[0].get_text("", strip=True)] = cells[1]
        official = next((str(a["href"]) for a in table.find_all("a", href=True)
                         if urlsplit(str(a["href"])).hostname == "aeonretail.com"
                         and urlsplit(str(a["href"])).path.startswith("/Page/k-")), None)
        period_cell = fields.get("受付") or fields.get("受付期間")
        products_cell = fields.get("対象商品")
        if not official or period_cell is None or products_cell is None:
            raise ValueError("AEON summary missing official link, products, or period")
        period = _period(period_cell.get_text(" ", strip=True),
                         datetime.now(ZoneInfo(config.timezone)).date())
        if period is None:
            raise ValueError("AEON summary application period invalid")
        names = products_cell.get_text("\n", strip=True).splitlines()
        catalog = source.parser_options.get("products", [])
        seen = set()
        for name in names:
            name = name.strip("・ \xa0")
            if not name or re.fullmatch(r"【.+】", name):
                continue
            product = next((p for p in catalog if name in p["aliases"]), None)
            if product is None:
                alerts.append(Alert(None, source.id, url, name, ["対象商品"],
                                    "aeon_entry_unknown_product",
                                    "イオンの新しい対象商品を公式で確認してください", None,
                                    official).with_fingerprint())
                continue
            if (case := _case(source, url, official, product, period, config)) is not None and (
                case.case_id not in seen
            ):
                cases.append(case)
                seen.add(case.case_id)
    if not found_section:
        raise ValueError("AEON summary section missing")
    return cases, [], alerts
