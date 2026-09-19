"""販売日として採用できる情報源を、抽選の信頼区分とは別に制限する。"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from tcg_monitor.models import Release, SourceTier


def is_trusted_retailer_release(release: Release) -> bool:
    """販売店の全ページを許可せず、検証済みの発売表の抽出結果だけを許可。"""
    parsed = urlparse(release.source_url)
    return (
        release.source_tier == SourceTier.OFFICIAL_INDIRECT
        and release.extraction_method == "clabo_release_calendar"
        and parsed.scheme == "https"
        and parsed.netloc == "www.c-labo.jp"
        and re.fullmatch(r"/special/\d+/", parsed.path) is not None
        and release.release_date is not None
    )


def is_accepted_release(release: Release) -> bool:
    return release.source_tier == SourceTier.OFFICIAL or is_trusted_retailer_release(release)
