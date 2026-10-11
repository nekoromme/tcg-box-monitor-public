"""公開投稿の『本日開始』を取得日へずらさず、同じ募集の履歴を使う。"""
from dataclasses import replace
from datetime import UTC, date, datetime
from unittest.mock import Mock

import pytest

from tcg_monitor.cli import _cleanup_duplicate_lottery_events, _prepare_cases, _remember_case
from tcg_monitor.config import load_config
from tcg_monitor.models import SourceTier
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState


def parse_notice(text, detected=date(2026, 10, 11)):
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "yahoo_realtime_seagull_common")
    stamp = datetime(2026, 10, 9, 1, tzinfo=UTC)
    status = (int(stamp.timestamp() * 1000) - 1288834974657) << 22
    html = f'''<div class="Tweet_TweetContainer__test"><p class="Tweet_body__test">
    【抽選予約受付中】{text} ポケモンカードゲーム 30th CELEBRATION カードセット
    10/16発売予定。抽選予約を受付中。申し込みは店舗の案内をご確認ください。
    </p><time><a href="https://x.com/SeagullJP/status/{status}">10月9日</a></time></div>'''
    cases, _, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, config, detected,
    )
    assert not alerts and len(cases) == 1
    return cases[0]


@pytest.mark.parametrize(("text", "expected"), [
    ("本日抽選予約開始", date(2026, 10, 9)),
    ("本日より抽選申込みを開始", date(2026, 10, 9)),
    ("今日から応募受付開始", date(2026, 10, 9)),
    ("明日より抽選予約開始", date(2026, 10, 10)),
])
def test_relative_opening_is_anchored_to_post_date(text, expected):
    row = parse_notice(text)
    assert row.start_at == expected
    assert row.extraction_method == "yahoo_realtime_body_application_period"


@pytest.mark.parametrize("text", [
    "本日発売！抽選予約受付中", "本日まで応募受付中", "本日結果発表。抽選予約受付中",
])
def test_other_today_labels_are_not_application_starts(text):
    row = parse_notice(text)
    assert row.extraction_method != "yahoo_realtime_body_application_period"


def test_relative_opening_reuses_existing_summary_and_social_deliveries(tmp_path):
    actual = parse_notice("本日抽選予約開始")
    summary = replace(actual, start_at=date(2026, 10, 9), end_at=date(2026, 10, 11),
                      source_url="https://news.example/summary", official_url="https://shop.example/app",
                      source_tier=SourceTier.SECONDARY,
                      extraction_method="nyuka_now_priority_retailer_application_start").with_id()
    observed = replace(actual, start_at=date(2026, 10, 11),
                       extraction_method="yahoo_realtime_detected_open").with_id()
    state = MonitorState(tmp_path / "state.json")
    for index, raw in enumerate((summary, observed)):
        row = merge_lotteries([raw])[0][0]
        _remember_case(state, row)
        state.data["delivery_journal"][f"lottery:started:{row.case_id}"] = {
            "status": "complete", "updated_at": f"2026-10-09T01:00:0{index}+00:00",
        }
        state.data["calendar_sync"][f"lottery:{row.case_id}"] = {
            "event_id": f"synthetic-event-{index}", "status": "inserted",
        }
    calendar = Mock()
    calendar.reconcile.return_value = {"status": "unchanged", "event_id": "synthetic-event-0"}
    calendar.delete_owned_event.return_value = {"status": "deleted"}
    prepared, count = _prepare_cases(state, [actual])
    assert len(prepared) == 1 and count == 0
    assert len(state.data["seen_cases"]) == 1
    current = prepared[0]
    assert state.delivered(f"lottery:started:{current.case_id}")
    _cleanup_duplicate_lottery_events(state, calendar, current, "試験", "合成データ")
    assert calendar.delete_owned_event.call_args.args[0] == "synthetic-event-1"
    _remember_case(state, current)
    state.save()
    state = MonitorState.load(state.path)
    again, count = _prepare_cases(state, [parse_notice("本日抽選予約開始", date(2026, 10, 12))])
    assert len(again) == 1 and count == 0
    assert state.delivered(f"lottery:started:{again[0].case_id}")
