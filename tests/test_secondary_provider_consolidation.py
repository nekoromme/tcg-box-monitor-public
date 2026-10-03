from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from tcg_monitor.cli import (
    _lottery_description,
    _lottery_discord_description,
    _lottery_result_confirmation,
)
from tcg_monitor.config import ConfigError, load_config
from tcg_monitor.models import LotteryCase, SourceTier
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "secondary_onepiece_news")
STATUS = "2105067964882198698"


def post(body: str, status: str = STATUS, account: str = "onepiecenyuka") -> str:
    return (
        f'<div class="Tweet_TweetContainer__test"><p>{body}</p>'
        f'<a href="https://x.com/{account}/status/{status}">投稿</a></div>'
    )


def parse(html: str, **kwargs):
    return parse_yahoo_realtime(
        html, SOURCE.discovery_urls[0], SOURCE, CONFIG, date(2026, 9, 30), **kwargs,
    )


def test_only_user_approved_information_providers_are_live() -> None:
    enabled = [s for s in CONFIG.sources if s.enabled and s.source_tier == SourceTier.SECONDARY]
    assert {s.parser_options["information_provider"] for s in enabled} == {
        "onepiecenyuka", "nyuka_now", "snkrdunk", "PokeGetInfoMain",
    }
    assert len(enabled) == 5  # スニダンだけゲーム別の2経路。他は運営元別の共通経路。
    assert all("premier777aa" not in url for s in enabled for url in s.discovery_urls)


def test_one_feed_routes_separate_posts_and_rejects_multi_store_roundups() -> None:
    common = 'ワンピースカード「Heroines Edition vol.2【EB-05】」抽選販売 '
    period = '応募期間：9月29日23:00～10月1日23:59'
    html = (
        post("ヤマダ電機 " + common + period)
        + post("コジマ " + common + period, str(int(STATUS) + 1))
        + post("ヤマダ電機・コジマ 抽選受付中の店舗一覧 " + common + period,
               str(int(STATUS) + 2))
        + post("ヤマダ電機 " + common + period, str(int(STATUS) + 3), "unapproved_account")
    )
    diagnostics = {}
    cases, _, alerts = parse(html, diagnostics=diagnostics)
    assert not alerts
    assert {case.retailer_id for case in cases} == {"yamada_denki", "kojima"}
    assert len(cases) == 2
    assert diagnostics["ambiguous_retailer_post"] == 1


@pytest.mark.parametrize("earlier_variant", ["", "抽選結果はアプリのマイページで確認\n"])
def test_major_yamada_post_recovers_start_from_colored_app_image(earlier_variant: str) -> None:
    # 実際の画像で、赤い日時は読めても青い「応募期間」見出しが消えたケース。
    ocr = earlier_variant + (
        "抽選販売受付\n2026年10月31日発売\n"
        "ONE PIECE Heroines Edition vol.2【EB-05】 1BOX\n"
        "2026年9月29日(火)23:00から10月1日(木)23:59まで\n"
        "抽選結果はデジタル会員アプリで確認\n"
    )
    body = (
        'ヤマダ電機でワンピースカード「Heroines Edition vol.2【EB-05】」抽選受付が開始 '
        '応募期間：10月1日23時59分まで 当選発表：10月28日12時頃'
    )
    html = post(body).replace("</p>", '</p><img src="https://pbs.twimg.com/media/app.png">')
    cases, _, alerts = parse(
        html, ocr_cache={f"https://x.com/onepiecenyuka/status/{STATUS}": ocr},
    )
    assert not alerts
    assert len(cases) == 1
    case = cases[0]
    assert case.start_at == datetime(2026, 9, 29, 23, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert case.end_at == datetime(2026, 10, 1, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert case.result_at == datetime(2026, 10, 28, 12, tzinfo=ZoneInfo("Asia/Tokyo"))
    for description in (
        _lottery_discord_description(case),
        _lottery_description(case, datetime.now(ZoneInfo("Asia/Tokyo"))),
    ):
        assert 'アプリ →「店頭セール」→ 対象商品の抽選バナー' in description
        assert "公式アプリ案内（応募はアプリ内）" in description
        assert "公式応募ページ" not in description
    assert "アプリ内の募集内容・条件を確認" in _lottery_discord_description(case)
    summary_case = replace(case, official_url="https://snkrdunk.com/articles/123/")
    assert "公式アプリ案内（応募はアプリ内）: https://www.yamada-denki.jp/" in (
        _lottery_discord_description(summary_case)
    )
    result_note = _lottery_result_confirmation("yamada_denki", summary_case.official_url)
    assert 'マイページ →「抽選販売申込履歴」' in result_note
    assert "https://www.yamada-denki.jp/" in result_note


def test_closed_or_date_incomplete_posts_are_not_new_openings() -> None:
    for body in (
        "ヤマダ電機 ワンピースカード EB-05 抽選結果発表！販売期間：10/31～11/6",
        "ヤマダ電機 ワンピースカード EB-05 抽選受付開始 応募期間：10/1まで",
        "ヤマダ電機 ワンピースカード EB-05 抽選販売 応募期間：9/1～9/3まで",
    ):
        assert not parse(post(body))[0]


def test_unapproved_or_impersonating_secondary_account_cannot_be_enabled(tmp_path: Path) -> None:
    for spoof in (False, True):
        raw = yaml.safe_load(Path("sites.yaml").read_text())
        source = next(s for s in raw["sources"]
                      if s["id"] == "yahoo_realtime_yamada_onepiece_secondary")
        source["enabled"] = True
        if spoof:
            source["parser_options"]["information_provider"] = "onepiecenyuka"
        path = tmp_path / "sources.yaml"
        path.write_text(yaml.safe_dump(raw, allow_unicode=True))
        with pytest.raises(ConfigError, match="unapproved secondary|does not match approved"):
            load_config(path)


def test_yamada_provider_change_keeps_delivery_but_next_campaign_does_not(tmp_path: Path) -> None:
    old = LotteryCase(
        "one_piece_card", "yamada_denki", "ヤマダデンキ", "Heroines Edition vol.2【EB-05】",
        "BOX", "EB-05", date(2026, 9, 29),
        "https://www.yamada-denki.jp/service/pointservice/digital-kaiin.html",
        "https://x.com/premier777aa/status/2104972501919158561",
        SourceTier.SECONDARY, "yahoo_realtime_secondary_body_application_period", "medium",
    ).with_id()
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"][old.case_id] = {
        **asdict(old), "start_at": str(old.start_at),
    }
    state.mark_delivered(f"lottery:started:{old.case_id}")
    new = replace(old, source_url=f"https://x.com/onepiecenyuka/status/{STATUS}",
                  case_id="").with_id()
    assert state.migrate_case_identity(new) == old.case_id
    assert state.delivered(f"lottery:started:{new.case_id}")
    next_campaign = replace(new, start_at=date(2026, 10, 29),
                            source_url="https://x.com/onepiecenyuka/status/2205067964882198698",
                            case_id="").with_id()
    assert state.migrate_case_identity(next_campaign) is None
    assert not state.delivered(f"lottery:started:{next_campaign.case_id}")
