"""2026/10/3の実投稿・通知履歴で、混入防止と仙台の取りこぼし防止を確認。"""

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup
from freezegun import freeze_time

from tcg_monitor.cli import _cleanup_confirmed_false_positive_cases
from tcg_monitor.config import load_config
from tcg_monitor.parsers.local_lottery import _tweet_body, parse_yahoo_realtime
from tcg_monitor.parsers.premium_bandai import parse_nyuka_now_fullcomp
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState
from tcg_monitor.store_scope import outside_store_scope

CONFIG = load_config("sites.yaml")
SOURCES = {source.id: source for source in CONFIG.sources}
FIXTURES = Path(__file__).parent / "fixtures"
KOJIMA = "https://x.com/PokeGetInfoMain/status/2105992441174302989"


def recovered_kojima():
    observed = json.loads((FIXTURES / "pokeget_kojima_ocr_cache.json").read_text())
    cache = {KOJIMA: observed["text"]}
    meta = {KOJIMA: observed["meta"]}
    # 本番で得た読取結果。更新日の行から先は引用された他店まとめ画像の文字。
    own_images_text = observed["text"].split("更新日 :", 1)[0].strip()
    reader = Mock(return_value=own_images_text)
    source = SOURCES["secondary_pokeget_news"]
    cases, _, alerts = parse_yahoo_realtime(
        (FIXTURES / "pokeget_kojima_quoted_roundup.html").read_text(),
        source.discovery_urls[0], source, CONFIG, date(2026, 10, 3),
        ocr_reader=reader, ocr_cache=cache, ocr_cache_meta=meta,
    )
    assert not alerts
    reader.assert_called_once()
    assert len(reader.call_args.args[0]) == 2  # 自分の添付2枚。アイコンと引用画像は含めない。
    assert cache[KOJIMA] == own_images_text  # 汚染された既存キャッシュも読み直す。
    assert {case.canonical_product_key.split(":")[0] for case in cases} == {
        "pokemon_30th_cardset",
    }
    merged, _ = merge_lotteries(cases)
    assert len(merged) == 1
    assert merged[0].start_at == date(2026, 10, 2)
    assert merged[0].end_at == date(2026, 10, 9)
    return merged[0]


@freeze_time("2026-10-03T06:47:00Z")
def test_actual_quoted_roundup_cannot_create_a_second_kojima_product() -> None:
    assert recovered_kojima().source_url == KOJIMA


def test_body_fallback_also_excludes_the_quoted_stores() -> None:
    soup = BeautifulSoup((FIXTURES / "pokeget_kojima_quoted_roundup.html").read_text(), "lxml")
    own_body = soup.select_one('p[class*="Tweet_body"]')
    assert own_body is not None
    own_body["class"] = "renamed_body"
    text = _tweet_body(soup)
    assert "コジマ" in text and "カードセット" in text
    assert "ポケセンオンライン" not in text and "ビックカメラ" not in text


@freeze_time("2026-10-03T06:47:00Z")
def test_existing_delivery_and_calendar_survive_cleanup_and_rerun(tmp_path: Path) -> None:
    state = MonitorState(tmp_path / "state.json")
    observed = json.loads((FIXTURES / "kojima_fullcomp_notification_state.json").read_text())
    state.data.update(observed)
    calendar = Mock()
    calendar.delete_owned_event.return_value = {"status": "deleted"}
    results = _cleanup_confirmed_false_positive_cases(
        state, calendar, CONFIG.system["runtime"]["confirmed_false_positive_cases"],
    )
    assert {item["retailer"] for item in results} == {"コジマ", "フルコンプ"}
    assert calendar.delete_owned_event.call_count == 3  # 誤商品の結果発表予定も削除する。
    case = recovered_kojima()
    key = f"lottery:started:{case.case_id}"
    before = state.data["delivery_journal"][key].copy()
    event = state.data["calendar_sync"][f"lottery:{case.case_id}"].copy()
    for _ in range(2):
        state.migrate_case_identity(case)
        assert state.delivered(key)
    assert state.data["delivery_journal"][key] == before
    assert state.data["calendar_sync"][f"lottery:{case.case_id}"] == event
    assert len(state.data["seen_cases"]) == 1
    assert set(state.data["calendar_sync"]) == {
        f"lottery:{case.case_id}", f"lottery_result:{case.case_id}",
    }
    assert not _cleanup_confirmed_false_positive_cases(
        state, calendar, CONFIG.system["runtime"]["confirmed_false_positive_cases"],
    )
    next_round = merge_lotteries([replace(case, start_at=date(2026, 11, 2), case_id="")])[0][0]
    assert state.migrate_case_identity(next_round) is None
    assert not state.delivered(f"lottery:started:{next_round.case_id}")


def test_cleanup_retains_history_until_both_calendar_events_are_removed(tmp_path: Path) -> None:
    state = MonitorState(tmp_path / "state.json")
    observed = json.loads((FIXTURES / "kojima_fullcomp_notification_state.json").read_text())
    state.data.update(observed)
    before = json.dumps(state.data, sort_keys=True)
    calendar = Mock()
    calendar.delete_owned_event.side_effect = [{"status": "deleted"}, {"status": "dry_run"}]
    confirmed = CONFIG.system["runtime"]["confirmed_false_positive_cases"]
    with pytest.raises(RuntimeError, match="誤結果予定"):
        _cleanup_confirmed_false_positive_cases(state, calendar, confirmed)
    assert json.dumps(state.data, sort_keys=True) == before
    calendar.delete_owned_event.side_effect = None
    calendar.delete_owned_event.return_value = {"status": "not_found"}
    assert len(_cleanup_confirmed_false_positive_cases(state, calendar, confirmed)) == 2


@freeze_time("2026-10-03T06:47:00Z")
def test_actual_fullcomp_list_excludes_other_stores_but_keeps_sendai_and_unknown() -> None:
    html = (FIXTURES / "fullcomp_no_sendai_20261003.html").read_text()
    stores = "横浜・秋葉原・渋谷東口・川崎・本厚木・池袋・秋葉原ラジオ会館・千葉"
    for content, count in (
        (html, 0),
        (html.replace(stores, "横浜・仙台駅前・千葉"), 1),
        (html.replace("対象店舗：" + stores, "対象店舗は公式で確認"), 1),
        (html.replace(stores, "横浜・千葉など"), 1),
    ):
        cases, _, alerts = parse_nyuka_now_fullcomp(
            content, "https://nyuka-now.com/archives/2459",
            SOURCES["nyuka_now_fullcomp_livepocket"], CONFIG,
        )
        assert not alerts
        assert len(cases) == count


@pytest.mark.parametrize(("text", "excluded"), [
    ("＜対象店舗＞フルコンプ横浜店 フルコンプ千葉店＜応募期間＞10/3〜10/6", True),
    ("対象店舗：横浜・仙 台駅前・千葉 詳細ページ", False),
    ("対象店舗：全店（仙台駅前店は対象外）", True),
    ("対象店舗：全国の全店舗", False),
    ("対象店舗：横浜・千葉…", False),
    ("対象店舗はリンク先でご確認ください", False),
    ("新品商品の抽選販売を開始しました！", False),
])
def test_store_filter_requires_explicit_complete_evidence(text: str, excluded: bool) -> None:
    assert outside_store_scope(CONFIG, "fullcomp", text, "source", "url") is excluded
    assert not outside_store_scope(CONFIG, "geo", text, "source", "url")


@freeze_time("2026-10-03T06:47:00Z")
def test_sendai_official_post_does_not_need_to_repeat_its_store_name() -> None:
    source = SOURCES["yahoo_realtime_fullcomp_sendai"]
    html = """<div class="Tweet_TweetContainer__observed">
    <p class="Tweet_body__observed">ポケモンカード 拡張パック「ストームエメラルダ」
    1BOX 抽選販売 応募期間10/3 10:00～10/6 11:59</p>
    <time><a href="https://x.com/fc_sendaieki/status/2105992441174302989">時刻</a></time>
    </div>"""
    cases, _, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, CONFIG, date(2026, 10, 3),
    )
    assert not alerts and len(cases) == 1
    assert cases[0].retailer_name == "フルコンプ仙台駅前店"
