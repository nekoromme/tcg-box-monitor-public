from dataclasses import replace
from datetime import datetime

from tcg_monitor.config import load_config
from tcg_monitor.confirmed_lotteries import confirmed_lotteries
from tcg_monitor.parsers.premium_bandai import parse_nyuka_now_lottery_summary
from tcg_monitor.parsers.retailer_lottery import parse_retailer_lottery_detail


def test_confirmed_famima_period_and_game_switch() -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "famima_online_lottery")
    now = datetime.fromisoformat("2026-09-15T15:48:00+09:00")
    cases = confirmed_lotteries(config, [source], now)
    assert len(cases) == 1
    assert cases[0].canonical_product_key == "OP-18"
    assert cases[0].end_at == datetime.fromisoformat("2026-09-21T23:59:00+09:00")
    assert not confirmed_lotteries(config, [], now)
    assert not confirmed_lotteries(config, [replace(source, enabled=False)], now)
    assert not confirmed_lotteries(
        replace(config, enabled_game_ids=frozenset({"pokemon_card"})), [source], now
    )
    for stamp in ("2026-09-15T09:59:00+09:00", "2026-09-22T00:00:00+09:00"):
        assert not confirmed_lotteries(config, [source], datetime.fromisoformat(stamp))


def test_famima_actual_reservation_heading_and_fullwidth_code() -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "famima_online_lottery")
    html = """
    <h1>【抽選商品】ワンピースカードゲーム ブースターパック【ＯＰ－１８】</h1>
    <p>予約開始日：2026/09/15(火) 10:00</p>
    <p>予約終了日：2026/09/21(月) 23:59</p>
    <p>お受け取り期間：2026/11/28(土)～12/11(金)</p>
    <p>抽選発表日：2026/09/24(木)</p>
    """
    cases, _, alerts = parse_retailer_lottery_detail(
        html, "https://famima-online.family.co.jp/item?itemCode=100162663879694780",
        source, config,
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].canonical_product_key == "OP-18"
    assert cases[0].start_at == datetime.fromisoformat("2026-09-15T10:00:00+09:00")


def test_famima_onepiece_summary_fallback() -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "nyuka_now_fullcomp_livepocket")
    html = """
    <h2>抽選・予約応募受付中のストア</h2><h3>ファミマオンライン</h3>
    <table>
    <tr><th>対象商品</th><td>ワンピースカードゲーム ブースターパック【OP-18】</td></tr>
    <tr><th>開始日</th><td>2026年9月15日(火)10:00</td></tr>
    </table>
    """
    cases, _, alerts = parse_nyuka_now_lottery_summary(
        html, "https://nyuka-now.com/archives/97393", source, config,
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "famima_online"
    assert cases[0].game_id == "one_piece_card"
