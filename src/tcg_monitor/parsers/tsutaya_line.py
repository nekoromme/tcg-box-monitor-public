from __future__ import annotations

import json
import re
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from tcg_monitor.classifier import classify_product
from tcg_monitor.config import source_with_runtime_parser_profile
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig, SourceTier


def tsutaya_line_form_urls(source: SourceConfig) -> tuple[str, ...]:
    """Return official LINE form APIs that must run beside the store X feed."""

    source = source_with_runtime_parser_profile(source)
    raw = source.parser_options.get("always_fetch_urls")
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(
        isinstance(value, str) and value for value in raw
    ):
        raise ValueError(f"bad parser option always_fetch_urls: {source.id}")
    configured = set(source.discovery_urls)
    if any(value not in configured for value in raw):
        raise ValueError(f"always_fetch_urls must also be discovery_urls: {source.id}")
    return tuple(raw)


def is_tsutaya_line_form_url(source: SourceConfig, url: str) -> bool:
    return url in tsutaya_line_form_urls(source)


def _question_choices(raw_question: object) -> list[str]:
    if not isinstance(raw_question, dict):
        return []
    raw_info = raw_question.get("questionInfo")
    if not isinstance(raw_info, str):
        return []
    info = json.loads(raw_info)
    if not isinstance(info, dict):
        return []
    choices = info.get("Choices")
    if not isinstance(choices, list):
        return []
    return [
        str(choice["Description"]).strip()
        for choice in choices
        if isinstance(choice, dict)
        and isinstance(choice.get("Description"), str)
        and str(choice["Description"]).strip()
    ]


def _configured_store_targets(source: SourceConfig) -> list[tuple[str, str, str]]:
    source = source_with_runtime_parser_profile(source)
    raw = source.parser_options.get("tsutaya_line_store_targets")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"bad parser option tsutaya_line_store_targets: {source.id}")
    targets: list[tuple[str, str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"bad TSUTAYA LINE store target: {source.id}")
        values = tuple(item.get(key) for key in ("retailer_id", "retailer_name", "match"))
        if not all(isinstance(value, str) and value for value in values):
            raise ValueError(f"bad TSUTAYA LINE store target: {source.id}")
        targets.append((str(values[0]), str(values[1]), str(values[2])))
    return targets


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _application_end(raw_settings: object, timezone: str) -> datetime | None:
    if not isinstance(raw_settings, str):
        return None
    settings = json.loads(raw_settings)
    if not isinstance(settings, dict) or not settings.get("TimerEnabledEnd"):
        return None
    raw_end = settings.get("EndTime")
    if not isinstance(raw_end, str) or raw_end.startswith("0001-"):
        return None
    parsed = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed.astimezone(ZoneInfo(timezone))


def _campaign_url(url: str, title: str) -> str:
    """Keep repeat lotteries for the same product distinct across campaigns."""

    match = re.search(r"(20\d{2})年\s*(\d{1,2})月", title)
    if not match:
        return url
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("tcg_campaign", f"{match.group(1)}-{int(match.group(2)):02d}"))
    return urlunsplit((*parts[:3], urlencode(query), parts.fragment))


def parse_tsutaya_line_form(
    payload: str,
    url: str,
    source: SourceConfig,
    config: Config,
    detected_on: date | None = None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    """Parse the first-party TSUTAYA Trading Card LINE application form."""

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("TSUTAYA LINE form response is not an object")
    settings = json.loads(str(data.get("settings") or "{}"))
    if data.get("status") != "Active" or (
        isinstance(settings, dict) and settings.get("FormClosed")
    ):
        return [], [], []

    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    if "抽選" not in f"{title}\n{description}":
        return [], [], []
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise ValueError("TSUTAYA LINE form questions are missing")

    product_choices: list[str] = []
    all_choices: list[str] = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        choices = _question_choices(question)
        all_choices.extend(choices)
        if "希望商品" in str(question.get("title") or ""):
            product_choices.extend(choices)
    if not product_choices:
        raise ValueError("TSUTAYA LINE form product choices are missing")

    compact_choices = {_compact(choice) for choice in all_choices}
    matched_stores = [
        (retailer_id, retailer_name)
        for retailer_id, retailer_name, store_match in _configured_store_targets(source)
        if any(_compact(store_match) in choice for choice in compact_choices)
    ]
    if not matched_stores:
        return [], [], []

    context = f"{title}\n{description}"
    detected = detected_on or datetime.now(ZoneInfo(config.timezone)).date()
    end_at = _application_end(data.get("settings"), config.timezone)
    public_form_url = str(
        source.parser_options.get("tsutaya_line_public_form_url") or url
    )
    application_url = str(
        source.parser_options.get("tsutaya_line_application_url")
        or public_form_url
    )
    campaign_url = _campaign_url(application_url, title)
    cases: dict[str, LotteryCase] = {}
    for game_id, game in config.games.items():
        if not source.supports(game_id):
            continue
        if not any(
            keyword.casefold() in context.casefold()
            for keyword in game.include_keywords
        ):
            continue
        for product_name in product_choices:
            classified = classify_product(
                game,
                product_name,
                product_name,
                public_form_url,
            )
            if not classified.is_box:
                continue
            for retailer_id, retailer_name in matched_stores:
                case = LotteryCase(
                    game_id,
                    retailer_id,
                    retailer_name,
                    classified.product_name,
                    classified.product_category,
                    classified.canonical_product_key,
                    detected,
                    campaign_url,
                    public_form_url,
                    SourceTier.OFFICIAL,
                    "tsutaya_line_official_form_first_seen",
                    "medium",
                    end_at=end_at,
                ).with_id()
                cases[case.case_id] = case
    return list(cases.values()), [], []


__all__ = [
    "is_tsutaya_line_form_url",
    "parse_tsutaya_line_form",
    "tsutaya_line_form_urls",
]
