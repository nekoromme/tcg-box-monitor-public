"""楽天ブックスの同日抽選を、4種類以上なら通知と予定の各1件へまとめる。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from tcg_monitor.discord import DiscordAdapter, split_discord_description
from tcg_monitor.google_calendar import CalendarAdapter
from tcg_monitor.identity import OBSERVED_START_METHODS
from tcg_monitor.logging_config import log_event
from tcg_monitor.models import Config, LotteryCase, OpportunityKind, SourceTier
from tcg_monitor.state import MonitorState

JST = ZoneInfo("Asia/Tokyo")
MIN_BATCH_SIZE = 4


def _date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.astimezone(JST).date() if value.tzinfo else value.date()
    return value


def _parse_date(value: object) -> date | datetime | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    raw = str(value)
    return datetime.fromisoformat(raw) if len(raw) > 10 else date.fromisoformat(raw)


def _format_when(value: date | datetime) -> str:
    if isinstance(value, datetime):
        local = value.replace(tzinfo=JST) if value.tzinfo is None else value.astimezone(JST)
        return local.strftime("%Y/%m/%d %H:%M")
    return value.strftime("%Y/%m/%d")


def rakuten_product_url(case: LotteryCase) -> str | None:
    """商品番号を数える。表示用の追跡指定や別表記で種類数を水増ししない。"""
    if (case.retailer_id != "rakuten_books"
            or case.opportunity_kind != OpportunityKind.LOTTERY
            or case.extraction_method in OBSERVED_START_METHODS):
        return None
    parts = urlsplit(case.official_url)
    match = re.fullmatch(r"/rb/(\d+)/?", parts.path)
    if parts.hostname != "books.rakuten.co.jp" or not match:
        return None
    return f"https://books.rakuten.co.jp/rb/{match[1]}/"


def _saved_case(case_id: str, record: dict[str, Any]) -> LotteryCase | None:
    if record.get("retailer_id") != "rakuten_books":
        return None
    try:
        start = _parse_date(record.get("start_at"))
        if start is None:
            return None
        return LotteryCase(
            game_id=str(record["game_id"]), retailer_id="rakuten_books",
            retailer_name=str(record.get("retailer_name") or "楽天ブックス"),
            product_name=str(record["product_name"]),
            product_category=str(record.get("product_category") or ""),
            canonical_product_key=str(record["canonical_product_key"]), start_at=start,
            official_url=str(record.get("official_url") or ""),
            source_url=str(record.get("source_url") or ""),
            source_tier=SourceTier(record.get("source_tier", "secondary")),
            extraction_method=str(record.get("extraction_method") or ""),
            confidence=str(record.get("confidence") or ""), case_id=case_id,
            opportunity_kind=OpportunityKind(record.get("opportunity_kind", "lottery")),
            end_at=_parse_date(record.get("end_at")),
            result_at=_parse_date(record.get("result_at")),
            application_round=str(record.get("application_round") or ""),
        )
    except (KeyError, ValueError, TypeError):
        log_event(phase="rakuten_batch", outcome="skipped", case_id=case_id,
                  reason_code="invalid_saved_case")
        return None


@dataclass(frozen=True)
class RakutenBatch:
    day: date
    cases: tuple[LotteryCase, ...]

    @property
    def internal_id(self) -> str:
        # 種類が増えても予定の識別子は同じ日付のままにする。
        return f"rakuten_books:{self.day.isoformat()}"

    @property
    def sync_key(self) -> str:
        return f"rakuten_batch:{self.day.isoformat()}"

    @property
    def urls(self) -> tuple[str, ...]:
        return tuple(sorted({url for case in self.cases if (url := rakuten_product_url(case))}))

    @property
    def when(self) -> date | datetime:
        # 同日でも開始時刻が違う場合、予定は最初の受付開始時刻に置く。
        # 時刻不明のものを含む場合は終日予定にし、勝手な時刻を補わない。
        if any(not isinstance(case.start_at, datetime) for case in self.cases):
            return self.day
        return min(case.start_at.replace(tzinfo=JST) if case.start_at.tzinfo is None
                   else case.start_at.astimezone(JST)
                   for case in self.cases if isinstance(case.start_at, datetime))

    @property
    def title(self) -> str:
        return f"【抽選】楽天ブックス／全{len(self.urls)}種"

    @property
    def description(self) -> str:
        # 商品説明を繰り返さず、日付と応募先だけをコンパクトに並べる。
        starts = sorted({_format_when(case.start_at) for case in self.cases})
        lines = ["受付開始（日本時間）: " + "、".join(starts), *self.urls]
        ends = {str(case.end_at) for case in self.cases}
        if len(ends) == 1 and self.cases[0].end_at is not None:
            lines.append("応募締切: " + _format_when(self.cases[0].end_at))
        else:
            lines.append("締切は各リンク先で確認")
        return "\n".join(lines)


def build_rakuten_batches(
    state: MonitorState, cases: list[LotteryCase], config: Config,
    today: date, *, include_saved: bool = True,
) -> list[RakutenBatch]:
    """取得が一部失敗しても、確認済みの同日商品とリンクを落とさない。"""
    known: dict[str, LotteryCase] = {}
    if include_saved:
        for case_id, record in state.data.get("seen_cases", {}).items():
            if isinstance(record, dict) and (saved := _saved_case(case_id, record)):
                known[case_id] = saved
    known.update({case.case_id: case for case in cases})
    grouped: dict[date, list[LotteryCase]] = {}
    for case in known.values():
        if case.game_id in config.active_game_ids and rakuten_product_url(case):
            grouped.setdefault(_date(case.start_at), []).append(case)
    last_day = today + timedelta(days=int(config.system.get("max_future_days", 365)))
    first_day = today - timedelta(days=max(0, int(
        config.system.get("lottery_late_detection_grace_days", 1),
    )))
    batches = []
    for day, items in sorted(grouped.items()):
        batch = RakutenBatch(day, tuple(sorted(items, key=lambda case: case.case_id)))
        still_open = any(case.end_at is not None and day <= today <= _date(case.end_at)
                         for case in items)
        if len(batch.urls) >= MIN_BATCH_SIZE and (first_day <= day <= last_day or still_open):
            batches.append(batch)
    return batches


def _cleanup_individual_events(
    state: MonitorState, calendar: CalendarAdapter, batch: RakutenBatch,
) -> None:
    """集約予定の作成成功後に、所有者を確認して元の商品別予定を整理する。"""
    sync = state.data.setdefault("calendar_sync", {})
    for case in batch.cases:
        key = f"lottery:{case.case_id}"
        record = sync.setdefault(key, {})
        if record.get("grouped_into") != batch.sync_key:
            event_id = str(record.get("event_id") or "")
            if event_id:
                result = calendar.delete_owned_event(
                    event_id, kind="lottery",
                    internal_id=state.calendar_case_identity(case.case_id),
                    expected_day=batch.day,
                )
                if result.get("status") not in {"deleted", "not_found", "retained_other_day"}:
                    raise RuntimeError(f"楽天ブックスの商品別予定の整理が未完了: {result}")
                # 旧版で同じ予定IDを使った過去の別表記も再作成しない。
                # 新しい応募日はgrouped_dayより後なら通常の処理に戻れる。
                for other_key, other in sync.items():
                    if other_key.startswith("lottery:") and other.get("event_id") == event_id:
                        other.update(grouped_into=batch.sync_key,
                                     grouped_day=batch.day.isoformat())
                log_event(phase="rakuten_batch_cleanup", outcome=result["status"],
                          case_id=case.case_id, event_id=event_id)
            record.update(grouped_into=batch.sync_key, grouped_day=batch.day.isoformat())
            state.save()
        # 商品別の履歴移行で残っていた余分な予定も同じ整理対象に含める。
        migration = state.data.get("case_id_migrations", {}).get(case.case_id, {})
        for duplicate in migration.get("duplicate_calendar_events", {}).values():
            if duplicate.get("status") in {"deleted", "not_found", "retained_other_day"}:
                continue
            result = calendar.delete_owned_event(
                str(duplicate["event_id"]), kind="lottery",
                internal_id=str(duplicate["internal_id"]),
                expected_day=batch.day,
            )
            if result.get("status") not in {"deleted", "not_found", "retained_other_day"}:
                raise RuntimeError(f"楽天ブックスの旧重複予定の整理が未完了: {result}")
            duplicate["status"] = result["status"]
            state.save()


def _resume_notification_parts(
    state: MonitorState, discord: DiscordAdapter, batch: RakutenBatch,
) -> int:
    """分割ごとの成功を保存し、失敗後は未送信の続きだけ送る。"""
    journal = state.data.setdefault("delivery_journal", {})
    progress = journal.get(f"{batch.sync_key}:notification", {})
    if progress.get("status") != "in_progress":
        return 0
    sent_count = 0
    for index, part in enumerate(progress["parts"], start=1):
        if part.get("status") == "complete":
            continue
        sent = discord.send(part["title"], part["description"])
        if sent.get("status") != "sent":
            raise RuntimeError("楽天ブックスの集約通知が送信されませんでした")
        timestamp = datetime.now(JST).isoformat()
        part.update(status="complete", updated_at=timestamp)
        progress["updated_at"] = timestamp
        for url in part["urls"]:
            key = f"{batch.sync_key}:url:{sha256(url.encode()).hexdigest()}"
            journal.setdefault(key, {"status": "complete", "updated_at": timestamp})
        # 最後の分割だけ失敗しても、成功した分を次の巡回で送らない。
        state.save()
        sent_count += 1
        log_event(phase="rakuten_batch_notification", outcome="sent", day=batch.day,
                  part=index, parts=len(progress["parts"]), products=len(part["urls"]))
    progress.update(status="complete", updated_at=datetime.now(JST).isoformat())
    state.save()
    return sent_count


def sync_rakuten_batch(
    state: MonitorState, calendar: CalendarAdapter, discord: DiscordAdapter,
    batch: RakutenBatch,
) -> None:
    sync = state.data.get("calendar_sync", {}).get(batch.sync_key, {})
    result = calendar.reconcile(
        "lottery_batch", batch.internal_id, batch.title, batch.when, batch.description,
        known_event_id=sync.get("event_id"),
    )
    if result.get("status") not in {"inserted", "updated", "unchanged"}:
        raise RuntimeError(f"楽天ブックスの集約予定を確認できませんでした: {result}")
    payload_hash = sha256(
        f"{batch.title}|{batch.when}|{batch.description}".encode(),
    ).hexdigest()
    state.mark_calendar_synced(batch.sync_key, payload_hash, result)
    # 通知側だけが失敗した後も、次回の一部取得で商品一覧を縮めない。
    for case in batch.cases:
        state.data["seen_cases"][case.case_id] = case.__dict__
    state.save()

    # 途中で失敗した通知は、当時の本文・分割番号のまま続きを送る。
    # 後から商品が増えても、未完了の本文を組み直して重複送信しない。
    journal = state.data.setdefault("delivery_journal", {})
    sent_parts = _resume_notification_parts(state, discord, batch)
    notified_urls = {
        url for url in batch.urls
        if state.delivered(f"{batch.sync_key}:url:{sha256(url.encode()).hexdigest()}")
        or any(rakuten_product_url(case) == url
               and state.delivered(f"lottery:started:{case.case_id}") for case in batch.cases)
    }
    pending_urls = set(batch.urls) - notified_urls
    if pending_urls:
        title = batch.title + (f"（追加{len(pending_urls)}種）" if notified_urls else "")
        # 追加通知には新しいURLだけを載せる。全URLは1件の予定に保持するので、
        # 大量の商品へ1種類が追加された時に前の一覧を何通も送り直さない。
        notification_description = "\n".join(
            line for line in batch.description.splitlines()
            if line not in batch.urls or line in pending_urls
        )
        descriptions = split_discord_description(notification_description)
        journal[f"{batch.sync_key}:notification"] = {
            "status": "in_progress", "updated_at": datetime.now(JST).isoformat(),
            "parts": [{
                "title": title + (f"・{index}/{len(descriptions)}" if len(descriptions) > 1
                                  else ""),
                "description": description,
                "urls": [url for url in batch.urls if url in description.splitlines()],
                "status": "pending",
            } for index, description in enumerate(descriptions, start=1)],
        }
        state.save()
        sent_parts += _resume_notification_parts(state, discord, batch)
    for url in batch.urls:
        key = f"{batch.sync_key}:url:{sha256(url.encode()).hexdigest()}"
        journal.setdefault(key, {"status": "complete", "updated_at": datetime.now(JST).isoformat()})
    for case in batch.cases:
        journal.setdefault(f"lottery:started:{case.case_id}", {
            "status": "complete", "updated_at": datetime.now(JST).isoformat(),
        })
    state.save()
    _cleanup_individual_events(state, calendar, batch)
    log_event(phase="rakuten_batch", outcome=result["status"],
              day=batch.day, products=len(batch.urls), case_records=len(batch.cases),
              notification="sent" if sent_parts else "already_delivered",
              new_products=len(pending_urls), sent_parts=sent_parts)


def already_grouped(state: MonitorState, case: LotteryCase) -> bool:
    """過去の別表記を含め、一度整理した商品別予定を再作成しない。"""
    record = state.data.get("calendar_sync", {}).get(f"lottery:{case.case_id}", {})
    return bool(record.get("grouped_into") and _date(case.start_at).isoformat()
                <= str(record.get("grouped_day") or ""))
