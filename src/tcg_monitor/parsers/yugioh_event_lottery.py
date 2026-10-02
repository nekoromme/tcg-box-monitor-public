"""公式大会ページの通販抽選だけを読む。大会参加や会場物販とは混ぜない。"""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from tcg_monitor.additional_products import additional_matches
from tcg_monitor.japanese_datetime import parse_period_start
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig
from tcg_monitor.parsers.local_lottery import _application_deadline

EVENT_INDEX = "https://www.yugioh-card.com/japan/event/"
_EVENT_PATH = re.compile(r"^/japan/event/(?:ycsj|wcs)/[^/]*?(20\d{2})/?$", re.I)
_PERIOD_LABEL = re.compile(r"^抽選(?:申し込み|申込(?:み)?|応募)(?:受付)?期間$")


def is_yugioh_event_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.netloc == "www.yugioh-card.com" and bool(_EVENT_PATH.fullmatch(parts.path))


def discover_yugioh_event_urls(html: str, url: str, today: date) -> list[str]:
    """公式一覧から当年以降の開催ページを追う。年度ごとの手動追記は不要。"""
    found: list[str] = []
    for anchor in BeautifulSoup(html, "lxml").find_all("a", href=True):
        candidate = urljoin(url, str(anchor.get("href")))
        match = _EVENT_PATH.fullmatch(urlsplit(candidate).path)
        if (is_yugioh_event_url(candidate) and match and int(match.group(1)) >= today.year
                and candidate not in found):
            found.append(candidate)
    return found[:12]


def _table_periods(table: Tag) -> list[tuple[str, str]]:
    """rowspanで省略された期間ラベルだけを引き継ぎ、当選発表行では解除する。"""
    periods: list[tuple[str, str]] = []
    remaining = 0
    for row in table.find_all("tr"):
        header = row.find("th")
        if isinstance(header, Tag):
            label = re.sub(r"\s+", "", header.get_text())
            remaining = (
                int(str(header.get("rowspan") or 1)) if _PERIOD_LABEL.fullmatch(label) else 0
            )
        if remaining <= 0:
            continue
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if cells:
            round_label = cells[0] if len(cells) > 1 else ""
            # 開始と締切が同じセルにある場合だけ使う。結果発表の日付は参照しない。
            value = cells[-1]
            if re.search(r"[～〜~]|から|\s[-–]\s", value):
                periods.append((round_label, value))
        remaining -= 1
    return periods


def parse_yugioh_event_lottery(
    html: str, url: str, source: SourceConfig, config: Config, today: date | None = None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    if not is_yugioh_event_url(url) or not source.supports("yu_gi_oh"):
        return [], [], []
    now = datetime.now(ZoneInfo(config.timezone))
    current = today or now.date()
    cases: dict[str, LotteryCase] = {}
    alerts: list[Alert] = []
    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.find_all("a", href=True):
        link_text = anchor.get_text(" ", strip=True)
        if "デュエルセット" not in link_text or "抽選" not in link_text:
            continue
        application_url = urljoin(url, str(anchor.get("href")))
        parts = urlsplit(application_url)
        if parts.netloc != "livepocket.jp" or not re.fullmatch(r"/e/[A-Za-z0-9_-]+", parts.path):
            continue
        section = anchor.find_parent("section")
        if not isinstance(section, Tag):
            continue
        scope = section.get_text(" ", strip=True)
        if "WEB抽選販売" not in re.sub(r"\s+", "", scope) or not re.search(
            r"特典カード|プロモカード|収録カード", scope,
        ):
            continue
        for table in section.find_all("table"):
            product_cell = None
            for row in table.find_all("tr"):
                header = row.find("th")
                if isinstance(header, Tag) and header.get_text(strip=True) == "商品":
                    product_cell = row.find("td")
                    break
            if not isinstance(product_cell, Tag):
                continue
            name = product_cell.get_text(" ", strip=True)
            products = additional_matches(config.games["yu_gi_oh"], name, identified_game=True)
            if len(products) != 1:
                continue
            product = products[0]
            periods = _table_periods(table)
            if not periods:
                alerts.append(Alert(
                    "yu_gi_oh", source.id, url, name, ["抽選申し込み期間"],
                    "yugioh_event_application_period_missing", "公式通販抽選の応募期間を読めません",
                    None, application_url,
                ).with_fingerprint())
            for round_label, period_text in periods:
                start = parse_period_start(period_text, current).value
                end = _application_deadline("応募期間 " + period_text, current)
                if not start or not end:
                    alerts.append(Alert(
                        "yu_gi_oh", source.id, url, name, ["抽選申し込み期間"],
                        "yugioh_event_application_period_missing",
                        "公式通販抽選の開始・締切を確定できません", None, application_url,
                    ).with_fingerprint())
                    continue
                end_day = end.date() if isinstance(end, datetime) else end
                if end_day < current or (isinstance(end, datetime) and end < now):
                    continue
                case = LotteryCase(
                    "yu_gi_oh", "dragonstar_online", "ドラゴンスター（遊戯王公式イベント通販）",
                    product.product_name, product.product_category, product.canonical_product_key,
                    start, application_url, url, source.source_tier,
                    "yugioh_official_event_web_lottery", "high", end_at=end,
                    application_round=round_label or start.isoformat(),
                ).with_id()
                cases[case.case_id] = case
    return list(cases.values()), [], alerts
