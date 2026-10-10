from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
from urllib.parse import urlsplit

from tcg_monitor.identity import (
    OBSERVED_START_METHODS,
    is_pokemon_30th_cardset,
    lottery_dedupe_key,
    release_dedupe_key,
)
from tcg_monitor.models import (
    Alert,
    LotteryCase,
    OpportunityKind,
    Release,
    SourceTier,
)
from tcg_monitor.release_sources import is_trusted_retailer_release

ORDER = {"official": 0, "official_indirect": 1, "secondary": 2}


def lottery_source_priority(tier: SourceTier, url: str) -> tuple[int, int]:
    """公式を優先し、同じ確度の補助情報なら長い入荷Nowまとめを最後にする。"""
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    return ORDER[tier.value], int(host == "nyuka-now.com")


def merge_lotteries(items: list[LotteryCase]) -> tuple[list[LotteryCase], list[Alert]]:
    observed_aliases: dict[str, set[str]] = defaultdict(set)
    for item in items:
        if (is_pokemon_30th_cardset(item.game_id, item.canonical_product_key)
                and item.end_at is not None
                and item.extraction_method not in OBSERVED_START_METHODS):
            # 同じ締切について実際の開始日も読めたら、その従来IDへ仮日付側をまとめる。
            observed_key = lottery_dedupe_key(replace(
                item, extraction_method="yahoo_realtime_detected_next_day",
            ))
            observed_aliases[observed_key].add(lottery_dedupe_key(item))
    grouped: dict[str, list[LotteryCase]] = defaultdict(list)
    for item in items:
        grouping_identity = lottery_dedupe_key(item)
        if is_pokemon_30th_cardset(item.game_id, item.canonical_product_key):
            # 店舗・抽選回は従来どおり区別し、種類だけを共通の商品名にまとめる。
            # 仮日付・LINEフォームの識別もidentityの共通規則に従う。
            identity = grouping_identity
            aliases = observed_aliases.get(identity, set())
            if (item.extraction_method in OBSERVED_START_METHODS
                    and len(aliases) == 1):
                identity = next(iter(aliases))
                grouping_identity = identity
            item = replace(
                item,
                product_name="30th CELEBRATION カードセット",
                canonical_product_key="pokemon_30th_cardset",
                case_id=sha256(identity.encode()).hexdigest(),
            )
        grouped[grouping_identity].append(item)
    merged = []
    for values in grouped.values():
        ordered = sorted(values, key=lambda item: (
            int(item.extraction_method.startswith("additional_product_")
                and item.opportunity_kind == OpportunityKind.DIRECT_SALE_SEEN),
            *lottery_source_priority(item.source_tier, item.source_url),
            # 同じ告知を複数経路で読めた場合、表示用短縮リンクより応募先を残す。
            int(urlsplit(item.official_url).netloc.lower() in {
                "t.co", "x.com", "twitter.com", "www.x.com", "www.twitter.com",
            }),
            int(is_pokemon_30th_cardset(item.game_id, item.canonical_product_key)
                and item.extraction_method in OBSERVED_START_METHODS),
            int(item.retailer_id == "lorcana_official"
                and item.opportunity_kind == OpportunityKind.DIRECT_SALE_SEEN),
        ))
        first = ordered[0]
        # The search page may expose a shortened display URL. Enrich only the
        # SAME post/case when another route provides its full same-host URL.
        # Keep case/delivery identity and source/date priority unchanged.
        for candidate in ordered[1:]:
            if (candidate.source_url == first.source_url
                    and candidate.official_url != first.official_url
                    and candidate.official_url.startswith(first.official_url)
                    and urlsplit(candidate.official_url).netloc
                    == urlsplit(first.official_url).netloc):
                first = replace(first, official_url=candidate.official_url)
        # 公式側が発表日を載せない場合、同じ抽選回の投稿にある日付を補う。
        if first.result_at is None:
            dated = next((item for item in ordered if item.result_at is not None), None)
            if dated:
                first = replace(first, result_at=dated.result_at)
        merged.append(first)
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
