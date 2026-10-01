from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.models import SourceTier
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_tsutaya_ichinoseki_store")
DETECTED = date(2026, 10, 1)
IMAGE = "https://pbs.twimg.com/media/official-notice.jpg"


def post(body="お知らせです。画像をご確認ください。", *, age=0, account=None, image=IMAGE):
    # 公開するテストでは実店舗の投稿を転載せず、投稿日時から架空のIDを作る。
    published = datetime(2026, 10, 1, 9, tzinfo=ZoneInfo("Asia/Tokyo")) - timedelta(days=age)
    status_id = str((int(published.timestamp() * 1000) - 1288834974657) << 22)
    account = account or SOURCE.parser_options["account"]
    url = f"https://x.com/{account}/status/{status_id}"
    html = f'<article><p class="Tweet_body__test">{body}</p>'
    html += f'<img src="{image}"><time><a href="{url}">投稿</a></time></article>'
    return html, url


NOTICE = (
    'ポケモンカードゲーム 拡張パック「監視テスト」1BOX 抽選販売 '
    '応募受付期間：2026年10月1日10時00分〜2026年10月3日23時59分'
)


def parse(html, text=NOTICE, **kwargs):
    return parse_yahoo_realtime(
        html, SOURCE.discovery_urls[1], kwargs.pop("source", SOURCE), CONFIG,
        detected_on=DETECTED, ocr_reader=kwargs.pop("ocr_reader", lambda _: text), **kwargs,
    )


def test_official_post_without_any_body_lottery_hint_reads_image_and_keeps_dates():
    html, url = post()
    diagnostics = {}
    cases, _, alerts = parse(html, diagnostics=diagnostics)
    assert not alerts
    assert len(cases) == 1
    assert cases[0].source_url == url
    assert cases[0].start_at.isoformat() == "2026-10-01T10:00:00+09:00"
    assert cases[0].end_at.isoformat() == "2026-10-03T23:59:00+09:00"
    assert cases[0].extraction_method == "yahoo_realtime_image_ocr_application_period"
    assert diagnostics["image_only_application_announcement"] == 1


def test_image_is_read_even_when_body_has_product_and_date_but_no_lottery_word():
    html, _ = post('ポケモンカードゲーム 拡張パック「監視テスト」 応募期間10月1日から')
    calls = []
    cases, _, alerts = parse(html, ocr_reader=lambda images: calls.append(images) or NOTICE)
    assert calls == [[IMAGE]]
    assert len(cases) == 1 and not alerts


@pytest.mark.parametrize("age", [0, 1])
def test_today_and_yesterday_official_images_are_checked(age):
    cases, _, alerts = parse(post(age=age)[0])
    assert len(cases) == 1 and not alerts


def test_old_or_nonofficial_posts_do_not_expand_image_reads():
    calls = []

    def reader(images):
        calls.append(images)
        return NOTICE

    assert not parse(post(age=3)[0], ocr_reader=reader)[0]
    assert not parse(post()[0], source=replace(SOURCE, source_tier=SourceTier.SECONDARY),
                     ocr_reader=reader)[0]
    assert not parse(post(account="unrelated_store")[0], ocr_reader=reader)[0]
    assert not calls


@pytest.mark.parametrize("text", ["営業時間 10時〜20時", ""])
def test_normal_or_textless_image_is_cached_without_repeated_warning(text):
    html, url = post()
    cache, meta, pending, calls = {}, {}, {}, []

    def reader(images):
        calls.append(images)
        return text
    for _ in range(2):
        cases, _, alerts = parse(html, ocr_reader=reader, ocr_cache=cache,
                                 ocr_cache_meta=meta, ocr_pending=pending)
        assert not cases and not alerts
    assert calls == [[IMAGE]]
    assert not pending
    assert meta[url]["image_urls"] == [IMAGE]


def test_changed_image_invalidates_a_negative_cache():
    html, url = post()
    cache, meta = {}, {}
    assert not parse(html, text="営業時間", ocr_cache=cache, ocr_cache_meta=meta)[0]
    new_image = "https://pbs.twimg.com/media/updated-notice.jpg"
    html = html.replace(IMAGE, new_image)
    cases, _, alerts = parse(html, ocr_cache=cache, ocr_cache_meta=meta)
    assert len(cases) == 1 and not alerts
    assert meta[url]["image_urls"] == [new_image]


@pytest.mark.parametrize("text", [
    NOTICE.replace("拡張パック「監視テスト」1BOX", "通常のスタートデッキ"),
    NOTICE.replace("抽選販売", "大会参加抽選"),
    NOTICE.replace("2026年10月3日", "2026年9月30日"),
    'ポケモンカードゲーム 拡張パック「監視テスト」1BOX 抽選結果 当選者販売期間10月1日から',
])
def test_image_does_not_bypass_deck_tournament_expired_or_result_filters(text):
    cases, _, _ = parse(post()[0], text=text)
    assert not cases


def test_image_only_ocr_failure_is_retried_and_never_creates_a_guessed_case():
    html, url = post('ポケモンカードゲーム 拡張パック「監視テスト」 お知らせ')
    pending = {}

    def failing_reader(_images):
        raise RuntimeError("画像の取得が一時的に失敗")

    for token, expected_alerts in [("run-1", 0), ("run-1", 0), ("run-2", 1)]:
        cases, _, alerts = parse(html, ocr_reader=failing_reader, ocr_pending=pending,
                                 ocr_attempt_token=token)
        assert not cases
        assert len(alerts) == expected_alerts
    assert pending[url]["attempts"] == 2
    cases, _, alerts = parse(html, ocr_pending=pending)
    assert len(cases) == 1 and not alerts and not pending


def test_image_only_cancellation_is_not_emitted_as_an_open_draw():
    cases, _, alerts = parse(post()[0], text=NOTICE + " 抽選販売中止")
    assert not cases
    assert [a.reason_code for a in alerts] == ["lottery_postponed_or_cancelled"]


@pytest.mark.parametrize("game,product", [
    ("one_piece_card", 'ONE PIECEカードゲーム ブースターパック「監視テスト」[OP-19] 1BOX'),
    ("dragon_ball_fusion_world", 'フュージョンワールド ブースターパック「監視テスト」[FB12] 1BOX'),
    ("yu_gi_oh", '遊戯王OCG ORIGINAL ARTWORK COLLECTION 1BOX'),
    ("lorcana", 'ディズニー・ロルカナ ブースターパック「監視テスト」1BOX'),
    ("gundam_card", 'ガンダムカードゲーム ブースターパック「監視テスト」[GD06] 1BOX'),
])
def test_image_only_notice_preserves_supported_games(game, product):
    text = product + ' 抽選販売 応募期間2026年10月1日10時00分〜10月3日23時59分'
    cases, _, alerts = parse(post()[0], text=text)
    assert not alerts
    assert [c.game_id for c in cases] == [game]


@freeze_time("2026-10-01 10:00:00+09:00")
def test_keyword_and_account_routes_share_ocr_and_one_case(monkeypatch, tmp_path):
    import tcg_monitor.pipeline as pipeline

    html, _ = post()
    calls = []

    def reader(images):
        calls.append(images)
        return NOTICE

    class Fetcher:
        def fetch(self, url, etag=None, last_modified=None):
            return FetchResult(url, 200, html, {})

    monkeypatch.setattr(pipeline, "read_image_text", reader)
    # このテストは2本の検索経路だけを対象にし、別のLINEフォームは混ぜない。
    source = replace(SOURCE, parser_options={
        key: SOURCE.parser_options[key] for key in ("account", "retailer_id", "retailer_name")
    })
    config = replace(CONFIG, sources=[source], system={
        **CONFIG.system, "social_account_fallback": False,
        "minimum_host_interval_seconds": 0, "max_parallel_hosts": 1,
    })
    state = MonitorState.load(tmp_path / "state.json")
    cases, _, alerts = run_pipeline(config, monitor_state=state, http_fetcher=Fetcher(),
                                    ocr_cache=state.data["ocr_cache"])
    assert len(cases) == 1 and not alerts
    assert calls == [[IMAGE]]
    assert state.data["monitors"][SOURCE.id]["outcome"] == "success"
