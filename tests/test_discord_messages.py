from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from tcg_monitor.cli import (
    _lottery_discord_description,
    _opportunity_title_prefix,
    _opportunity_uses_calendar,
    _release_discord_description,
)
from tcg_monitor.config import load_config
from tcg_monitor.discord import DiscordAdapter
from tcg_monitor.models import LotteryCase, Release, SourceTier


def test_lottery_discord_message_contains_only_user_facing_details() -> None:
    case = LotteryCase(
        game_id="pokemon_card",
        retailer_id="internal_retailer",
        retailer_name="テスト店",
        product_name="拡張パック「テスト」",
        product_category="拡張パック",
        canonical_product_key="internal_product_key",
        start_at=datetime(
            2026,
            7,
            26,
            10,
            30,
            tzinfo=ZoneInfo("Asia/Tokyo"),
        ),
        official_url="https://example.com/apply",
        source_url="https://example.com/source",
        source_tier=SourceTier.OFFICIAL,
        extraction_method="internal_parser",
        confidence="high",
        case_id="internal_case_id",
    )

    description = _lottery_discord_description(case)

    assert "店舗: テスト店" in description
    assert "受付開始: 2026/07/26 10:30" in description
    assert "応募ページ: https://example.com/apply" in description
    assert "内部" not in description
    assert "pokemon_card" not in description
    assert "Calendar結果" not in description


def test_amazon_open_invitation_is_labeled_as_seen_not_exact_start() -> None:
    case = LotteryCase(
        game_id="one_piece_card",
        retailer_id="amazon_jp",
        retailer_name="Amazon.co.jp",
        product_name="ブースターパック「世界最強の戦士」",
        product_category="ブースターパック",
        canonical_product_key="OP-17",
        start_at=date(2026, 7, 31),
        official_url="https://www.amazon.co.jp/dp/B0TESTOP17",
        source_url="https://snkrdunk.com/articles/32599/",
        source_tier=SourceTier.SECONDARY,
        extraction_method="snkrdunk_open_invitation_seen",
        confidence="low",
    ).with_id()

    description = _lottery_discord_description(case)

    assert "招待受付の確認日（開始日時不明）: 2026/07/31" in description
    assert "受付開始:" not in description
    assert "Amazon招待リクエストページ:" in description
    assert _opportunity_title_prefix(case, load_config("sites.yaml")) == (
        "【ワンピカードAmazon招待】"
    )
    assert not _opportunity_uses_calendar(case)


def test_social_amazon_invitation_has_the_same_user_facing_semantics() -> None:
    case = LotteryCase(
        game_id="one_piece_card",
        retailer_id="amazon_jp",
        retailer_name="Amazon.co.jp",
        product_name="エクストラブースター「Heroines Edition vol.2」[EB-05]",
        product_category="エクストラブースター",
        canonical_product_key="EB-05",
        start_at=date(2026, 8, 11),
        official_url="https://www.amazon.co.jp/dp/B0HB3JQ6P4",
        source_url="https://x.com/onepiecenyuka/status/2087125238991696167",
        source_tier=SourceTier.SECONDARY,
        extraction_method="yahoo_realtime_amazon_invitation_seen",
        confidence="medium",
    ).with_id()

    description = _lottery_discord_description(case)

    assert "招待受付の確認日（開始日時不明）: 2026/08/11" in description
    assert "Amazon招待リクエストページ: https://www.amazon.co.jp/dp/B0HB3JQ6P4" in (description)
    assert not _opportunity_uses_calendar(case)


def test_release_discord_message_hides_internal_fields() -> None:
    release = Release(
        game_id="one_piece_card",
        product_name="ブースターパック「テスト」",
        product_category="ブースターパック",
        canonical_product_key="OP-99",
        release_date=date(2026, 8, 22),
        release_month=None,
        official_url="https://example.com/product",
        source_url="https://example.com/source",
        source_tier=SourceTier.OFFICIAL,
        extraction_method="internal_parser",
        confidence="high",
        release_id="internal_release_id",
    )

    description = _release_discord_description(release, date_changed=True)

    assert "発売日: 2026/08/22" in description
    assert "公式ページ: https://example.com/product" in description
    assert "更新: 発売日が変更されました" in description
    assert "内部" not in description
    assert "one_piece_card" not in description
    assert "Calendar結果" not in description


def test_discord_transport_error_never_exposes_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    webhook = "https://discord.com/api/webhooks/" + "1234567890/abcdefghijklmnopqrstuvwxyz012345"

    def fail_post(*_args: object, **_kwargs: object) -> httpx.Response:
        request = httpx.Request("POST", webhook + "?wait=true")
        raise httpx.ConnectError("connection failed", request=request)

    monkeypatch.setattr(httpx, "post", fail_post)

    with pytest.raises(RuntimeError) as captured:
        DiscordAdapter(webhook_url=webhook).send("title", "description")

    message = str(captured.value)
    assert webhook not in message
    assert "abcdefghijklmnopqrstuvwxyz012345" not in message
    assert "Discord通知の送信に失敗しました" in message
