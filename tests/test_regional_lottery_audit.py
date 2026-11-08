"""近隣監視の実例。募集画像の当選者向け注意事項で受付を落とさない。"""
import json
from dataclasses import replace
from datetime import date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.cli import _lottery_description, _lottery_discord_description
from tcg_monitor.config import load_config
from tcg_monitor.models import Release, SourceTier
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.source_priority import merge_lotteries

FIXTURE = json.loads((Path(__file__).parent / "fixtures" /
                      "pokedou_kitakami_30th_20261106.json").read_text())
CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_pokedou_kitakami")


def parse(body, image_text, detected=date(2026, 11, 8), source=SOURCE, body_html=None):
    body_markup = body_html or f'<p class="Tweet_body">{escape(body)}</p>'
    html = (f'<article>{body_markup}'
            f'<a href="{FIXTURE["source_url"]}">投稿</a>'
            f'<img src="{escape(FIXTURE["image_url"])}"></article>')
    record = dict(FIXTURE['official_release'])
    record['release_date'] = date.fromisoformat(record['release_date'])
    record['source_tier'] = SourceTier(record['source_tier'])
    diagnostics = {}
    cases, _, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, CONFIG, detected,
        ocr_reader=lambda _: image_text, known_releases=[Release(**record)],
        diagnostics=diagnostics,
    )
    return cases, alerts, diagnostics


def test_observed_poor_ocr_still_preserves_paid_entry_and_confirmed_deadline():
    cases, alerts, diagnostics = parse(FIXTURE['body'], FIXTURE['observed_ocr'])
    assert len(cases) == 1 and not alerts
    assert 'closed_or_result_notice' not in diagnostics
    case = cases[0]
    assert case.game_id == 'pokemon_card'
    assert '30th CELEBRATION' in case.product_name
    assert case.end_at == datetime(2026, 11, 12, 23, 59, tzinfo=ZoneInfo('Asia/Tokyo'))
    assert '受付開始日: 不明' in _lottery_description(case, datetime.now())
    assert '開始日時不明' in _lottery_discord_description(case)
    repeated = parse(FIXTURE['body'], FIXTURE['observed_ocr'])[0][0]
    assert len(merge_lotteries([case, repeated])[0]) == 1


def test_next_post_with_readable_deadline_does_not_need_confirmed_override():
    source = replace(SOURCE, parser_options={
        k: v for k, v in SOURCE.parser_options.items() if k != 'confirmed_application_ends'
    })
    cases, alerts, _ = parse(FIXTURE['body'], FIXTURE['image_transcription'], source=source)
    assert len(cases) == 1 and not alerts
    assert cases[0].end_at == datetime(2026, 11, 12, 23, 59, tzinfo=ZoneInfo('Asia/Tokyo'))


def test_expired_entry_is_not_revived():
    assert not parse(FIXTURE['body'], FIXTURE['observed_ocr'], date(2026, 11, 13))[0]


@pytest.mark.parametrize('body', [
    '当選者の方へのお知らせ。30th CELEBRATION抽選販売分のみとなります。',
    '抽選販売の応募方法 フォロー＆リポスト さらに1BOXプレゼント！',
    '抽選販売の応募方法 フォロー＆リポスト 店頭に掲示のQRコードから応募',
])
def test_results_giveaways_and_two_visit_entries_remain_excluded(body):
    assert not parse(body, FIXTURE['image_transcription'])[0]


def test_actual_yahoo_hashtags_do_not_replace_product_with_store_name():
    cases, alerts, _ = parse(
        FIXTURE['body'], FIXTURE['observed_ocr'], body_html=FIXTURE['yahoo_body_html'],
    )
    assert len(cases) == 1 and not alerts
    assert cases[0].product_name == '拡張パック「30th CELEBRATION」'


def test_explicit_winner_notice_cannot_be_revived_by_repeated_entry_instructions():
    body = '当選者のお知らせ。' + FIXTURE['body']
    assert not parse(body, FIXTURE['image_transcription'])[0]
