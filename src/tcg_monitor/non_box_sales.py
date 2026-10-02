"""Purchase windows for explicitly selected products, never ordinary decks/supplies."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

from tcg_monitor.additional_products import additional_matches
from tcg_monitor.japanese_datetime import normalize_text, parse_first_datetime, parse_period_start
from tcg_monitor.models import Config, LotteryCase, OpportunityKind, SourceConfig

_SALE = r"(?:予約|受注(?:生産)?|注文|先着販売|再販|再販売|販売)"
_LABEL = re.compile(
    rf"(?:{_SALE}(?:の)?(?:受け?付け?|受付)?|受付)"
    r"(?:期間|開始(?:日時)?|締め?切り?|締切|終了|期限)"
)
_DATE = re.compile(
    r"(?:(?:20\d{2})[/.年])?\d{1,2}[/.月]\d{1,2}日?"
    r"(?:\([月火水木金土日]\))?"
    r"\s*(?:(?:午前|午後|正午|昼)?\s*\d{1,2}(?:時(?:\d{1,2}分?)?|:\d{2}))?"
)
_BOUNDARY = re.compile(
    r"発売(?:予定)?日|発売予定|お届け|発送|出荷|当選|抽選結果|販売価格|商品価格|税込|内容物"
)
_CLOSED = re.compile(
    rf"{_SALE}(?:の)?(?:受付|受け付け)?(?:は|が|を)?"
    r"(?:終了(?!(?:予定|日時|日|時|まで|は|[:：]?\d))|締め?切りました|締切済)"
    r"|完売|売り切れ|在庫なし|SOLD\s*OUT|抽選結果|当選発表", re.I,
)


def additional_sale_signal(text: str) -> bool:
    folded = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    folded = re.sub(r"抽選(?:販売)?(?:では|は|で)(?:ありません|なく)", "", folded)
    if "抽選" in folded:
        return False
    # A bare release date, production plan or past purchase window is not an opening.
    return bool(re.search(
        rf"{_SALE}(?:の)?(?:受付|受け付け)?(?:を|が|は|に)?"
        r"(?:開始|スタート|受付中|受付期間|期間|受付締切|締切)", folded,
    ) or re.search(r"(?:予約|受注|注文)(?:受付|受け付け)(?:中|開始|期間|締切)", folded))


def _sale_period(text: str, base: date) -> tuple[date | datetime | None,
                                               date | datetime | None]:
    folded = re.sub(r"\s+", " ", normalize_text(unicodedata.normalize("NFKC", text)))
    start: date | datetime | None = None
    end: date | datetime | None = None
    labels = list(_LABEL.finditer(folded))
    for index, label in enumerate(labels):
        stop = labels[index + 1].start() if index + 1 < len(labels) else len(folded)
        after = folded[label.end():min(stop, label.end() + 180)]
        boundary = _BOUNDARY.search(after)
        if boundary:
            after = after[:boundary.start()]
        values = list(_DATE.finditer(after))
        closing = label.group().endswith(("締切", "締め切り", "締切り", "終了", "期限"))
        if closing:
            parsed = parse_first_datetime(after, base).value
            if parsed:
                end = parsed
            continue
        if values:
            parsed = parse_period_start(after, base).value
            if parsed and start is None:
                start = parsed
            if len(values) > 1 and re.search(r"~|から|より|→|-", after):
                end_base = parsed.date() if isinstance(parsed, datetime) else parsed or base
                end = parse_first_datetime(after[values[-1].start():], end_base).value
            elif parsed and (short_end := re.search(r"(?:~|→)\s*(\d{1,2}日[^。]*)", after)):
                end_base = parsed.date() if isinstance(parsed, datetime) else parsed
                end = parse_first_datetime(
                    f"{end_base.month}月{short_end.group(1)}", end_base,
                ).value
            elif parsed is None and re.search(r"まで|締切|終了", after):
                end = parse_first_datetime(after, base).value
        if "開始" in label.group() and start is None:
            # Support both 「予約開始:10/3」 and 「10/3 11時から予約開始」.
            before = folded[max(0, label.start() - 65):label.start()]
            before = re.split(r"[。!！\n]", before)[-1]
            dates = [] if _BOUNDARY.search(before) or "発売" in before else list(
                _DATE.finditer(before)
            )
            if dates:
                last_date = dates[-1]
                gap = before[last_date.end():].strip()
                if re.fullmatch(r"(?:から|より|に)?[、,:：]*", gap):
                    start = parse_first_datetime(before[last_date.start():], base).value
            elif "本日" in before or "本日" in after or "今日" in before:
                start = base
    return start, end


def period_has_ended(end: date | datetime | None, config: Config,
                     detected_on: date | None = None) -> bool:
    now = datetime.now(ZoneInfo(config.timezone))
    today = detected_on or now.date()
    if isinstance(end, datetime):
        return end.date() < today or (today == now.date() and end < now)
    return end is not None and end < today


def additional_sale_cases(
    text: str, url: str, source: SourceConfig, config: Config,
    retailer_id: str, retailer_name: str, *, source_url: str | None = None,
    announced_on: date | None = None, detected_on: date | None = None,
) -> list[LotteryCase]:
    if not additional_sale_signal(text):
        return []
    if _CLOSED.search(re.sub(r"\s+", "", text)):
        return []
    now = datetime.now(ZoneInfo(config.timezone))
    today = detected_on or now.date()
    base = announced_on or today
    start, end = _sale_period(text, base)
    if period_has_ended(end, config, detected_on):
        return []
    # Old mirrors without a still-open explicit window are not fresh opportunities.
    start_day = start.date() if isinstance(start, datetime) else start
    if announced_on and (today - announced_on).days > 1 and end is None and (
        start_day is None or start_day < today
    ):
        return []
    if start_day and start_day < today and end is None:
        return []
    mode = "made_to_order" if "受注" in text else "preorder" if "予約" in text else "sale"
    cases = []
    for gid, game in config.games.items():
        if gid not in config.active_game_ids or not source.supports(gid):
            continue
        for product in additional_matches(game, text):
            parts = product.canonical_product_key.split(":")
            item_id = parts[1] if parts[0] == "nonbox" and len(parts) > 1 else parts[0]
            if not any(item.id == item_id and item.monitor_sales
                       for item in game.additional_products):
                continue
            cases.append(LotteryCase(
                gid, retailer_id, retailer_name, product.product_name, product.product_category,
                product.canonical_product_key, start or base, url, source_url or url,
                source.source_tier, f"additional_product_{mode}_{'period' if start else 'seen'}",
                "high" if start else "medium",
                opportunity_kind=(OpportunityKind.DIRECT_SALE if start
                                  else OpportunityKind.DIRECT_SALE_SEEN),
                end_at=end,
            ).with_id())
    return cases
