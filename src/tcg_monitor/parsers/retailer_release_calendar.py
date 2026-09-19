"""カードラボの発売日一覧。ブラウザー・画像認識・商品個別URLに依存しない。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from tcg_monitor.classifier import classify_product
from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig

# 表のカテゴリで作品を限定する。遊戯王RDや別作品の同名商品を混ぜない。
CATEGORIES = {
    "ポケモン": "pokemon_card",
    "ワンピース": "one_piece_card",
    "DBS FW": "dragon_ball_fusion_world",
    "遊戯王": "yu_gi_oh",
    "ガンダム": "gundam_card",
    "ロルカナ": "lorcana",
}
DAY = re.compile(r"^(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日[（(]([月火水木金土日])[）)]発売$")


def discover_clabo_calendar_urls(html: str, url: str) -> list[str]:
    """固定の記事番号を使わず、トップの『発売日カレンダー』を毎回たどる。"""
    found: list[str] = []
    for anchor in BeautifulSoup(html, "lxml").select("a[href]"):
        if "発売日カレンダー" not in anchor.get_text(" ", strip=True):
            continue
        target = urljoin(url, str(anchor["href"]))
        parsed = urlparse(target)
        if (
            parsed.scheme == "https"
            and parsed.netloc == "www.c-labo.jp"
            and re.fullmatch(r"/special/\d+/", parsed.path)
            and target not in found
        ):
            found.append(target)
    return found


def parse_clabo_release_calendar(
    html: str,
    url: str,
    source: SourceConfig,
    config: Config,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    soup = BeautifulSoup(html, "lxml")
    alerts: list[Alert] = []

    def alert(reason: str, message: str) -> None:
        alerts.append(
            Alert(
                None, source.id, url, source.name, ["発売日"], reason, message, None, url
            ).with_fingerprint()
        )

    title = soup.find("h1")
    article = title.find_parent("article") if title else None
    if title is None or article is None or "発売日カレンダー" not in title.get_text():
        alert("expected_element_missing", "発売日カレンダーの本文がありません")
        return [], [], alerts
    # 現在年を勝手に補うと、放置された去年の表を今年の予定として再登録してしまう。
    # 必ず記事の更新日を基準にし、年越しと曜日も検証する。
    stamp = article.select_one(".article_date")
    match = re.fullmatch(
        r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", stamp.get_text(strip=True) if stamp else ""
    )
    try:
        updated = date(*map(int, match.groups())) if match else None
    except ValueError:
        updated = None
    today = datetime.now(ZoneInfo(config.timezone)).date()
    if updated is None or not today - timedelta(days=120) <= updated <= today:
        alert("release_calendar_stale", "更新日が不明、未来、または120日以上更新されていません")
        return [], [], alerts

    releases: dict[str, Release] = {}
    daily_tables = 0
    for table in article.find_all("table"):
        headers = [x.get_text(strip=True) for x in table.select("thead th")]
        if headers[:2] != ["カテゴリ", "商品名"]:
            continue  # タイトル別表示は同じ商品の重複なので読まない。
        daily_tables += 1
        heading = table.find_previous_sibling()
        text = re.sub(r"\s+", "", heading.get_text() if isinstance(heading, Tag) else "")
        day_match = DAY.fullmatch(text)
        when = None
        if day_match:
            explicit_year, month, day, weekday = day_match.groups()
            year = int(explicit_year) if explicit_year else updated.year
            # この一覧は更新月以降の予定表。12月更新で1月なら翌年になる。
            if not explicit_year and int(month) < updated.month:
                year += 1
            try:
                candidate = date(year, int(month), int(day))
                if "月火水木金土日"[candidate.weekday()] == weekday and updated.replace(
                    day=1
                ) <= candidate <= updated + timedelta(days=366):
                    when = candidate
            except ValueError:
                pass
        if when is None:
            alert("release_calendar_date_invalid", f"発売日の見出しを確定できません: {text}")
            continue
        for row in table.select("tbody tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) != 3:
                alert("expected_element_missing", "発売表の商品行の列数が変わっています")
                continue
            category, name = (cell.get_text(" ", strip=True) for cell in cells[:2])
            game_id = CATEGORIES.get(category)
            if game_id is None or not source.supports(game_id):
                continue
            classified = classify_product(config.games[game_id], name, name)
            if not classified.is_box:
                continue
            # 公式ページは作品名・シリーズ名を省いた商品名を使う。
            # 一覧側だけに付く接頭辞を外し、公式確認後の二重登録を防ぐ。
            if game_id == "pokemon_card":
                name = re.sub(r"^ポケモンカードゲーム\s*(?:MEGA\s*)?", "", name).strip()
            elif game_id == "yu_gi_oh":
                name = re.sub(r"^(?:遊戯王|遊☆戯☆王)\s*", "", name).strip()
            release = Release(
                game_id,
                name,
                classified.product_category,
                classified.canonical_product_key,
                when,
                None,
                "",
                url,
                source.source_tier,
                "clabo_release_calendar",
                "medium",
            ).with_id()
            previous = releases.get(release.release_id)
            if previous and previous.release_date != when:
                alert("release_calendar_conflict", f"同じ商品の発売日が表内で異なります: {name}")
                return [], [], alerts
            releases[release.release_id] = release
    if not daily_tables:
        alert("expected_element_missing", "カテゴリ・商品名の発売表が見つかりません")
    return [], list(releases.values()), alerts
