from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

JP_TZ = ZoneInfo("Asia/Tokyo")
WD = "月火水木金土日"
_PERIOD_DATE = re.compile(
    r"(?:(?:20\d{2})[/.年])?\d{1,2}[/.月]\d{1,2}日?"
    r"(?:[()][月火水木金土日][()])?"
)


@dataclass(frozen=True)
class DateParseResult:
    value: datetime | date | None
    month_only: str | None = None
    warnings: tuple[str, ...] = ()


def normalize_text(text: str) -> str:
    table = str.maketrans(
        {
            "０": "0",
            "１": "1",
            "２": "2",
            "３": "3",
            "４": "4",
            "５": "5",
            "６": "6",
            "７": "7",
            "８": "8",
            "９": "9",
            "／": "/",
            "：": ":",
            "－": "-",
            "〜": "~",
            "～": "~",
            "（": "(",
            "）": ")",
        }
    )
    normalized = text.translate(table).replace("　", " ")
    # OCR can drop a range mark and concatenate "12時～20時" into
    # "12時20時". Restore the only valid interpretation before the
    # optional-minute parser can backtrack and treat the leading "2" as minutes.
    return re.sub(r"(?<=時)(?=\d{1,2}時)", "~", normalized)


def _date_with_nearby_year(month: int, day: int, base: date, explicit_year: str | None) -> date:
    """Infer an omitted year without turning an old post into a far-future date."""
    if explicit_year:
        return date(int(explicit_year), month, day)
    value = date(base.year, month, day)
    if (value - base).days < -180:
        value = value.replace(year=value.year + 1)
    elif (value - base).days > 180:
        value = value.replace(year=value.year - 1)
    return value


def _date_result(match: re.Match[str], base: date) -> DateParseResult:
    warnings: list[str] = []
    try:
        value = _date_with_nearby_year(
            int(match.group("m")),
            int(match.group("d")),
            base,
            match.groupdict().get("y"),
        )
    except ValueError:
        return DateParseResult(None, warnings=("invalid_calendar_date",))
    weekday = match.groupdict().get("w")
    if weekday and WD[value.weekday()] != weekday:
        warnings.append("weekday_date_mismatch")
    return DateParseResult(value, warnings=tuple(warnings))


def parse_first_datetime(text: str, base_date: date | None = None) -> DateParseResult:
    base = base_date or datetime.now(JP_TZ).date()
    normalized = normalize_text(text)
    timed_patterns = [
        r"(?:(?P<y>20\d{2})年)?(?P<m>\d{1,2})月(?P<d>\d{1,2})日"
        r"(?:[()](?P<w>[月火水木金土日])[()])?\s*"
        r"(?:(?P<ap>午前|午後|正午|昼))?\s*(?P<h>\d{1,2})時(?P<mi>\d{1,2})?分?",
        r"(?:(?P<y>20\d{2})[/.年])?(?P<m>\d{1,2})[/.月](?P<d>\d{1,2})日?"
        r"(?:[()](?P<w>[月火水木金土日])[()])?\s*"
        r"(?P<h>\d{1,2})[:：](?P<mi>\d{2})",
    ]
    exact_date_patterns = [
        r"(?:(?P<y>20\d{2})年)?(?P<m>\d{1,2})月(?P<d>\d{1,2})日"
        r"(?:[()](?P<w>[月火水木金土日])[()])?",
        r"(?P<y>20\d{2})[./](?P<m>\d{1,2})[./](?P<d>\d{1,2})"
        r"(?:[()](?P<w>[月火水木金土日])[()])?",
        r"(?<![\d.])(?:(?P<y>20\d{2})[./])?(?P<m>\d{1,2})[/.](?P<d>\d{1,2})日?"
        r"(?:[()](?P<w>[月火水木金土日])[()])?(?![.\d])",
    ]
    timed_matches = [
        (match.start(), pattern_index, match)
        for pattern_index, pattern in enumerate(timed_patterns)
        for match in re.finditer(pattern, normalized)
    ]
    exact_date_matches = [
        (match.start(), pattern_index, match)
        for pattern_index, pattern in enumerate(exact_date_patterns)
        for match in re.finditer(pattern, normalized)
    ]
    first_timed = min(timed_matches, key=lambda item: (item[0], item[1]), default=None)
    first_exact = min(
        exact_date_matches,
        key=lambda item: (item[0], item[1]),
        default=None,
    )

    # A range may omit the start time while spelling out only the deadline time,
    # for example "8月7日～8月10日21時まで".  The old implementation searched
    # timed values first and therefore returned the deadline.  Select the value
    # whose date appears first in the text; when both start at the same position,
    # keep the timed match so a real start time is not discarded.
    if first_timed and (not first_exact or first_timed[0] <= first_exact[0]):
        timed_match = first_timed[2]
        hour = int(timed_match.group("h"))
        am_pm = timed_match.groupdict().get("ap")
        if am_pm == "午後" and hour < 12:
            hour += 12
        if am_pm in {"正午", "昼"}:
            hour = 12
        try:
            inferred_date = _date_with_nearby_year(
                int(timed_match.group("m")),
                int(timed_match.group("d")),
                base,
                timed_match.groupdict().get("y"),
            )
            value = datetime(
                inferred_date.year,
                inferred_date.month,
                inferred_date.day,
                hour,
                int(timed_match.groupdict().get("mi") or 0),
                tzinfo=JP_TZ,
            )
        except ValueError:
            # Invalid OCR must not abort the whole source or turn a later
            # deadline into a guessed start by skipping to the next date.
            return DateParseResult(None, warnings=("invalid_datetime",))
        warnings: list[str] = []
        weekday = timed_match.groupdict().get("w")
        if weekday and WD[value.weekday()] != weekday:
            warnings.append("weekday_date_mismatch")
        return DateParseResult(value, warnings=tuple(warnings))

    if first_exact:
        return _date_result(first_exact[2], base)

    # Do not let 2026.08.22 backtrack into a false "2026-08" month-only match.
    if month_match := re.search(
        r"(?P<y>20\d{2})[.年](?P<m>\d{1,2})(?![.\d])月?",
        normalized,
    ):
        if not 1 <= int(month_match.group("m")) <= 12:
            return DateParseResult(None, warnings=("invalid_calendar_month",))
        return DateParseResult(
            None,
            month_only=(
                f"{month_match.group('y')}-{int(month_match.group('m')):02d}"
            ),
        )
    return DateParseResult(None)


def period_is_deadline_only(text: str, *, label_is_start: bool = False) -> bool:
    """Return whether a period scope publishes only its closing date.

    A heading such as ``応募期間`` is sometimes followed by just
    ``7月29日23:59まで``.  That date is a deadline, not an application start.
    Ranges remain valid even when OCR damages the separator, provided that two
    dates appear before the first closing marker.
    """

    if label_is_start:
        return False
    compact = re.sub(r"\s+", "", normalize_text(text))
    heading_marks = (":", "〗", "】", "〕", "］", "》", ")", "」", "』")
    while compact.startswith(heading_marks):
        compact = compact[1:]
    if compact.startswith(("~", "→")):
        return True

    dates = list(_PERIOD_DATE.finditer(compact))
    if not dates:
        return False
    first_date = dates[0]
    until = compact.find("まで", first_date.end())
    closing_word_positions = [
        position
        for word in ("締切", "期限", "終了")
        if (position := compact.find(word)) >= 0
    ]
    if until < 0 and not closing_word_positions:
        return False

    segment_end = until if until >= 0 else len(compact)
    segment = compact[:segment_end]
    dates_in_segment = list(_PERIOD_DATE.finditer(segment))
    has_start_or_range = any(marker in segment for marker in ("~", "から", "より", "→"))
    return len(dates_in_segment) < 2 and not has_start_or_range


def parse_period_start(
    text: str,
    base_date: date | None = None,
    *,
    label_is_start: bool = False,
) -> DateParseResult:
    """Parse a period start without mistaking a lone deadline for it."""

    if period_is_deadline_only(text, label_is_start=label_is_start):
        return DateParseResult(None, warnings=("application_deadline_without_start",))
    return parse_first_datetime(text, base_date)
