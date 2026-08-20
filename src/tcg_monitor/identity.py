from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from tcg_monitor.models import LotteryCase, OpportunityKind, Release

_ONE_PIECE_CODE = re.compile(r"\b(?:OP|EB|PRB)-\d{2}\b", re.I)
_DRAGONBALL_CODE = re.compile(r"\b(?:FB|SB|ST)\d{2}\b", re.I)
_QUOTED_TITLE = re.compile(r"[「『\"“]([^」』\"”]{2,80})[」』\"”]")
_DATE_NOISE = re.compile(
    r"(?:20\d{2}[年/.])?\d{1,2}[月/.]\d{1,2}日?"
    r"(?:\([月火水木金土日]\))?(?:\s*\d{1,2}[:時]\d{0,2}分?)?"
)
_CALENDAR_PREFIX = re.compile(r"^[\[【][^\]】]*(?:発売|新弾)[^\]】]*[\]】]")
_NOISE_WORDS = (
    "ポケモンカードゲーム",
    "ポケモンカード",
    "ポケカ",
    "ONE PIECEカードゲーム",
    "ONE PIECEカード",
    "ワンピースカードゲーム",
    "ワンピースカード",
    "ワンピカード",
    "ドラゴンボールスーパーカードゲーム",
    "フュージョンワールド",
    "DBFW",
    "強化拡張パック",
    "ハイクラスパック",
    "再拡張パック",
    "拡張パック",
    "エクストラブースター",
    "プレミアムブースター",
    "ブースターパック",
    "MANGA BOOSTER",
    "STORY BOOSTER",
    "ブースター",
    "1BOX",
    "BOX",
    "ボックス",
    "新弾",
    "発売予定",
    "発売日",
    "発売",
)
_PROVISIONAL_PRODUCT_MARKERS = (
    "商品名は画像参照",
    "対象商品",
    "抽選",
    "受付",
    "応募",
    "当選",
    "連絡日",
    "お渡し期間",
    "購入期限",
    "販売期間",
    "販売について",
    "本日以降",
    "本日",
    "今日",
    "明日",
    "今後",
    "開催予定",
    "店舗一覧",
    "抽選リスト",
)


def is_provisional_product_name(value: str) -> bool:
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))
    return any(marker in compact for marker in _PROVISIONAL_PRODUCT_MARKERS)


def release_title_token(value: str) -> str:
    """Return a source-independent product title token for legacy event matching."""
    text = unicodedata.normalize("NFKC", value).strip()
    text = _CALENDAR_PREFIX.sub("", text).strip()
    quoted = _QUOTED_TITLE.findall(text)
    if quoted:
        # Product articles sometimes contain several quotes.  The longest quoted
        # value is normally the product's proper name and is stable across sources.
        text = max(quoted, key=len)
    else:
        text = _DATE_NOISE.sub("", text)
        text = _ONE_PIECE_CODE.sub("", text)
        text = _DRAGONBALL_CODE.sub("", text)
        for word in _NOISE_WORDS:
            text = re.sub(re.escape(word), "", text, flags=re.I)
    return re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー]+", "", text).lower()


def release_dedupe_key_values(
    game_id: str,
    product_name: str,
    canonical_product_key: str,
    fallback_id: str = "",
) -> str:
    """Identify one physical BOX from source-independent product fields."""
    haystack = f"{canonical_product_key} {product_name}"
    if game_id == "dragon_ball_fusion_world" and (
        match := _DRAGONBALL_CODE.search(haystack)
    ):
        return f"{game_id}:code:{match.group(0).upper()}"
    token = release_title_token(product_name)
    if token:
        return f"{game_id}:title:{token}"
    if game_id == "one_piece_card" and (match := _ONE_PIECE_CODE.search(haystack)):
        return f"{game_id}:code:{match.group(0).upper()}"
    token = release_title_token(canonical_product_key)
    return f"{game_id}:title:{token or fallback_id}"


def release_dedupe_key(release: Release) -> str:
    """Identify one physical BOX even when official and secondary URLs differ."""
    return release_dedupe_key_values(
        release.game_id,
        release.product_name,
        release.canonical_product_key,
        release.release_id,
    )


def lottery_dedupe_key(case: LotteryCase) -> str:
    token = release_title_token(case.product_name)
    product_haystack = f"{case.canonical_product_key} {case.product_name}"
    product_code_pattern = {
        "one_piece_card": _ONE_PIECE_CODE,
        "dragon_ball_fusion_world": _DRAGONBALL_CODE,
    }.get(case.game_id)
    product_code = (
        product_code_pattern.search(product_haystack)
        if product_code_pattern is not None
        else None
    )
    product_identity = (
        product_code.group(0).upper()
        if product_code is not None
        else token or case.canonical_product_key
    )
    retailer_id = case.retailer_id
    if retailer_id in {
        "onepiece_official_shop",
        "onepiece_official_shop_sendai",
        "onepiece_official_shop_miyagi_natori",
    }:
        # The national Bandai Namco article and the existing Parks ticket pages
        # describe the same application.  Normalize only for same-run merging;
        # stored case IDs remain untouched.
        retailer_id = "onepiece_official_shop"
    # 同じ抽選をLivePocketでは時刻付き、Xでは日付だけで取得する場合がある。
    # 通知単位では同日開始の同一店舗・同一商品を1件として扱う。
    start_day = case.start_at.date() if isinstance(case.start_at, datetime) else case.start_at
    parts = [
        case.game_id,
        retailer_id,
        product_identity,
        start_day.isoformat(),
    ]
    if case.opportunity_kind != OpportunityKind.LOTTERY:
        parts.append(case.opportunity_kind.value)
    return "|".join(parts)


__all__ = [
    "is_provisional_product_name",
    "lottery_dedupe_key",
    "release_dedupe_key",
    "release_dedupe_key_values",
    "release_title_token",
]
