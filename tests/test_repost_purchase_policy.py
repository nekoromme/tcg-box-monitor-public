"""リポスト購入抽選を許可し、無料企画と店頭限定応募を混ぜない。"""

import json
from datetime import date
from html import escape
from pathlib import Path

import pytest
from freezegun import freeze_time

from tcg_monitor.config import load_config
from tcg_monitor.models import Release, SourceTier
from tcg_monitor.parsers.local_lottery import (
    _requires_disallowed_application,
    parse_yahoo_realtime,
)
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_great_yorozuya_morioka")
OBSERVED = json.loads((Path(__file__).parent / "fixtures" /
                       "yorozuya_heroines_repost_20261021.json").read_text())
STATUS = OBSERVED["source_url"]


def markup(body: str) -> str:
    return (f'<article><p class="Tweet_body">{escape(body)}</p>'
            f'<a href="{STATUS}">投稿</a>'
            '<img src="https://pbs.twimg.com/media/purchase-conditions.jpg"></article>')


def parse(body: str, image_text: str = ""):
    diagnostics = {}
    cases, _, alerts = parse_yahoo_realtime(
        markup(body), SOURCE.discovery_urls[0], SOURCE, CONFIG, date(2026, 10, 21),
        ocr_reader=lambda _urls: image_text, diagnostics=diagnostics,
    )
    return cases, alerts, diagnostics


@freeze_time("2026-10-21T12:00:00Z")
def test_reported_heroines_purchase_has_correct_dates_and_one_delivery(tmp_path):
    cases, alerts, diagnostics = parse(OBSERVED["body"], OBSERVED["image_text"])
    assert not alerts and "disallowed_application" not in diagnostics
    assert len(cases) == 1
    case = cases[0]
    assert case.game_id == "one_piece_card"
    assert "Heroines Edition vol.2" in case.product_name
    assert case.source_url == STATUS
    assert case.end_at == date(2026, 10, 27)
    # この店舗では結果発表通知は有効化していない。既存の対象店舗設定を維持する。
    assert case.result_at is None
    # 同じ投稿が複数経路・次の巡回に現れても既存の履歴を引き継ぐ。
    again = parse(OBSERVED["body"], OBSERVED["image_text"])[0][0]
    assert len(merge_lotteries([case, again])[0]) == 1
    state = MonitorState(tmp_path / "state.json")
    key = f"lottery:started:{case.case_id}"
    state.mark_delivered(key)
    assert state.delivered(f"lottery:started:{again.case_id}")


@pytest.mark.parametrize("text", [
    "フォロー＆リポスト 抽選で1BOXプレゼント",
    "RPキャンペーン 抽選応募受付中 プレ企画",
    "リツイートで応募 giveaway 1BOX",
    "抽選販売開始記念！1BOXを抽選で無料進呈",
    "引用リポスト 当選者に無料で1BOXを差し上げます",
    "購入権をプレゼント。さらに別の抽選で1BOXプレゼント",
    "応募は店頭に掲示されたQRコードから",
    "当選者は店頭にて予約をしてください。発売日に受取",
])
def test_giveaways_and_two_visit_entries_stay_excluded(text):
    assert _requires_disallowed_application(text)


@pytest.mark.parametrize("text", [
    "当アカウントをフォロー ②このポストをリポスト 抽選販売",
    "フォロー＆RT 抽選予約受付開始",
    "引用リポストで購入権を抽選でプレゼント",
    "購入権利のプレゼント。当選者は店頭で購入",
    "購入権の抽選です。プレゼントではございません。",
    "抽選販売 プレゼント企画ではありません。",
    "抽選販売 送料無料 応募無料",
])
def test_paid_purchase_and_negative_giveaway_wording_are_allowed(text):
    assert not _requires_disallowed_application(text)


@pytest.mark.parametrize("in_image", [False, True])
def test_giveaway_conditions_in_body_or_image_cannot_become_sale(in_image):
    body = OBSERVED["body"]
    gift = "抽選で1BOXプレゼント"
    cases, alerts, diagnostics = parse(
        body if in_image else body + gift,
        OBSERVED["image_text"] + gift if in_image else OBSERVED["image_text"],
    )
    assert not cases and not alerts
    assert diagnostics["disallowed_application"] == 1


def test_vague_repost_draw_without_purchase_evidence_is_not_notified():
    body = ('ワンピースカード「Heroines Edition vol.2」1BOX 抽選応募受付中 '
            'このポストをリポスト 10月27日 応募締切')
    cases, alerts, diagnostics = parse(body, "応募条件：このポストをリポスト")
    assert not cases and not alerts
    assert diagnostics["repost_without_purchase_evidence"] == 1


def test_purchase_evidence_can_be_in_image_instead_of_body():
    body = ('ワンピースカード「Heroines Edition vol.2」1BOX 抽選応募受付中 '
            'このポストをリポスト 10月27日 応募締切')
    cases, alerts, _ = parse(body, OBSERVED["image_text"])
    assert len(cases) == 1 and not alerts


def test_failed_image_read_is_pending_until_purchase_conditions_can_be_verified():
    pending = {}
    diagnostics = {}

    def unavailable(_urls):
        raise RuntimeError("temporary image failure")

    cases, _, alerts = parse_yahoo_realtime(
        markup(OBSERVED["body"]), SOURCE.discovery_urls[0], SOURCE, CONFIG,
        date(2026, 10, 21), ocr_reader=unavailable, ocr_pending=pending,
        diagnostics=diagnostics,
    )
    assert not cases and not alerts
    assert diagnostics["repost_ocr_pending"] == 1
    assert STATUS in pending
    recovered, _, _ = parse_yahoo_realtime(
        markup(OBSERVED["body"]), SOURCE.discovery_urls[0], SOURCE, CONFIG,
        date(2026, 10, 21), ocr_reader=lambda _urls: OBSERVED["image_text"],
        ocr_pending=pending,
    )
    assert len(recovered) == 1 and STATUS not in pending


@freeze_time("2026-10-28T12:00:00Z")
def test_closed_repost_purchase_is_not_backfilled_as_new():
    diagnostics = {}
    cases, _, alerts = parse_yahoo_realtime(
        markup(OBSERVED["body"]), SOURCE.discovery_urls[0], SOURCE, CONFIG,
        date(2026, 10, 28), diagnostics=diagnostics,
    )
    assert not cases and not alerts
    assert diagnostics["application_ended"] == 1


def test_actual_image_ocr_uses_official_catalog_when_series_prefix_is_omitted():
    record = dict(OBSERVED["official_release"])
    record["release_date"] = date.fromisoformat(record["release_date"])
    record["source_tier"] = SourceTier(record["source_tier"])
    release = Release(**record)
    diagnostics = {}
    cases, _, alerts = parse_yahoo_realtime(
        markup(OBSERVED["body"]), SOURCE.discovery_urls[0], SOURCE, CONFIG,
        date(2026, 10, 21), ocr_reader=lambda _urls: OBSERVED["observed_ocr"],
        known_releases=[release], diagnostics=diagnostics,
    )
    assert len(cases) == 1 and not alerts
    assert cases[0].game_id == "one_piece_card"
    assert cases[0].end_at == date(2026, 10, 27)
    assert "Heroines Edition vol.2" in cases[0].product_name
    assert "unclassified_lottery" not in diagnostics
