from __future__ import annotations

import re
from datetime import date, datetime
from html import unescape
from urllib.parse import urljoin

from tcg_monitor.classifier import classify_product
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig

_PRODUCT_OBJECT = re.compile(r"p\[\d+\]\s*=\s*\{(?P<body>.*?)\}\s*;", re.DOTALL)
_CATALOG_ROOT = "https://www.yugioh-card.com/japan/products/"
_BOX_CLASS_KEYS = {"basic", "concept", "special"}


def _field(body: str, name: str) -> str:
    match = re.search(
        rf"[\"']{re.escape(name)}[\"']\s*:\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
        body,
        re.DOTALL,
    )
    if not match:
        return ""
    value = match.group("value")
    value = value.replace(r"\/", "/").replace(r'\"', '"').replace(r"\'", "'")
    return unescape(value).strip()


def _official_url(raw_url: str, fallback: str) -> str:
    if not raw_url or raw_url.startswith("#"):
        return fallback
    target = raw_url if "." in raw_url.rsplit("/", 1)[-1] else f"{raw_url.rstrip('/')}/"
    return urljoin(_CATALOG_ROOT, target)


def _release_date_in_window(
    release_date: date | None,
    release_month: str | None,
    config: Config,
    today: date,
) -> bool:
    past_days = int(config.system.get("implausible_past_days", 45))
    future_days = int(config.system.get("max_future_days", 365))
    if release_date:
        delta = (release_date - today).days
        return -past_days <= delta <= future_days
    if release_month:
        try:
            month_start = datetime.strptime(release_month, "%Y-%m").date()
        except ValueError:
            return False
        delta = (month_start - today.replace(day=1)).days
        return -past_days <= delta <= future_days
    return False


def parse_yugioh_official_products(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
    today: date | None = None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Parse the official OCG catalog embedded as JavaScript product records."""

    game = config.games["yu_gi_oh"]
    current = today or datetime.now().astimezone().date()
    releases: dict[str, Release] = {}
    alerts: list[Alert] = []
    records = list(_PRODUCT_OBJECT.finditer(html))

    for record in records:
        body = record.group("body")
        class_key = _field(body, "class-key").casefold()
        if class_key not in _BOX_CLASS_KEYS:
            continue
        category = _field(body, "class-name")
        product_name = _field(body, "title")
        raw_release = _field(body, "release-date")
        if not product_name:
            continue
        official_url = _official_url(_field(body, "url"), url)
        combined = f"{category} {product_name} {raw_release}"
        classified = classify_product(game, product_name, combined, official_url)
        if not classified.is_box:
            continue

        parsed = parse_first_datetime(raw_release)
        release_date: date | None = None
        if isinstance(parsed.value, datetime):
            release_date = parsed.value.date()
        elif isinstance(parsed.value, date):
            release_date = parsed.value
        if not release_date and not parsed.month_only:
            alerts.append(
                Alert(
                    "yu_gi_oh",
                    source.id,
                    url,
                    product_name,
                    ["発売日"],
                    "new_box_product_without_release_value",
                    "遊戯王OCG公式商品一覧から発売日または発売月を解析できません",
                    None,
                    official_url,
                ).with_fingerprint()
            )
            continue
        if not _release_date_in_window(
            release_date,
            parsed.month_only,
            config,
            current,
        ):
            continue

        release = Release(
            "yu_gi_oh",
            product_name,
            classified.product_category,
            classified.canonical_product_key,
            release_date,
            parsed.month_only,
            official_url,
            url,
            source.source_tier,
            "yugioh_official_embedded_catalog",
            "high" if release_date else "medium",
        ).with_id()
        releases[release.release_id] = release

    if not records:
        alerts.append(
            Alert(
                "yu_gi_oh",
                source.id,
                url,
                source.name,
                ["商品情報", "発売日"],
                "expected_element_missing",
                "遊戯王OCG公式商品一覧の商品データが見つかりません",
                None,
                url,
            ).with_fingerprint()
        )
    return [], list(releases.values()), alerts


__all__ = ["parse_yugioh_official_products"]
