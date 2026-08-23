from datetime import date

from tcg_monitor.parsers.local_lottery import _application_start, _notice_range_start


def test_nakazato_date_only_start_is_not_replaced_by_timed_deadline() -> None:
    ocr_text = """
    8月22日（土）発売
    ONE PIECEカードゲーム ブースターパック「世界最強の戦士」
    抽選受付期間
    LivePocketオンライン受付
    8月7日（金）～8月10日（月）21:00まで
    """

    assert _application_start(ocr_text, date(2026, 8, 7)) == date(2026, 8, 7)


def test_application_period_with_only_a_deadline_has_no_start() -> None:
    text = """
    ポケモンカードゲーム 拡張パック「ストームエメラルダ」
    【予約受付期間】7月29日（水）23:59まで
    【当選者発表】7月30日（木）
    """

    assert _application_start(text, date(2026, 7, 4)) is None


def test_loose_ocr_notice_with_only_a_deadline_has_no_start() -> None:
    text = """
    抽選販売のお知らせ
    7月29日（水）23:59まで
    """

    assert _notice_range_start(text, date(2026, 7, 4)) is None
