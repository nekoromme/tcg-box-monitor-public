"""確認済みの2026年10月10日重複だけを整理する。Discordへは送信しない。"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from tcg_monitor.cli import (
    _calendar_payload_hash,
    _cleanup_duplicate_lottery_events,
    _lottery_description,
    _opportunity_title_prefix,
    _prepare_cases,
    _remember_case,
)
from tcg_monitor.config import load_config
from tcg_monitor.google_calendar import CalendarAdapter
from tcg_monitor.identity import OBSERVED_START_METHODS, is_pokemon_30th_cardset
from tcg_monitor.logging_config import log_event
from tcg_monitor.models import Config, LotteryCase, OpportunityKind, SourceTier, stable_url_identity
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

REPAIR_KEY = "lottery_duplicates_20261010"
SOCIAL_REFERENCE_REPAIR_KEY = "lottery_social_reference_duplicates_20261010"
FULLCOMP_POST = "https://x.com/fc_sendaieki/status/2108806066981282193"
MORIOKA_FORM = "https://t.co/2uqpB26XsS"
MORIOKA_POST_IDS = {"2108220330569584791", "2108397146928226791", "2108728929368633617"}


def _case(row: dict[str, Any]) -> LotteryCase:
    fields = dict(row)
    for name in ("start_at", "end_at", "result_at"):
        value = fields.get(name)
        if value:
            fields[name] = (datetime.fromisoformat(str(value)) if len(str(value)) > 10
                            else date.fromisoformat(str(value)))
    fields["source_tier"] = SourceTier(fields["source_tier"])
    fields["opportunity_kind"] = OpportunityKind(fields.get("opportunity_kind", "lottery"))
    return LotteryCase(**fields)


def repair(state: MonitorState, calendar: CalendarAdapter, config: Config) -> int:
    maintenance = state.data.setdefault("maintenance", {})
    if maintenance.get(REPAIR_KEY, {}).get("status") == "complete":
        return 0
    selected = []
    for case_id, row in state.data["seen_cases"].items():
        if (row.get("game_id") != "pokemon_card"
                or row.get("canonical_product_key") != "pokemon_30th_cardset"
                or row.get("opportunity_kind", "lottery") != "lottery"):
            continue
        fullcomp = row.get("retailer_id") == "fullcomp" and row.get("source_url") == FULLCOMP_POST
        morioka = (row.get("retailer_id") == "batoloco_morioka"
                   and row.get("official_url") == MORIOKA_FORM
                   and str(row.get("source_url", "")).rsplit("/", 1)[-1] in MORIOKA_POST_IDS)
        if not (fullcomp or morioka):
            continue
        if fullcomp and str(row.get("end_at", ""))[:10] == "2026-10-16":
            # 元投稿の完全な本文と画像にある応募締切は12日23:59。
            # 発売日16日を借りた、この既知の履歴だけを補正し原本も残す。
            state.data.setdefault("verified_metadata_corrections", {})[case_id] = {
                "reason": "truncated_body_borrowed_release_date_from_image",
                "verified_source_url": FULLCOMP_POST,
                "original_record": dict(row),
                "correct_end_at": "2026-10-12T23:59:00+09:00",
            }
            row["end_at"] = "2026-10-12T23:59:00+09:00"
        selected.append(_case(row))
    if not selected:
        return 0
    prepared, _ = _prepare_cases(state, selected)
    now = datetime.now(UTC)
    for case in prepared:
        # 配信済み履歴を引き継ぐ。初めて見た応募を通知済みにする用途には使わない。
        if not state.delivered(f"lottery:started:{case.case_id}"):
            raise RuntimeError("確認済み重複の通知履歴を引き継げませんでした")
        _remember_case(state, case)
        summary = _opportunity_title_prefix(case, config) + case.retailer_name + "／" + (
            case.product_name
        )
        description = _lottery_description(case, now, config)
        sync_key = f"lottery:{case.case_id}"
        known = state.data["calendar_sync"].get(sync_key, {})
        kept = calendar.reconcile(
            "lottery", state.calendar_case_identity(case.case_id), summary, case.start_at,
            description, known_event_id=known.get("event_id"),
        )
        if kept.get("status") not in {"inserted", "updated", "unchanged"}:
            raise RuntimeError("残す抽選予定を確認できませんでした")
        state.mark_calendar_synced(sync_key, _calendar_payload_hash(
            summary, case.start_at, description,
        ), kept)
        _cleanup_duplicate_lottery_events(state, calendar, case, summary, description)
    maintenance[REPAIR_KEY] = {
        "status": "complete", "completed_at": now.isoformat(),
        "case_ids": [case.case_id for case in prepared],
        "discord_notifications": 0,
    }
    state.save()
    log_event(phase="verified_lottery_repair", outcome="complete", repair=REPAIR_KEY,
              campaigns=len(prepared), discord_notifications=0)
    return len(prepared)


def repair_social_route_duplicates(
    state: MonitorState, calendar: CalendarAdapter, config: Config,
) -> int:
    """同一投稿をリンク有無で保存した実履歴を、通知を送らずに引き継ぐ。"""
    maintenance = state.data.setdefault("maintenance", {})
    if maintenance.get(SOCIAL_REFERENCE_REPAIR_KEY, {}).get("status") == "complete":
        return 0
    groups: dict[tuple[str, str, str, str, str], list[LotteryCase]] = defaultdict(list)
    for row in state.data["seen_cases"].values():
        if (not is_pokemon_30th_cardset(str(row.get("game_id") or ""),
                                     str(row.get("canonical_product_key") or ""))
                or row.get("extraction_method") not in OBSERVED_START_METHODS):
            continue
        case = _case(row)
        groups[(case.game_id, case.retailer_id, case.opportunity_kind.value,
                case.application_round, stable_url_identity(case.source_url))].append(case)
    selected = []
    for rows in groups.values():
        merged, _ = merge_lotteries(rows)
        if (len(merged) < len(rows)
                and all(state.delivered(f"lottery:started:{case.case_id}") for case in rows)):
            selected.extend(rows)
    if not selected:
        return 0
    prepared, _ = _prepare_cases(state, selected)
    now = datetime.now(UTC)
    for case in prepared:
        if not state.delivered(f"lottery:started:{case.case_id}"):
            raise RuntimeError("同一投稿の通知履歴を引き継げませんでした")
        _remember_case(state, case)
        summary = _opportunity_title_prefix(case, config) + case.retailer_name + "／" + (
            case.product_name
        )
        description = _lottery_description(case, now, config)
        key = f"lottery:{case.case_id}"
        known = state.data["calendar_sync"].get(key, {})
        result = calendar.reconcile(
            "lottery", state.calendar_case_identity(case.case_id), summary, case.start_at,
            description, known_event_id=known.get("event_id"),
        )
        if result.get("status") not in {"inserted", "updated", "unchanged"}:
            raise RuntimeError("同一投稿の抽選予定を確認できませんでした")
        state.mark_calendar_synced(key, _calendar_payload_hash(summary, case.start_at, description),
                                   result)
        _cleanup_duplicate_lottery_events(state, calendar, case, summary, description)
    maintenance[SOCIAL_REFERENCE_REPAIR_KEY] = {
        "status": "complete", "completed_at": now.isoformat(),
        "case_ids": [case.case_id for case in prepared], "discord_notifications": 0,
    }
    state.save()
    log_event(phase="verified_lottery_repair", outcome="complete",
              repair=SOCIAL_REFERENCE_REPAIR_KEY, campaigns=len(prepared),
              discord_notifications=0)
    return len(prepared)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("state", type=Path)
    parser.add_argument("--config", default="sites.yaml")
    args = parser.parse_args()
    state = MonitorState.load(args.state)
    calendar = CalendarAdapter()
    config = load_config(args.config)
    count = repair(state, calendar, config)
    count += repair_social_route_duplicates(state, calendar, config)
    print(f"verified_lottery_repair: complete campaigns={count} discord_notifications=0")
