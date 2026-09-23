"""Extract a published result date only for retailers without dependable email results."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from tcg_monitor.japanese_datetime import normalize_text, parse_first_datetime

RESULT_REMINDER_RETAILERS = frozenset({"yamada_denki", "furuichi", "kids_republic"})
_LABEL = re.compile(r"(?:抽選結果発表(?:日|日時)?|当選(?:結果)?発表(?:日|日時)?|当落発表(?:日|日時)?|結果発表(?:日|日時)?|抽選結果確認(?:開始日)?)")
_NEXT_FIELD = re.compile(r"(?:応募|申込|受付|発売|購入|受取|支払|入金|引換|販売|当選者のみ|落選者)\s*(?:期間|開始|締切|期限|日|について|への|には)")


def published_result_date(
    text: str, start_at: date | datetime, end_at: date | datetime | None = None
) -> date | datetime | None:
    """Ignore a result label if its own field has no date or precedes applications."""
    normalized = normalize_text(text)
    start_day = start_at.date() if isinstance(start_at, datetime) else start_at
    end_day = (end_at.date() if isinstance(end_at, datetime) else end_at) or start_day
    for label in _LABEL.finditer(normalized):
        scope = normalized[label.end():label.end() + 100]
        # A later application/release date must never become the result date.
        boundary = _NEXT_FIELD.search(scope)
        if boundary:
            scope = scope[:boundary.start()]
        scope = scope.split("\n", 1)[0] if "\n" in scope else scope
        parsed = parse_first_datetime(scope, end_day)
        value = parsed.value
        if value is None or parsed.warnings:
            continue
        result_day = value.date() if isinstance(value, datetime) else value
        if end_day <= result_day <= end_day + timedelta(days=365):
            return value
    return None
