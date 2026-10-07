"""全国チェーン名と、名前の一部が同じ別店舗の募集を区別する。"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


def retailer_mention_matches(
    retailer_id: str, text: str, aliases: Iterable[str], *, label: bool = False,
) -> bool:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    compact = re.sub(r"\s+", "", normalized)
    names = [unicodedata.normalize("NFKC", alias).casefold() for alias in aliases]
    if retailer_id != "geo":
        return any(re.sub(r"\s+", "", name) in compact for name in names)

    # SuperKaBoS+GEOは併設店の独自抽選。全国のゲオ抽選と同じIDへ
    # 振り分けると、福井の店頭受取を一関で応募できる募集として通知する。
    # 二次情報の投稿本文でも、この別店舗の名前を先に識別する。
    other_store = r"(?:superkabos|スーパーカボス|カボス|文真堂(?:書店)?)"
    if re.search(
        rf"{other_store}[+・&/]*(?:geo|ゲオ)|(?:geo|ゲオ)[+・&/]*{other_store}",
        compact,
    ):
        return False

    if label:
        # 店舗見出しは店名そのものが識別根拠。途中のGEOには一致させず、
        # 別支店名・併設ブランドも全国募集へ昇格させない。
        return bool(re.fullmatch(
            r"(?:ゲオ|geo)(?:\s*\((?:geo|ゲオ|アプリ|全国|web|ウェブ|オンライン)\)"
            r"|オンライン|アプリ)?(?:\s+(?:抽選|予約|受付|応募|招待|[0-9]).*"
            r"|の(?:抽選|予約|応募).*)?",
            normalized.strip(),
        ))

    # 本文は「ゲオで抽選」なども認める。英字のGEOは単語単位で判定し、
    # SuperKaBoSGEO・+GEO・別サービス名中のgeoを拾わない。
    return any(
        bool(re.search(r"(?<![a-z0-9_+])geo(?![a-z0-9_+])", compact))
        if name == "geo" else name in compact
        for name in names
    )
