"""締切しか読めない公式投稿の仮登録と、初回検知日の固定を検証する。"""
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from tcg_monitor.cli import (
    _lottery_description,
    _lottery_discord_description,
    _opportunity_title_prefix,
    _reuse_first_detection_start,
)
from tcg_monitor.config import load_config
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.state import MonitorState


def _parse(detected=date(2026, 9, 15), image_text='', secondary=False):
    config = load_config('sites.yaml')
    source = next(s for s in config.sources if s.id == 'yahoo_realtime_dragonstar_online')
    if secondary:
        from tcg_monitor.models import SourceTier
        source = replace(source, source_tier=SourceTier.SECONDARY)
    # 実在投稿と混同しないため、テスト内だけの投稿IDを時刻から生成する。
    stamp = datetime(2026, 9, 15, 3, tzinfo=UTC)
    status_id = (int(stamp.timestamp() * 1000) - 1288834974657) << 22
    html = f'''
    <div class="Tweet_TweetContainer__test"><p class="Tweet_body__test">
    ドラゴンスター通販にてワンピースカードゲーム
    『蒼海の七傑』の抽選販売の受付をスタートしました🎉
    応募期間は9月17日までとなりますので、お探しのお客様はぜひお買い求めください😍
    ▼商品ページはこちらから▼
    </p><img src="https://rts-pctr.c.yimg.jp/dragonstar-test-poster">
    <time><a href="https://x.com/ds_ecommerce/status/{status_id}">9月15日</a></time></div>
    '''
    # OCRでは商品までは読めたが、開始日は欠落した状況を再現する。
    return parse_yahoo_realtime(
        html, source.discovery_urls[0], source, config, detected,
        lambda _urls: 'ワンピースカードゲーム 蒼海の七傑 [OP-14] 1BOX ' + image_text,
        {},
    )


def test_dragonstar_deadline_is_not_start_and_displays_unknown():
    cases, _, alerts = _parse()
    assert not alerts
    assert len(cases) == 1
    case = cases[0]
    assert case.start_at == date(2026, 9, 16)
    assert case.end_at == date(2026, 9, 17)
    assert case.extraction_method == 'yahoo_realtime_detected_next_day'
    assert case.confidence == 'low'
    assert '開始日不明' in _lottery_discord_description(case)
    assert '応募締切: 2026/09/17' in _lottery_discord_description(case)
    assert '受付開始日: 不明' in _lottery_description(case, datetime.now(UTC))
    assert '開始日不明' in _opportunity_title_prefix(case, load_config('sites.yaml'))


def test_readable_image_start_takes_priority():
    cases, _, alerts = _parse(image_text='抽選期間 2026年9月15日(火)～9月17日(木)')
    assert not alerts
    assert cases[0].start_at == date(2026, 9, 15)
    assert cases[0].extraction_method == 'yahoo_realtime_image_ocr_application_period'


@pytest.mark.parametrize('delivered', [False, True])
def test_first_detection_does_not_drift_even_if_delivery_is_delayed(tmp_path, delivered):
    first = _parse()[0][0]
    later = _parse(detected=date(2026, 9, 16))[0][0]
    state = MonitorState(tmp_path / 'state.json')
    state.data['seen_cases'][first.case_id] = first.__dict__
    if delivered:
        state.data['delivery_journal'][f'lottery:started:{first.case_id}'] = {
            'status': 'complete', 'updated_at': '2026-09-16T02:00:00+00:00',
        }
    assert _reuse_first_detection_start(state, later).start_at == date(2026, 9, 16)


def test_old_misread_start_is_repaired_from_first_delivery_in_japan_time(tmp_path):
    later = _parse(detected=date(2026, 9, 16))[0][0]
    state = MonitorState(tmp_path / 'state.json')
    state.data['seen_cases'][later.case_id] = {
        **later.__dict__, 'start_at': '2026-09-17',
        'extraction_method': 'yahoo_realtime_body_application_period',
    }
    state.data['delivery_journal'][f'lottery:started:{later.case_id}'] = {
        'status': 'complete', 'updated_at': '2026-09-14T16:00:00+00:00',
    }
    assert _reuse_first_detection_start(state, later).start_at == date(2026, 9, 16)


def test_closed_campaign_is_not_revived():
    assert not _parse(detected=date(2026, 9, 18))[0]


def test_secondary_deadline_only_post_is_still_excluded():
    assert not _parse(secondary=True)[0]
