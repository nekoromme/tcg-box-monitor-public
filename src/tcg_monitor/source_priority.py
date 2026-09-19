from __future__ import annotations

import re
from collections import defaultdict

from tcg_monitor.identity import lottery_dedupe_key, release_dedupe_key
from tcg_monitor.models import Alert, LotteryCase, Release
from tcg_monitor.release_sources import is_trusted_retailer_release

ORDER = {"official": 0, "official_indirect": 1, "secondary": 2}


def merge_lotteries(items: list[LotteryCase]) -> tuple[list[LotteryCase], list[Alert]]:
    grouped: dict[str, list[LotteryCase]] = defaultdict(list)
    for item in items:
        grouped[lottery_dedupe_key(item)].append(item)
    merged = [
        sorted(values, key=lambda item: ORDER[item.source_tier.value])[0]
        for values in grouped.values()
    ]
    return merged, []


def _release_month(item: Release) -> str | None:
    if item.release_date is not None:
        return f"{item.release_date.year:04d}-{item.release_date.month:02d}"
    return item.release_month


def _authoritative_secondary_conflict(first: Release, other: Release) -> bool:
    """Compare only values that genuinely contradict an official release value.

    The official Pokémon catalog lists currently published products and can lag a
    newly announced set. A secondary exact date and an official month-only value
    are compatible when they point to the same month; absence from the catalog is
    not evidence of a conflict.
    """

    tiers = {first.source_tier.value, other.source_tier.value}
    if "official" not in tiers or not tiers.intersection({"secondary", "official_indirect"}):
        return False

    if first.release_date is not None and other.release_date is not None:
        return first.release_date != other.release_date

    first_month = _release_month(first)
    other_month = _release_month(other)
    return (
        first_month is not None
        and other_month is not None
        and first_month != other_month
    )


def merge_releases(items: list[Release]) -> tuple[list[Release], list[Alert]]:
    grouped: dict[str, list[Release]] = defaultdict(list)
    alerts: list[Alert] = []
    output: list[Release] = []
    # コード付き商品は店舗と公式の表記が違っても同一視する。
    # コードのない既存記事は従来の商品名キーで、コード側に結び付ける。
    def code_key(item: Release) -> str | None:
        pattern = {
            "one_piece_card": r"\b(?:OP|EB|PRB)-\d{2}\b",
            "gundam_card": r"\b(?:GD|EB)\d{2}\b",
        }.get(item.game_id)
        if pattern and (match := re.search(
            pattern, f"{item.canonical_product_key} {item.product_name}", re.I,
        )):
            return f"{item.game_id}:code:{match.group(0).upper()}"
        return None

    title_codes: dict[str, set[str]] = defaultdict(set)
    for item in items:
        if code := code_key(item):
            title_codes[release_dedupe_key(item)].add(code)
    for item in items:
        title = release_dedupe_key(item)
        codes = title_codes.get(title, set())
        key = code_key(item) or (next(iter(codes)) if len(codes) == 1 else title)
        grouped[key].append(item)
    for values in grouped.values():
        values.sort(key=lambda item: ORDER[item.source_tier.value])
        first = values[0]
        # 公式が月だけなら、その月と一致する検証済み販売店の日付を補完に使う。
        # メーカーの確定日、または月が食い違う情報は販売店で上書きしない。
        if first.release_date is None:
            for candidate in values:
                if is_trusted_retailer_release(candidate) and (
                    not first.release_month or first.release_month == _release_month(candidate)
                ):
                    first = candidate
                    break
        output.append(first)
        for other in values:
            if _authoritative_secondary_conflict(first, other):
                alerts.append(
                    Alert(
                        first.game_id,
                        "release",
                        first.source_url,
                        first.product_name,
                        ["発売日"],
                        "secondary_official_conflict",
                        "発売日情報が矛盾",
                        None,
                        first.official_url,
                    ).with_fingerprint()
                )
    return output, alerts
