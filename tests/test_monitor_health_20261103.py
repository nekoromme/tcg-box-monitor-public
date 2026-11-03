"""11/3の本番障害を、保存履歴と実際の公式投稿から再現する。"""
from __future__ import annotations

import json
from dataclasses import replace
from html import escape
from pathlib import Path

import pytest
from freezegun import freeze_time
from PIL import Image

from tcg_monitor.config import load_config
from tcg_monitor.fetching import PageFetcher
from tcg_monitor.fxembed import FxEmbedReader, timeline_url
from tcg_monitor.http_client import FetchResult, HttpFetcher
from tcg_monitor.ocr import _color_text_variant
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.pipeline import SourceMetrics, _healthy_fallbacks, run_pipeline
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
POSTS = json.loads(Path("tests/fixtures/health_notices_20261103.json").read_text())


def markup(post):
    return (f'<article><p>{escape(post["text"])}</p><a href="{escape(post["url"])}">投稿</a>'
            + ''.join(f'<img src="{escape(u)}"/>' for u in post['images']) + '</article>')


@pytest.mark.parametrize("post", POSTS, ids=lambda p: p["source_id"])
@freeze_time("2026-11-03T04:00:00Z")
def test_actual_result_or_stock_notice_does_not_retry_ocr(post):
    source = next(s for s in CONFIG.sources if s.id == post['source_id'])
    status = post['url'].split('?')[0]
    pending = {status: {'source_id': source.id, 'attempts': 5}}
    cases, releases, alerts = parse_yahoo_realtime(
        markup(post), source.discovery_urls[0], source, CONFIG, ocr_pending=pending,
        ocr_reader=lambda _: pytest.fail('本文で当選者・通常販売案内と判定できる'),
    )
    assert not cases and not releases and not alerts and not pending


@freeze_time("2026-11-03T04:00:00Z")
def test_mixed_result_and_new_lottery_is_still_read():
    post = {**POSTS[1], 'text': POSTS[1]['text'] +
            ' 新たにONE PIECEカードゲーム ブースターパック「神の支配」抽選受付開始。'
            '応募期間：11/3〜11/5。'}
    source = next(s for s in CONFIG.sources if s.id == post['source_id'])
    cases, _, _ = parse_yahoo_realtime(markup(post), source.discovery_urls[0], source, CONFIG,
                                      ocr_reader=lambda _: '')
    assert any(c.game_id == 'one_piece_card' for c in cases)


def test_rgb_transparency_does_not_crash_grayscale_ocr(tmp_path):
    original = tmp_path / 'original.png'
    Image.new('RGB', (12, 10), 'white').save(original, transparency=(255, 255, 255))
    destination = tmp_path / 'contrast.png'
    assert _color_text_variant(original, destination) == destination
    with Image.open(destination) as image:
        assert image.mode == 'L' and image.size == (24, 20)
        assert 'transparency' not in image.info


class Responses(HttpFetcher):
    def __init__(self, pages):
        super().__init__(minimum_host_interval=0)
        self.pages = pages
        self.calls = []

    def fetch(self, url, etag=None, last_modified=None):
        self.calls.append(url)
        status, body = self.pages[url]
        return FetchResult(url, status, body, {})


@pytest.mark.parametrize('unresolved', [False, True])
@freeze_time('2026-11-03T04:00:00Z')
def test_quiet_official_search_and_failed_fxembed_are_distinguished(tmp_path, unresolved):
    original = next(s for s in CONFIG.sources if s.id == 'yahoo_realtime_konami_style')
    source = replace(original, discovery_urls=original.discovery_urls[:1])
    root = timeline_url(source)
    text = ('新商品の抽選販売受付開始。詳細はこちら。' if unresolved else '本日も営業中です。')
    html = '<article><p>' + text + '</p><a href="https://x.com/konamistyle/status/'
    html += '2117104414586515803">投稿</a></article>'
    fetcher = Responses({source.discovery_urls[0]: (200, html), root: (404, 'not found')})
    config = replace(CONFIG, sources=[source], system={**CONFIG.system,
        'social_account_fallback': False, 'max_parallel_hosts': 1})
    state = MonitorState.load(tmp_path / 'state.json')
    _, _, alerts = run_pipeline(config, monitor_state=state, http_fetcher=fetcher)
    record = state.data['monitors'][source.id]
    assert record['outcome'] == ('failed' if unresolved else 'success')
    assert record['routes'][root]['status'] == 'fetch_failed'
    assert bool(alerts) is unresolved
    assert not state.data['fxembed_watermarks']


@pytest.mark.parametrize('pinned,reposted,complete', [(False,False,True),
                                                     (True,False,False),
                                                     (False,True,False)])
@freeze_time('2026-11-03T04:00:00Z')
def test_sparse_timeline_reaches_exact_previous_boundary(pinned, reposted, complete):
    source = next(s for s in CONFIG.sources if s.id == 'yahoo_realtime_tcgpit_sendai')
    root = timeline_url(source)
    sid = '2117241324600734184'
    post = {'id': sid, 'text': '本日も営業中',
            'author': {'screen_name': source.parser_options['account']},
            'is_pinned': pinned, 'reposted_by': 'another' if reposted else None}
    payload = json.dumps({'code': 200, 'results': [post], 'cursor': {'bottom': 'broken'}})
    fetcher = Responses({root: (200, payload), root + '&cursor=broken': (404, 'not found')})
    marks = {source.parser_options['account'].lower(): sid}
    reader = FxEmbedReader(PageFetcher(fetcher, lambda *_: pytest.fail('browser')), marks)
    reader.fetch(root, source)
    assert reader.reports[root]['complete'] is complete
    assert (len(fetcher.calls) == 1) is complete
    assert marks[source.parser_options['account'].lower()] == sid


def test_existing_geo_and_yamada_backups_require_actual_same_retailer_evidence():
    evidence = {}
    for source_id, game_id in [('snkrdunk_pokemon', 'pokemon_card'),
                               ('snkrdunk_onepiece', 'one_piece_card')]:
        metrics = SourceMetrics(source_id)
        for retailer in ['geo', 'yamada_denki']:
            metrics.retailer_ids.add(retailer)
            metrics.retailer_game_ids.add((retailer, game_id))
        evidence[source_id] = metrics
    outcomes = {'geo': False, 'yamada_denki': False,
                'snkrdunk_pokemon': True, 'snkrdunk_onepiece': True}
    covered = _healthy_fallbacks(CONFIG, outcomes, evidence=evidence)
    assert covered['geo'] == ['snkrdunk_pokemon']
    assert covered['yamada_denki'] == ['snkrdunk_pokemon', 'snkrdunk_onepiece']
    evidence['snkrdunk_onepiece'].retailer_game_ids.clear()
    assert 'yamada_denki' not in _healthy_fallbacks(CONFIG, outcomes, evidence=evidence)
    assert 'geo' not in _healthy_fallbacks(CONFIG, outcomes, evidence={})


@pytest.mark.parametrize('unresolved', [False, True])
@freeze_time('2026-11-03T09:00:00Z')
def test_actual_seagull_candidates_cover_optional_api_failure(tmp_path, unresolved):
    # 本番巡回で最後に残った警告。4投稿中2投稿を案件化できても404警告が残っていた。
    data = json.loads(Path('tests/fixtures/seagull_health_20261103.json').read_text())
    original = next(s for s in CONFIG.sources if s.id == 'yahoo_realtime_seagull_common')
    source = replace(original, discovery_urls=original.discovery_urls[:1])
    html = ''.join(markup(p) for p in data['posts'])
    if unresolved:
        # 正常な抽選を検出していても、別の投稿が未解決なら障害を隠さない。
        html += ('<article><p>新商品の抽選販売受付開始。詳細はこちら。</p>'
                 '<a href="https://x.com/SeagullJP/status/2117104414586515803">投稿</a>'
                 '</article>')
    root = timeline_url(source)
    fetcher = Responses({source.discovery_urls[0]: (200, html), root: (404, 'not found')})
    config = replace(CONFIG, sources=[source], system={**CONFIG.system,
        'social_account_fallback': False, 'max_parallel_hosts': 1})
    state = MonitorState.load(tmp_path / 'state.json')
    state.data['ocr_cache'] = data['ocr_cache']
    state.data['ocr_cache_meta'] = data['ocr_cache_meta']
    cases, _, alerts = run_pipeline(config, monitor_state=state, http_fetcher=fetcher,
                                    ocr_cache=state.data['ocr_cache'])
    assert cases
    record = state.data['monitors'][source.id]
    assert record['outcome'] == 'success'
    assert record['routes'][root]['status'] == 'fetch_failed'
    assert record['routes'][source.discovery_urls[0]]['diagnostics']['accepted_post'] > 0
    assert bool(alerts) is unresolved
