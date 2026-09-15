"""公式画面で確認済みの案件を、受付期間内だけ補完する。"""

from datetime import datetime

from tcg_monitor.models import Config, LotteryCase, SourceConfig


def confirmed_lotteries(
    config: Config, sources: list[SourceConfig], now: datetime
) -> list[LotteryCase]:
    cases = []
    for source in sources:
        if not source.enabled:
            continue
        for record in source.parser_options.get("confirmed_lotteries", []):
            game_id = record["game_id"]
            if game_id not in config.active_game_ids or not source.supports(game_id):
                continue
            start = datetime.fromisoformat(record["start_at"])
            end = datetime.fromisoformat(record["end_at"])
            # タイムゾーン無し・逆転期間は設定ミス。推測して通知しない。
            if start.tzinfo is None or end.tzinfo is None or end < start:
                raise ValueError(f"Invalid confirmed lottery period: {source.id}")
            if not start <= now <= end:
                continue
            cases.append(LotteryCase(
                game_id=game_id,
                retailer_id=source.parser_options["retailer_id"],
                retailer_name=source.parser_options["retailer_name"],
                product_name=record["product_name"],
                product_category=record["product_category"],
                canonical_product_key=record["canonical_product_key"],
                start_at=start,
                end_at=end,
                official_url=record["official_url"],
                source_url=record["official_url"],
                source_tier=source.source_tier,
                extraction_method="user_verified_official_screenshot",
                confidence="high",
            ).with_id())
    return cases
