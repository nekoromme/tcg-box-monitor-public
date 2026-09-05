from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from tcg_monitor.config import load_config
from tcg_monitor.models import (
    Config,
    GameConfig,
    GameId,
    GameSupport,
    SourceConfig,
    SourceTier,
)
from tcg_monitor.parsers.premium_bandai import parse_nyuka_now_lottery_summary
from tcg_monitor.parsers.retailer_lottery import (
    discover_retailer_lottery_urls,
    is_retailer_lottery_source,
    parse_retailer_lottery_detail,
    retailer_lottery_index_error,
)


def _config() -> Config:
    pokemon = GameConfig(
        GameId.POKEMON,
        "ポケモンカードゲーム",
        "ポケカ",
        "",
        "",
        "",
        "",
        ["ポケモンカードゲーム", "ポケモンカード", "ポケカ"],
        ["拡張パック", "強化拡張パック", "ハイクラスパック"],
        [r"(?i)\b1?BOX\b"],
        ["スターターセット", "スタートデッキ", "デッキ", "セット"],
    )
    one_piece = GameConfig(
        GameId.ONE_PIECE,
        "ONE PIECEカードゲーム",
        "ワンピカード",
        "",
        "",
        "",
        "",
        ["ONE PIECEカードゲーム", "ワンピースカード", "ワンピカード"],
        ["ブースターパック", "エクストラブースター", "プレミアムブースター"],
        [r"(?i)\b1?BOX\b", r"\[(?:OP|EB|PRB)-\d{2}\]"],
        ["スタートデッキ", "スターターデッキ", "デッキ", "セット"],
        [
            r"\b(?P<code>OP-\d{2})\b",
            r"\b(?P<code>EB-\d{2})\b",
            r"\b(?P<code>PRB-\d{2})\b",
        ],
    )
    dragon_ball = GameConfig(
        GameId.DRAGON_BALL,
        "ドラゴンボールスーパーカードゲーム フュージョンワールド",
        "ドラゴン",
        "",
        "",
        "",
        "",
        ["フュージョンワールド", "DBFW"],
        ["ブースターパック", "MANGA BOOSTER", "STORY BOOSTER"],
        [r"(?i)\b1?BOX\b", r"\[(?:FB|SB|ST)\d{2}\]"],
        ["スタートデッキ", "デッキ", "セット"],
        [r"\b(?P<code>FB\d{2})\b", r"\b(?P<code>SB\d{2})\b"],
    )
    return Config(
        2,
        "Asia/Tokyo",
        {},
        {
            "pokemon_card": pokemon,
            "one_piece_card": one_piece,
            "dragon_ball_fusion_world": dragon_ball,
        },
        {},
        [],
    )


def _source(
    source_id: str,
    games: tuple[str, ...],
    start_labels: list[str] | None = None,
) -> SourceConfig:
    configured = next(
        (source for source in load_config("sites.yaml").sources if source.id == source_id),
        None,
    )
    if configured is not None:
        return replace(
            configured,
            supported_games={game_id: GameSupport.VERIFIED for game_id in games},
            start_labels=start_labels or configured.start_labels,
        )
    return SourceConfig(
        source_id,
        source_id,
        SourceTier.OFFICIAL,
        {game_id: GameSupport.VERIFIED for game_id in games},
        ["lottery_discovery"],
        True,
        ["https://example.com"],
        start_labels or [],
    )


def test_famima_overseas_error_shell_is_monitor_failure() -> None:
    html = """
    <html><body><main>
      <h1>ファミマオンライン</h1>
      <p>海外からのアクセスは受け付けておりません。</p>
      <p>日本国内からご利用ください。</p>
    </main></body></html>
    """

    assert retailer_lottery_index_error(html, "famima_online_lottery") == (
        "ファミマオンラインがメンテナンス・地域制限のエラーページを返しました"
    )


def test_ministop_index_follows_box_lottery_and_skips_deck_set() -> None:
    html = """
    <main>
      <article><a href="/Form/Product/ProductDetail.aspx?pid=800001-01&amp;shop=0">
        【抽選応募】ポケモンカードゲーム MEGA 拡張パック
        「30th CELEBRATION」1BOX（30パック）
      </a></article>
      <article><a href="/Form/Product/ProductDetail.aspx?pid=800002-01&amp;shop=0">
        【抽選応募】ポケモンカードゲーム MEGA 30th CELEBRATION
        プレミアムデッキセット エーフィ・ブラッキー
      </a></article>
    </main>
    """
    source = _source("ministop_online_lottery", ("pokemon_card",))

    assert discover_retailer_lottery_urls(
        html,
        source.discovery_urls[0],
        source,
        _config(),
    ) == [
        "https://online.ministop.co.jp/Form/Product/ProductDetail.aspx?pid=800001-01&shop=0"
    ]


def test_ministop_detail_parses_box_application_period() -> None:
    html = """
    <h1>【抽選応募】ONE PIECEカードゲーム
    ブースターパック 決戦の刻【OP-16】1BOX（24パック）</h1>
    <p>抽選応募受付期間：2026年7月24日（金）15時～
    2026年7月31日（金）15時まで</p>
    """
    source = _source("ministop_online_lottery", ("one_piece_card",))
    cases, releases, alerts = parse_retailer_lottery_detail(
        html,
        "https://online.ministop.co.jp/Form/Product/ProductDetail.aspx?pid=772754-01&shop=0",
        source,
        _config(),
    )

    assert not releases
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "ministop_online"
    assert cases[0].canonical_product_key == "OP-16"
    assert cases[0].start_at == datetime(
        2026, 7, 24, 15, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )


def test_ministop_campaign_page_uses_retailer_parser_without_being_index() -> None:
    source = _source("ministop_online_lottery", ("pokemon_card",))

    assert is_retailer_lottery_source(source)
    cases, releases, alerts = parse_retailer_lottery_detail(
        """
        <h1>ポケモンカードゲーム MEGA 30th CELEBRATION</h1>
        <p>プレミアムデッキセット エーフィ・ブラッキー抽選販売</p>
        <p>抽選応募受付期間 2026年9月2日（水）15時～2026年9月4日（金）15時</p>
        """,
        "https://online.ministop.co.jp/Page/pockemon.aspx",
        source,
        _config(),
    )
    assert not cases
    assert not releases
    assert not alerts


def test_namco_index_follows_only_sendai_and_natori_onepiece_boxes() -> None:
    html = """
    <ul>
      <li><a href="/category/EL/sendai.html">【仙台店】7/27・28【抽選申込】
      ONE PIECEカードゲーム『ブースターパック 決戦の刻【OP-16】』
      購入権チケット</a></li>
      <li><a href="/category/EL/natori.html">【宮城名取店】7/27・28【抽選申込】
      ONE PIECEカードゲーム『ブースターパック 決戦の刻【OP-16】』
      購入権チケット</a></li>
      <li><a href="/category/EL/tokyo.html">【東京店】同じ抽選 購入権
      ONE PIECEカードゲーム ブースターパック</a></li>
      <li><a href="/category/EL/sendai-event.html">【仙台店】大会抽選</a></li>
    </ul>
    """
    source = _source("namco_onepiece_official_shop_miyagi", ("one_piece_card",))
    assert discover_retailer_lottery_urls(
        html,
        "https://parks2.bandainamco-am.co.jp/category/EL/",
        source,
        _config(),
    ) == [
        "https://parks2.bandainamco-am.co.jp/category/EL/sendai.html",
        "https://parks2.bandainamco-am.co.jp/category/EL/natori.html",
    ]


def test_namco_detail_uses_application_start_and_store_identity() -> None:
    html = """
    <h1>【宮城名取店】7/27・28【抽選申込】 ONE PIECEカードゲーム
    『ブースターパック 決戦の刻【OP-16】』購入権チケット</h1>
    <p>事前抽選販売にて1BOX（24パック）まで販売いたします。</p>
    <dl><dt>申込開始</dt><dd>2026/07/18 17:00から</dd>
    <dt>申込終了</dt><dd>2026/07/21 23:59まで</dd>
    <dt>当選発表</dt><dd>2026/07/22 17:00</dd></dl>
    """
    source = _source(
        "namco_onepiece_official_shop_miyagi",
        ("one_piece_card",),
        ["申込開始"],
    )
    cases, releases, alerts = parse_retailer_lottery_detail(
        html,
        "https://parks2.bandainamco-am.co.jp/category/EL/natori.html",
        source,
        _config(),
    )
    assert not releases
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "onepiece_official_shop_miyagi_natori"
    assert cases[0].canonical_product_key == "OP-16"
    assert cases[0].start_at == datetime(2026, 7, 18, 17, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def test_itoyokado_index_and_detail_require_an_actual_box_lottery() -> None:
    index_html = """
    <h1>現在承り中の予約/抽選 一覧</h1>
    <article><a href="/shop/g/g4900000000001/">
    ポケモンカードゲーム MEGA 拡張パック「ストームエメラルダ」BOX
    </a></article>
    <article><a href="/shop/g/g4900000000002/">
    ポケモンカードゲーム スターターセットex
    </a></article>
    """
    source = _source("itoyokado_online_lottery", ("pokemon_card",))
    assert discover_retailer_lottery_urls(
        index_html,
        "https://iyec.itoyokado.co.jp/shop/e/eE4reslot/",
        source,
        _config(),
    ) == ["https://iyec.itoyokado.co.jp/shop/g/g4900000000001/"]

    detail_html = """
    <h1>ポケモンカードゲーム MEGA 拡張パック
    「ストームエメラルダ」BOX 抽選販売</h1>
    <p>抽選応募受付期間：2026年7月15日（水）10:00～
    2026年7月20日（月）23:59</p>
    <p>当選発表：2026年7月22日（水）</p>
    """
    cases, _, alerts = parse_retailer_lottery_detail(
        detail_html,
        "https://iyec.itoyokado.co.jp/shop/g/g4900000000001/",
        source,
        _config(),
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "itoyokado_online"
    assert cases[0].start_at == datetime(2026, 7, 15, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def test_dmm_detail_parses_onepiece_application_period() -> None:
    html = """
    <h1>【BOX販売】ONE PIECEカードゲーム ブースターパック
    「決戦の刻【OP-16】」抽選販売</h1>
    <p>抽選申し込み期間 2026年7月14日(火)15:00〜
    2026年7月21日(火)15:00</p>
    <p>1BOX（24パック入り）</p>
    """
    source = _source(
        "dmm_hobby_lottery",
        ("one_piece_card",),
        ["抽選申し込み期間"],
    )
    cases, _, alerts = parse_retailer_lottery_detail(
        html,
        "https://www.dmm.com/mono/hobby/-/detail/=/cid=test/",
        source,
        _config(),
    )
    assert not alerts
    assert cases[0].retailer_id == "dmm_tsuhan"
    assert cases[0].canonical_product_key == "OP-16"
    assert cases[0].start_at == datetime(2026, 7, 14, 15, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def test_hobbylink_index_follows_game_lottery_article_without_product_name() -> None:
    html = """
    <section>
      <a href="/hc/ja/articles/59743843810969-lottery">
      【抽選販売】ポケモンカードゲーム 抽選販売応募概要</a>
      <a href="/hc/ja/articles/123-maintenance">サイトメンテナンス</a>
    </section>
    """
    source = _source(
        "hobbylink_japan_lottery",
        ("pokemon_card", "one_piece_card"),
    )
    assert discover_retailer_lottery_urls(
        html,
        ("https://support.hlj.co.jp/hc/ja/sections/203939188-%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B"),
        source,
        _config(),
    ) == ["https://support.hlj.co.jp/hc/ja/articles/59743843810969-lottery"]


def test_hobbylink_detail_uses_article_date_when_page_only_publishes_deadline() -> None:
    html = """
    <article>
      <h1>【抽選販売】ポケモンカードゲーム 抽選販売応募概要</h1>
      <p>2026年07月15日 12:05</p>
      <h2>【抽選販売対象商品】</h2>
      <a href="https://www.hlj.co.jp/product/PKM-TRAINER.html">
      ポケモンカードゲーム MEGA プレミアムトレーナーボックス MEGA</a>
      <a href="https://www.hlj.co.jp/product/PKM-DREAM.html">
      ポケモンカードゲーム MEGA ハイクラスパック MEGAドリームex 1Box 10pcs</a>
      <a href="https://www.hlj.co.jp/product/PKM-STARTER.html">
      ポケモンカードゲーム MEGA スターターセットMEGA メガゲンガーex</a>
      <a href="https://www.hlj.co.jp/product/PKM-CARDSET.html">
      ポケモンカードゲーム MEGA スペシャルカードセット メガエルレイドex</a>
      <h2>【エントリー受付期間】</h2>
      <p>7月22日(水) 23時59分まで</p>
      <a href="https://forms.gle/example">応募フォームはこちら</a>
    </article>
    """
    source = _source(
        "hobbylink_japan_lottery",
        ("pokemon_card", "one_piece_card"),
        ["エントリー受付期間"],
    )
    cases, _, alerts = parse_retailer_lottery_detail(
        html,
        "https://support.hlj.co.jp/hc/ja/articles/59743843810969-lottery",
        source,
        _config(),
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "hobbylink_japan"
    assert cases[0].product_name.endswith("ハイクラスパック MEGAドリームex 1Box 10pcs")
    assert cases[0].start_at == datetime(2026, 7, 15, 12, 5, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[0].official_url == "https://forms.gle/example"
    assert cases[0].extraction_method == "retailer_article_published_open"


def test_hobby_search_follows_only_active_box_lottery_and_uses_detection_date() -> None:
    index_html = """
    <main>
      <article>
        <a href="/11390001">
          ポケモンカードゲーム MEGA 拡張パック
          「30th CELEBRATION」BOX
        </a>
        <span>抽選販売</span>
      </article>
      <article>
        <a href="/11390002">
          ポケモンカードゲーム MEGA スタートデッキ100
        </a>
        <span>抽選販売</span>
      </article>
    </main>
    """
    source = _source("hobby_search_lottery", ("pokemon_card",))
    assert discover_retailer_lottery_urls(
        index_html,
        "https://www.1999.co.jp/list/3352/7/1",
        source,
        _config(),
    ) == ["https://www.1999.co.jp/11390001"]

    detail_html = """
    <h1>ポケモンカードゲーム MEGA 拡張パック
    「30th CELEBRATION」 (トレーディングカード)</h1>
    <p>抽選販売</p>
    <button>抽選に応募する</button>
    <p>1BOX30パック</p>
    """
    cases, _, alerts = parse_retailer_lottery_detail(
        detail_html,
        "https://www.1999.co.jp/11390001",
        source,
        _config(),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "hobby_search"
    assert cases[0].start_at == datetime.now(ZoneInfo("Asia/Tokyo")).date()
    assert cases[0].extraction_method == "hobby_search_active_lottery_detected"
    assert cases[0].confidence == "medium"


def test_nyuka_now_recovers_current_dmm_onepiece_lottery() -> None:
    html = """
    <h2>抽選・予約応募受付中</h2>
    <h3>DMM通販</h3>
    <table>
      <tr>
        <th>対象商品</th>
        <td><ul>
          <li>ONE PIECEカードゲーム
          プレミアムブースター ONE PIECE CARD THE BEST vol.2【PRB-02】（BOX）</li>
          <li>ONE PIECEカードゲーム
          エクストラブースター EGGHEAD CRISIS【EB-04】（BOX）</li>
          <li>ONE PIECEカードゲーム
          ブースターパック 決戦の刻【OP-16】（BOX）</li>
        </ul></td>
      </tr>
      <tr><th>開始日</th><td>2026年8月10日(月)15:00</td></tr>
    </table>
    <a href="https://www.dmm.com/mono/hobby/-/detail/=/cid=test/">
      DMM通販の応募ページ
    </a>
    """
    source = _source(
        "nyuka_now_fullcomp_livepocket",
        ("pokemon_card", "one_piece_card"),
    )

    cases, releases, alerts = parse_nyuka_now_lottery_summary(
        html,
        "https://nyuka-now.com/archives/97393",
        source,
        _config(),
    )

    assert not releases
    assert not alerts
    assert {case.retailer_id for case in cases} == {"dmm_tsuhan"}
    assert {case.canonical_product_key for case in cases} == {
        "PRB-02",
        "EB-04",
        "OP-16",
    }
    assert {case.start_at.isoformat() for case in cases} == {"2026-08-10T15:00:00+09:00"}


def test_nyuka_now_recovers_current_famima_and_itoyokado_lotteries() -> None:
    html = """
    <article>
      <h2>抽選・予約応募受付中のストア</h2>
      <h3>ファミマオンライン</h3>
      <table>
        <tr><th>対象商品</th><td>ポケモンカード MEGA 拡張パック 30th CELEBRATION</td></tr>
        <tr><th>開始日</th><td>2026年9月2日(水)10:00</td></tr>
      </table>
      <h3>イトーヨーカドーネット通販</h3>
      <table>
        <tr><th>対象商品</th><td>ポケモンカード MEGA 拡張パック 30th CELEBRATION</td></tr>
        <tr><th>開始日</th><td>2026年9月2日(水)10:00</td></tr>
      </table>
    </article>
    """
    source = _source("nyuka_now_fullcomp_livepocket", ("pokemon_card",))

    cases, releases, alerts = parse_nyuka_now_lottery_summary(
        html,
        "https://nyuka-now.com/archives/2459",
        source,
        load_config("sites.yaml"),
    )

    assert not releases
    assert not alerts
    assert {case.retailer_id for case in cases} == {
        "famima_online",
        "itoyokado_online",
    }
    assert all(
        case.start_at == datetime(2026, 9, 2, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        for case in cases
    )


def test_nyuka_now_recovers_current_kojima_app_lottery_box_only() -> None:
    html = """
    <article>
      <h2>抽選・予約応募受付中のストア</h2>
      <h3>コジマ（アプリ）</h3>
      <table>
        <tr><th>対象商品</th><td><ul>
          <li>ポケモンカード 30th CELEBRATION BOX</li>
          <li>ポケモンカード 30th CELEBRATION
          プレミアムデッキセット エーフィ・ブラッキー</li>
        </ul></td></tr>
        <tr><th>開始日</th><td>2026年9月4日(金)21:00</td></tr>
      </table>
      <a href="https://www.kojima.net/shop/app/kojima_appli.html">
        コジマアプリの詳細ページ
      </a>
    </article>
    """
    source = _source("nyuka_now_fullcomp_livepocket", ("pokemon_card",))

    cases, releases, alerts = parse_nyuka_now_lottery_summary(
        html,
        "https://nyuka-now.com/archives/2459",
        source,
        load_config("sites.yaml"),
    )

    assert not releases
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "kojima"
    assert cases[0].product_name == "ポケモンカード 30th CELEBRATION BOX"
    assert cases[0].start_at == datetime(
        2026, 9, 4, 21, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert cases[0].official_url == "https://www.kojima.net/shop/app/kojima_appli.html"


def test_box_lottery_without_start_raises_manual_check_alert() -> None:
    html = """
    <h1>ポケモンカードゲーム 拡張パック「新商品」BOX 抽選販売</h1>
    <p>応募方法は後日ご案内します。</p>
    """
    source = _source("famima_online_lottery", ("pokemon_card",))
    cases, _, alerts = parse_retailer_lottery_detail(
        html,
        "https://famima-online.family.co.jp/item?itemCode=test",
        source,
        _config(),
    )
    assert not cases
    assert [alert.reason_code for alert in alerts] == ["retailer_application_period_missing"]


def test_tokyo_otaku_mode_index_follows_supported_box_articles() -> None:
    html = """
    <main>
      <article>
        <a href="/blogs/news/pokemontcg-storm-emeralda-raffle">
          〖抽選販売〗抽選応募受付開始についてのお知らせ
        </a>
        <p>ポケモンカードゲーム MEGA 拡張パック
        ストームエメラルダ BOXの抽選応募を開始いたします。</p>
      </article>
      <article>
        <a href="/blogs/news/shipping-delay">配送遅延のお知らせ</a>
        <p>カード商品の配送に遅れが発生しています。</p>
      </article>
      <article>
        <a href="/blogs/news/pokemontcg-storm-emeralda-raffle">
          同じ記事を表示するモバイル用リンク
        </a>
      </article>
    </main>
    """
    source = _source(
        "tokyo_otaku_mode_lottery",
        (
            "pokemon_card",
            "one_piece_card",
            "dragon_ball_fusion_world",
        ),
    )
    assert discover_retailer_lottery_urls(
        html,
        "https://ja.otakumode.com/blogs/news",
        source,
        _config(),
    ) == ["https://ja.otakumode.com/blogs/news/pokemontcg-storm-emeralda-raffle"]


def test_tokyo_otaku_mode_uses_article_date_not_deadline_for_all_games() -> None:
    samples = [
        (
            "ポケモンカードゲーム MEGA 拡張パック ストームエメラルダ BOX",
            "pokemon_card",
            "pokemon-form",
        ),
        (
            "ONE PIECEカードゲーム ブースターパック 新世界への航路 [OP-17] BOX",
            "one_piece_card",
            "onepiece-form",
        ),
        (
            "ドラゴンボールスーパーカードゲーム フュージョンワールド ブースターパック [FB08] BOX",
            "dragon_ball_fusion_world",
            "dragonball-form",
        ),
    ]
    source = _source(
        "tokyo_otaku_mode_lottery",
        (
            "pokemon_card",
            "one_piece_card",
            "dragon_ball_fusion_world",
        ),
        ["抽選応募受付期間", "抽選受付期間", "応募受付期間"],
    )

    for product, expected_game, form_id in samples:
        html = f"""
        <article>
          <h1>〖抽選販売〗抽選応募受付開始についてのお知らせ</h1>
          <time datetime="2026-07-29">2026年7月29日</time>
          <p>下記の商品につきまして、抽選応募を開始いたします。</p>
          <p>{product}</p>
          <h2>〖抽選応募 受付期間〗</h2>
          <p>〜2026年8月3日 12時00分 JST</p>
          <h2>〖当選発表〗</h2>
          <p>2026年8月4日以降予定</p>
          <a href="https://docs.google.com/forms/d/e/{form_id}/viewform">
            ご応募はこちら
          </a>
        </article>
        """
        cases, releases, alerts = parse_retailer_lottery_detail(
            html,
            f"https://ja.otakumode.com/blogs/news/{form_id}",
            source,
            _config(),
        )

        assert not releases
        assert not alerts
        assert len(cases) == 1
        assert cases[0].game_id == expected_game
        assert cases[0].retailer_id == "tokyo_otaku_mode"
        assert cases[0].start_at.isoformat() == "2026-07-29"
        assert cases[0].official_url.endswith(f"/{form_id}/viewform")
        assert cases[0].extraction_method == "retailer_article_published_open"
        assert cases[0].confidence == "medium"


def test_tokyo_otaku_mode_prefers_an_explicit_application_start() -> None:
    html = """
    <article>
      <h1>〖抽選販売〗ポケモンカードゲーム BOX</h1>
      <time>2026年7月28日</time>
      <p>ポケモンカードゲーム 拡張パック
      「ストームエメラルダ」BOX</p>
      <p>抽選応募受付期間：2026年7月29日 18時00分〜
      2026年8月3日 12時00分</p>
    </article>
    """
    source = _source(
        "tokyo_otaku_mode_lottery",
        ("pokemon_card",),
        ["抽選応募受付期間"],
    )
    cases, _, alerts = parse_retailer_lottery_detail(
        html,
        "https://ja.otakumode.com/blogs/news/explicit-start",
        source,
        _config(),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].start_at.isoformat() == "2026-07-29T18:00:00+09:00"
    assert cases[0].extraction_method == "retailer_detail_application_period"
    assert cases[0].confidence == "high"
