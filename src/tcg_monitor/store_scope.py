"""明示された対象店舗だけで選別する。記載なし・省略は通知候補に残す。"""

from __future__ import annotations

import re
import unicodedata

from tcg_monitor.logging_config import log_event
from tcg_monitor.models import Config


def outside_store_scope(
    config: Config, retailer_id: str, text: str, source_id: str, source_url: str,
) -> bool:
    targets = config.system.get("lottery_store_filters", {}).get(retailer_id, [])
    if not targets:
        return False
    normalized = unicodedata.normalize("NFKC", text)
    compact = re.sub(r"\s+", "", normalized)
    # 「仙台を含む一覧」と「仙台は対象外」を混同しない。
    explicit_exclusion = any(re.search(
        re.escape(target) + r"(?:駅前)?(?:店)?(?:は|を|のみ)?(?:対象外|除外|除く|以外)", compact,
    ) for target in targets)
    blocks = re.findall(
        r"(?:対象|実施|受取)店舗\s*(?:[:：>〉】]|\n)\s*(.+?)"
        r"(?=[<＜【]|応募期間|応募条件|開始日|終了日|当選発表|購入期間|詳細ページ|$)",
        normalized, re.S,
    )
    # 同じ募集内に仙台の対象欄があれば残す。店名が無いことだけでは落とさない。
    if not explicit_exclusion and any(
        target in re.sub(r"\s+", "", block) for block in blocks for target in targets
    ):
        return False
    if not explicit_exclusion and any(re.search(r"全店舗|全店|全国", block) for block in blocks):
        return False
    complete_lists = [block for block in blocks if (
        not re.search(r"など|ほか|他の|その他|一部|参照|確認|画像|リンク|詳細|…|\.\.\.", block)
        and (re.search(r"[・、/／\n]", block.strip()) or re.search(r"\S+店", block))
    )]
    excluded = explicit_exclusion or bool(complete_lists)
    if excluded:
        log_event(
            phase="lottery_store_scope", status="excluded",
            reason_code="explicit_store_exclusion" if explicit_exclusion else "target_store_absent",
            retailer=retailer_id, source_id=source_id, source_url=source_url,
            target_stores=targets, store_list=complete_lists[:1],
        )
    return excluded
