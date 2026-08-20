from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor import cli
from tcg_monitor.cli import (
    _lottery_discord_description,
    _opportunity_is_still_open,
    _opportunity_title_prefix,
)
from tcg_monitor.config import load_config
from tcg_monitor.models import LotteryCase, OpportunityKind, SourceTier
from tcg_monitor.parsers.official_retailers import (
    discover_official_retailer_urls,
    is_official_retailer_index,
    parse_konami_style,
    parse_onepiece_official_shop,
    parse_premium_bandai_dragonball,
    parse_takaratomy_mall,
)
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.source_priority import merge_lotteries


def _source(source_id: str):  # type: ignore[no-untyped-def]
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == source_id)
    return config, source


def _fixture(name: str) -> str:
    return Path("tests/fixtures", name).read_text(encoding="utf-8")


def test_added_official_store_indexes_follow_only_target_box_pages() -> None:
    cases = (
        (
            "onepiece_official_shop_news",
            "https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/",
            "onepiece_official_shop_news.html",
            [
                "https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/"
                "news/important/20260810.html"
            ],
        ),
        (
            "konami_style_yugioh",
            "https://www.konamistyle.jp/products/list.php?category_id=1001087&mode=search",
            "konami_style_yugioh.html",
            ["https://www.konamistyle.jp/products/detail.php?product_id=113536"],
        ),
        (
            "takaratomy_mall_lorcana",
            "https://takaratomymall.jp/shop/c/cLorcana/",
            "takaratomy_mall_lorcana.html",
            ["https://takaratomymall.jp/shop/g/g8000000207587/"],
        ),
        (
            "premium_bandai_dragonball",
            "https://p-bandai.jp/brand/b0062/",
            "premium_bandai_dragonball.html",
            ["https://p-bandai.jp/item/item-1000255641/"],
        ),
    )
    for source_id, url, fixture, expected in cases:
        config, source = _source(source_id)
        assert discover_official_retailer_urls(
            _fixture(fixture),
            url,
            source,
            config,
        ) == expected


def test_takaratomy_official_search_is_a_product_index() -> None:
    url = (
        "https://takaratomymall.jp/shop/goods/search.aspx?all=0&category=Lorcana"
        "&ismodesmartphone=on&optionalcategory=trading&release=0&search=true&sort=spd"
    )
    assert is_official_retailer_index("takaratomy_mall_lorcana", url)


def test_onepiece_official_shop_reads_national_article_and_application_link() -> None:
    config, source = _source("onepiece_official_shop_news")
    url = (
        "https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/"
        "news/important/20260810.html"
    )
    cases, _, alerts = parse_onepiece_official_shop(
        _fixture("onepiece_official_shop_news__20260810.html"),
        url,
        source,
        config,
    )

    assert not alerts
    assert len(cases) == 1
    case = cases[0]
    assert case.canonical_product_key == "OP-17"
    assert case.start_at == datetime(
        2026, 8, 12, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert case.end_at == datetime(
        2026, 8, 16, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert case.official_url == "https://parks2.bandainamco-am.co.jp/category/EL/"


def test_konami_style_separates_lottery_from_period_limited_direct_sale() -> None:
    config, source = _source("konami_style_yugioh")
    lottery_url = "https://www.konamistyle.jp/products/detail.php?product_id=113536"
    cases, _, alerts = parse_konami_style(
        _fixture("konami_style_yugioh__113536.html"),
        lottery_url,
        source,
        config,
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].opportunity_kind == OpportunityKind.LOTTERY
    assert cases[0].start_at == datetime(
        2026, 8, 5, 11, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert cases[0].end_at == datetime(
        2026, 8, 17, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo")
    )

    direct_html = """
    <main>
      <h1>遊戯王OCGデュエルモンスターズ LIMITED PACK GX</h1>
      <p>本商品は受注生産商品となります。</p>
      <p>注文受付期間：2026年8月14日（金）11時～2026年8月31日（月）23時59分</p>
      <p>1パック4枚入り、1ボックス10パック入り</p>
    </main>
    """
    direct, _, direct_alerts = parse_konami_style(
        direct_html,
        "https://www.konamistyle.jp/products/detail.php?product_id=113174",
        source,
        config,
    )
    assert not direct_alerts
    assert len(direct) == 1
    assert direct[0].opportunity_kind == OpportunityKind.DIRECT_SALE


def test_takaratomy_mall_ignores_banner_date_and_reports_only_buyable_box() -> None:
    config, source = _source("takaratomy_mall_lorcana")
    url = "https://takaratomymall.jp/shop/g/g8000000207587/"
    cases, _, alerts = parse_takaratomy_mall(
        _fixture("takaratomy_mall_lorcana__g8000000207587.html"),
        url,
        source,
        config,
        today=date(2026, 8, 11),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE_SEEN
    assert cases[0].start_at == date(2026, 8, 11)
    assert cases[0].start_at != date(2026, 8, 1)

    out_of_stock = _fixture(
        "takaratomy_mall_lorcana__g8000000207587.html"
    ).replace("○在庫あり", "×在庫なし").replace(
        "<button>カートに入れる</button>",
        "<button>在庫なし</button>",
    )
    absent, _, absent_alerts = parse_takaratomy_mall(
        out_of_stock,
        url,
        source,
        config,
        today=date(2026, 8, 11),
    )
    assert not absent
    assert not absent_alerts


def test_premium_bandai_dragonball_reads_active_booster_lottery() -> None:
    config, source = _source("premium_bandai_dragonball")
    url = "https://p-bandai.jp/item/item-1000255641/"
    cases, _, alerts = parse_premium_bandai_dragonball(
        _fixture("premium_bandai_dragonball__item-1000255641.html"),
        url,
        source,
        config,
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].canonical_product_key == "ST01"
    assert cases[0].start_at == datetime(
        2026, 8, 7, 11, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert cases[0].end_at == datetime(
        2026, 8, 20, 23, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert _opportunity_is_still_open(cases[0], date(2026, 8, 11))


def test_official_store_sources_run_end_to_end_with_fixtures() -> None:
    config = replace(
        load_config("sites.yaml"),
        system={
            **load_config("sites.yaml").system,
            "implausible_past_days": 5_000,
            "max_future_days": 5_000,
        },
    )
    cases, releases, alerts = run_pipeline(
        config,
        "tests/fixtures",
        {
            "onepiece_official_shop_news",
            "konami_style_yugioh",
            "takaratomy_mall_lorcana",
            "premium_bandai_dragonball",
        },
    )

    assert not releases
    assert not alerts
    assert {case.game_id for case in cases} == {
        "one_piece_card",
        "yu_gi_oh",
        "lorcana",
        "dragon_ball_fusion_world",
    }


def test_official_store_sources_respect_game_switch_before_fetching() -> None:
    config = replace(
        load_config("sites.yaml"),
        enabled_game_ids=frozenset({"pokemon_card"}),
    )
    cases, releases, alerts = run_pipeline(
        config,
        "tests/fixtures",
        {
            "onepiece_official_shop_news",
            "konami_style_yugioh",
            "takaratomy_mall_lorcana",
            "premium_bandai_dragonball",
        },
    )
    assert not cases
    assert not releases
    assert not alerts


def test_direct_sale_labels_do_not_call_an_ordinary_sale_a_lottery() -> None:
    config = load_config("sites.yaml")
    case = LotteryCase(
        "lorcana",
        "takaratomy_mall",
        "タカラトミーモール",
        "【BOX販売】ロルカナ テスト",
        "ブースターパック",
        "test",
        date(2026, 8, 11),
        "https://takaratomymall.jp/shop/g/gtest/",
        "https://takaratomymall.jp/shop/g/gtest/",
        SourceTier.OFFICIAL,
        "takaratomy_mall_first_seen_available",
        "medium",
        opportunity_kind=OpportunityKind.DIRECT_SALE_SEEN,
    ).with_id()

    assert _opportunity_title_prefix(case, config) == "【ロルカナ公式販売】"
    description = _lottery_discord_description(case)
    assert "販売を確認した日（開始日時不明）" in description
    assert "公式購入ページ" in description
    assert "受付開始" not in description


def test_new_opportunity_kind_preserves_old_lottery_ids_and_separates_sales() -> None:
    common = dict(
        game_id="yu_gi_oh",
        retailer_id="konami_style",
        retailer_name="KONAMI STYLE",
        product_name="ORIGINAL ARTWORK COLLECTION",
        product_category="ORIGINAL ARTWORK COLLECTION",
        canonical_product_key="original-artwork-collection",
        start_at=date(2026, 8, 5),
        official_url="https://www.konamistyle.jp/products/detail.php?product_id=1",
        source_url="https://www.konamistyle.jp/products/detail.php?product_id=1",
        source_tier=SourceTier.OFFICIAL,
        extraction_method="test",
        confidence="high",
    )
    legacy = LotteryCase(**common).with_id()
    explicit_lottery = LotteryCase(
        **common,
        opportunity_kind=OpportunityKind.LOTTERY,
    ).with_id()
    direct_sale = LotteryCase(
        **common,
        opportunity_kind=OpportunityKind.DIRECT_SALE,
    ).with_id()

    assert legacy.case_id == explicit_lottery.case_id
    assert direct_sale.case_id != legacy.case_id


def test_onepiece_new_article_and_existing_parks_source_merge_once() -> None:
    common = dict(
        game_id="one_piece_card",
        product_name="ブースターパック 世界最強の戦士【OP-17】",
        product_category="ブースターパック",
        canonical_product_key="OP-17",
        start_at=date(2026, 8, 12),
        source_tier=SourceTier.OFFICIAL,
        extraction_method="test",
        confidence="high",
    )
    national = LotteryCase(
        retailer_id="onepiece_official_shop",
        retailer_name="ONE PIECEカードゲーム公式ショップ",
        official_url="https://parks2.bandainamco-am.co.jp/category/EL/",
        source_url=(
            "https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/"
            "news/important/20260810.html"
        ),
        **common,
    ).with_id()
    local = LotteryCase(
        retailer_id="onepiece_official_shop_sendai",
        retailer_name="ONE PIECEカードゲーム公式ショップ 仙台店",
        official_url="https://parks2.bandainamco-am.co.jp/category/EL/sendai.html",
        source_url="https://parks2.bandainamco-am.co.jp/category/EL/",
        **common,
    ).with_id()

    merged, alerts = merge_lotteries([national, local])
    assert not alerts
    assert len(merged) == 1
    assert merged[0] == national


def test_first_seen_official_sale_sends_discord_without_fake_calendar_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    case = LotteryCase(
        "lorcana",
        "takaratomy_mall",
        "タカラトミーモール",
        "【BOX販売】ロルカナ テスト",
        "ブースターパック",
        "test",
        today,
        "https://takaratomymall.jp/shop/g/gtest/",
        "https://takaratomymall.jp/shop/g/gtest/",
        SourceTier.OFFICIAL,
        "takaratomy_mall_first_seen_available",
        "medium",
        opportunity_kind=OpportunityKind.DIRECT_SALE_SEEN,
    ).with_id()
    discord_calls: list[tuple[str, str]] = []

    class FakeCalendar:
        def upsert(self, *_args: object, **_kwargs: object) -> dict[str, str]:
            raise AssertionError("開始日時不明の在庫確認をCalendarへ登録してはいけません")

    class FakeDiscord:
        def send(self, message_title: str, description: str) -> dict[str, str]:
            discord_calls.append((message_title, description))
            return {"status": "sent"}

    monkeypatch.setattr(cli, "run_pipeline", lambda *_args, **_kwargs: ([case], [], []))
    monkeypatch.setattr(cli, "CalendarAdapter", FakeCalendar)
    monkeypatch.setattr(cli, "DiscordAdapter", FakeDiscord)
    state_path = tmp_path / "state.json"
    state = cli.MonitorState.load(state_path)
    state.mark_baseline()
    state.arm()
    state.data["enabled_game_ids"] = sorted(load_config("sites.yaml").games)
    state.save()

    assert cli.main(["--config", "sites.yaml", "--state", str(state_path), "run"]) == 0
    assert len(discord_calls) == 1
    assert discord_calls[0][0].startswith("【ロルカナ公式販売】")
    assert "販売を確認した日（開始日時不明）" in discord_calls[0][1]
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert f"lottery:{case.case_id}" not in saved["calendar_sync"]


def test_new_official_source_delivers_an_older_but_still_open_lottery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    case = LotteryCase(
        "dragon_ball_fusion_world",
        "premium_bandai",
        "プレミアムバンダイ",
        "フュージョンワールド STORY BOOSTER 01 [ST01]",
        "STORY BOOSTER",
        "ST01",
        today - timedelta(days=4),
        "https://p-bandai.jp/item/item-1000255641/",
        "https://p-bandai.jp/item/item-1000255641/",
        SourceTier.OFFICIAL,
        "premium_bandai_labelled_period",
        "high",
        end_at=today + timedelta(days=5),
    ).with_id()
    calendar_calls: list[str] = []
    discord_calls: list[str] = []

    class FakeCalendar:
        def upsert(
            self,
            _kind: str,
            internal_id: str,
            _summary: str,
            _when: date,
            _description: str,
        ) -> dict[str, str]:
            calendar_calls.append(internal_id)
            return {"status": "inserted", "event_id": "fake"}

    class FakeDiscord:
        def send(self, message_title: str, _description: str) -> dict[str, str]:
            discord_calls.append(message_title)
            return {"status": "sent"}

    monkeypatch.setattr(cli, "run_pipeline", lambda *_args, **_kwargs: ([case], [], []))
    monkeypatch.setattr(cli, "CalendarAdapter", FakeCalendar)
    monkeypatch.setattr(cli, "DiscordAdapter", FakeDiscord)
    state_path = tmp_path / "state.json"
    state = cli.MonitorState.load(state_path)
    state.mark_baseline()
    state.arm()

    assert cli.main(["--config", "sites.yaml", "--state", str(state_path), "run"]) == 0
    assert calendar_calls == [case.case_id]
    assert len(discord_calls) == 1
