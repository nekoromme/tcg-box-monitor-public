"""限定系列の実商品、通常商品の除外、既存履歴、公式通販の取得経路を確認する。"""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tcg_monitor.additional_products import additional_matches
from tcg_monitor.classifier import classify_product
from tcg_monitor.cli import _lottery_description, _lottery_discord_description, _remember_case
from tcg_monitor.config import ConfigError, _additional_products, load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.identity import lottery_dedupe_key
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.parsers.pokemon_center import parse_pokemon_center_lottery
from tcg_monitor.parsers.yugioh_event_lottery import EVENT_INDEX, discover_yugioh_event_urls
from tcg_monitor.parsers.yugioh_official import parse_yugioh_official_products
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
NAME = "神を超えたしもべ－青眼の究極竜 デュエルセット"
URL = "https://www.yugioh-card.com/japan/event/ycsj/tokyo2026/"
SOURCE = next(s for s in CONFIG.sources if s.id == "yugioh_official_products")
HTML = Path("tests/fixtures/yugioh_event_web_lottery.html").read_text()


@pytest.mark.parametrize(("game_id", "name"), [
    ("pokemon_card", "スペシャルBOX「ポケモンセンタートウホク」"),
    ("pokemon_card", "拡張パック「熱風のアリーナ」ポケモンセンターセット"),
    ("pokemon_card", "35周年記念カードセット ピカチュウ"),
    ("one_piece_card", "ONE PIECEカードゲーム PREMIUM CARD COLLECTION -FILM RED-"),
    ("one_piece_card", "ONE PIECEカードゲーム 3rd ANNIVERSARY SET"),
    ("dragon_ball_fusion_world", "フュージョンワールド 2nd ANNIVERSARY SET"),
    ("yu_gi_oh", NAME),
    ("yu_gi_oh", "デュエルセット WCS2026"),
    ("yu_gi_oh", "ORIGINAL ARTWORK DUEL SET - 海馬編 -"),
])
def test_card_bearing_families_remain_non_box_targets(game_id: str, name: str) -> None:
    product = classify_product(CONFIG.games[game_id], name, name)
    assert product.is_target and not product.is_box
    assert product.canonical_product_key  # 調査済み商品は系列より優先する固定キー。


@pytest.mark.parametrize(("game_id", "name"), [
    ("pokemon_card", "スターターセットMEGA メガゲンガーex"),
    ("pokemon_card", "プレミアムデッキセット 別の商品"),
    ("pokemon_card", "ポケモンセンターセット"),
    ("one_piece_card", "プレミアムカードコレクション"),
    ("yu_gi_oh", "開催記念デュエルセット"),
    ("yu_gi_oh", "神を超えたしもべ－青眼の究極竜 デュエルセット用スリーブ"),
    ("yu_gi_oh", "神を超えたしもべ－青眼の究極竜 デュエルセット プレイマット単体"),
    ("lorcana", "ギフトセット"),
    ("gundam_card", "スタートデッキ"),
])
def test_ordinary_products_and_supplies_are_not_promoted(game_id: str, name: str) -> None:
    assert not classify_product(CONFIG.games[game_id], name, name).is_target


def test_shared_anniversary_title_is_bound_to_its_game() -> None:
    text = "ONE PIECEカードゲーム 3rd ANNIVERSARY SET 抽選販売"
    assert additional_matches(CONFIG.games["one_piece_card"], text)
    assert not additional_matches(CONFIG.games["dragon_ball_fusion_world"], text)
    assert not additional_matches(CONFIG.games["one_piece_card"], "3rd ANNIVERSARY SET")


def test_explicit_opt_out_overrides_broader_family() -> None:
    game = CONFIG.games["pokemon_card"]
    original = game.additional_products[0]
    modified = replace(game, additional_products=tuple(
        replace(item, enabled=False) if item.id == original.id else item
        for item in game.additional_products
    ))
    assert not classify_product(modified, original.name, original.name).is_target
    assert classify_product(game, original.name, original.name).canonical_product_key == original.id


def test_new_product_names_get_distinct_stable_keys() -> None:
    game = CONFIG.games["pokemon_card"]
    a = classify_product(game, "スペシャルBOX「ポケモンセンタートウホク」", "")
    b = classify_product(game, "スペシャルＢＯＸ ポケモンセンタートウホク", "")
    c = classify_product(game, "スペシャルBOX「ポケモンセンターフクオカ」", "")
    assert a.canonical_product_key == b.canonical_product_key
    assert a.canonical_product_key != c.canonical_product_key
    assert "「" not in a.product_name and "」" not in a.product_name


@freeze_time("2026-10-02 23:22:00+09:00")
def test_existing_social_parser_detects_new_non_box_family() -> None:
    source = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_seagull_common")
    posted = datetime(2026, 10, 2, 19, tzinfo=ZoneInfo("Asia/Tokyo"))
    status = (int(posted.timestamp() * 1000) - 1288834974657) << 22
    html = (f'<div class="Tweet_TweetContainer__test"><p>遊戯王 {NAME} 抽選受付開始 '
            '応募期間 10/2 19:00～10/14 23:59</p>'
            f'<a href="https://x.com/SeagullJP/status/{status}">投稿</a></div>')
    cases, releases, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, CONFIG, date(2026, 10, 2), known_releases=[],
    )
    assert not alerts and not releases and len(cases) == 1
    assert cases[0].product_category == "デュエルセット"
    assert len(merge_lotteries(cases + cases)[0]) == 1
    assert "相場・利益は未確認" in _lottery_description(cases[0], posted)
    assert "相場・利益は未確認" in _lottery_discord_description(cases[0])


@freeze_time("2026-10-02 23:22:00+09:00")
def test_set_contents_are_not_independent_boxes() -> None:
    source = next(s for s in CONFIG.sources if s.id == "pokemon_center_online")
    html = ('<main>ポケモンカードゲーム 拡張パック「熱風のアリーナ」ポケモンセンターセット '
            '抽選販売 応募期間 2026年10月2日19時～10月14日23時59分 '
            '内容物：拡張パック「熱風のアリーナ」2BOX デッキシールド デッキケース</main>')
    cases, _, alerts = parse_pokemon_center_lottery(html, "https://example.com/", source, CONFIG)
    assert not alerts and len(cases) == 1
    assert cases[0].product_category == "ポケモンセンターセット"


@freeze_time("2026-10-02 23:22:00+09:00")
def test_real_web_lottery_is_separate_from_participation_and_results() -> None:
    cases, releases, alerts = parse_yugioh_official_products(HTML, URL, SOURCE, CONFIG)
    assert not alerts and not releases and len(cases) == 2
    assert {case.application_round for case in cases} == {"1次", "2次"}
    assert cases[0].start_at == datetime(2026, 10, 2, 19, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[0].end_at == datetime(2026, 10, 14, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[1].start_at == datetime(2026, 11, 6, 19, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[1].end_at == datetime(2026, 11, 9, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert len({case.case_id for case in cases}) == 2
    assert len({lottery_dedupe_key(case) for case in cases}) == 2
    assert len(merge_lotteries(cases + cases)[0]) == 2
    assert all(
        case.official_url == "https://livepocket.jp/e/ycsjtokyo2026_duelset" for case in cases
    )


@freeze_time("2026-10-02 23:22:00+09:00")
def test_official_event_rounds_keep_separate_delivery_history(tmp_path: Path) -> None:
    cases, _, _ = parse_yugioh_official_products(HTML, URL, SOURCE, CONFIG)
    state = MonitorState.load(tmp_path / "state.json")
    _remember_case(state, cases[0])
    state.mark_delivered("lottery:started:" + cases[0].case_id)
    _remember_case(state, cases[1])
    assert len(state.data["seen_cases"]) == 2
    assert state.delivered("lottery:started:" + cases[0].case_id)
    assert not state.delivered("lottery:started:" + cases[1].case_id)


@freeze_time("2026-11-10 00:00:00+09:00")
def test_closed_rounds_do_not_reappear() -> None:
    assert not parse_yugioh_official_products(HTML, URL, SOURCE, CONFIG)[0]


def test_event_has_to_have_online_card_bearing_product_and_application_period() -> None:
    for missing in ("WEB抽選販売", "特典カードを同梱"):
        assert not parse_yugioh_official_products(HTML.replace(missing, ""), URL, SOURCE, CONFIG)[0]
    replaced = HTML.replace("抽選申し込み期間", "当選発表期間")
    cases, _, alerts = parse_yugioh_official_products(replaced, URL, SOURCE, CONFIG)
    assert not cases and alerts[0].reason_code == "yugioh_event_application_period_missing"


@freeze_time("2026-10-02 23:22:00+09:00")
def test_existing_official_monitor_discovers_and_parses_event_pages(tmp_path: Path) -> None:
    source = replace(SOURCE, discovery_urls=[EVENT_INDEX])
    config = replace(CONFIG, sources=[source])
    index = (f'<main><a href="{URL}">YCSJ TOKYO 2026</a>'
             '<a href="/japan/event/ycsj/tokyo2025/">2025</a>'
             '<a href="https://example.com/japan/event/ycsj/tokyo2026/">外部</a></main>')
    assert discover_yugioh_event_urls(index, EVENT_INDEX, date(2026, 10, 2)) == [URL]
    calls: list[str] = []

    class Fetcher:
        def fetch(self, url: str, **_kwargs: object) -> FetchResult:
            calls.append(url)
            assert url in {EVENT_INDEX, URL}
            return FetchResult(url, 200, index if url == EVENT_INDEX else HTML, {})

    state = MonitorState.load(tmp_path / "state.json")
    cases, releases, alerts = run_pipeline(
        config, monitor_state=state, http_fetcher=Fetcher(),  # type: ignore[arg-type]
    )
    assert calls == [EVENT_INDEX, URL]
    assert not alerts and not releases and len(cases) == 2
    assert state.data["monitors"][source.id]["outcome"] == "success"


@pytest.mark.parametrize("patch", [
    {"name_patterns": ["["]},
    {"name_patterns": ["カードセット"]},
    {"require_game_identity": "true"},
])
def test_invalid_family_configuration_fails(patch: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        _additional_products([{"id": "x", "name": "x", "category": "x", **patch}])
