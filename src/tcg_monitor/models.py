from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def stable_url_identity(value: str) -> str:
    """Normalize an article URL while retaining query fields that identify it."""

    parts = urlsplit(value)
    stable_query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith(
                ("utm_", "ref", "fbclid", "gclid")
            )
        )
    )
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            parts.path.rstrip("/") or "/",
            stable_query,
            "",
        )
    )


class SourceTier(StrEnum):
    OFFICIAL = "official"
    OFFICIAL_INDIRECT = "official_indirect"
    SECONDARY = "secondary"


class GameId(StrEnum):
    POKEMON = "pokemon_card"
    ONE_PIECE = "one_piece_card"
    DRAGON_BALL = "dragon_ball_fusion_world"
    YU_GI_OH = "yu_gi_oh"
    LORCANA = "lorcana"


class EventKind(StrEnum):
    LOTTERY = "lottery"
    RELEASE = "release"
    ALERT = "alert"


class OpportunityKind(StrEnum):
    """User-facing kind of a BOX purchase opportunity.

    ``LotteryCase`` is the legacy state object used throughout the monitor.  Keeping
    that object avoids changing every existing lottery identifier, while this field
    lets official maker stores report ordinary order windows without calling them a
    lottery.  Existing records have no field and therefore continue to mean
    ``lottery``.
    """

    LOTTERY = "lottery"
    DIRECT_SALE = "direct_sale"
    DIRECT_SALE_SEEN = "direct_sale_seen"


class GameSupport(StrEnum):
    """How confidently a source can be used for one game.

    ``verified`` and ``prospective`` are eligible for normal parsing.  A
    ``discovery_only`` entry may be fetched as an early-warning source, but it
    must not create a lottery/release by itself.  ``unsupported`` is an
    explicit opt-out and is never parsed for that game.
    """

    VERIFIED = "verified"
    PROSPECTIVE = "prospective"
    DISCOVERY_ONLY = "discovery_only"
    UNSUPPORTED = "unsupported"

    @property
    def parse_enabled(self) -> bool:
        return self in {self.VERIFIED, self.PROSPECTIVE}


class LotteryStartPolicy(StrEnum):
    """How a social source chooses a lottery start date."""

    AUTO = "auto"
    FIRST_DETECTION = "first_detection"
    FIRST_DETECTION_NEXT_DAY = "first_detection_next_day"


class RenderMode(StrEnum):
    HTTP = "http"
    PLAYWRIGHT = "playwright"
    HTTP_THEN_PLAYWRIGHT_IF_EMPTY = "http_then_playwright_if_empty"
    HTTP_THEN_BROWSER_IF_SHELL = "http_then_browser_if_shell"
    HTTP_NO_CHALLENGE_BYPASS = "http_no_challenge_bypass"
    HTTP_THEN_BROWSER_ONCE_NO_CHALLENGE_BYPASS = (
        "http_then_browser_once_no_challenge_bypass"
    )

    @property
    def browser_fallback_enabled(self) -> bool:
        return self in {
            self.HTTP_THEN_PLAYWRIGHT_IF_EMPTY,
            self.HTTP_THEN_BROWSER_IF_SHELL,
            self.HTTP_THEN_BROWSER_ONCE_NO_CHALLENGE_BYPASS,
        }


@dataclass(frozen=True)
class SourceConfig:
    id: str
    name: str
    source_tier: SourceTier
    supported_games: dict[str, GameSupport]
    purposes: list[str]
    enabled: bool
    discovery_urls: list[str]
    start_labels: list[str] = field(default_factory=list)
    render_mode: RenderMode = RenderMode.HTTP
    render_wait_selector: str | None = None
    poll_minutes: int = 10
    selectors: dict[str, list[str]] = field(default_factory=dict)
    expected_elements: list[str] = field(default_factory=list)
    robots_url: str | None = None
    fallback_source_ids: list[str] = field(default_factory=list)
    activation_group: str = "always"
    application_method: str | None = None
    required_store_visits: int | None = None
    lottery_start_policy: LotteryStartPolicy = LotteryStartPolicy.AUTO
    fallback_on_empty_result: bool = False

    def supports(self, game_id: str) -> bool:
        status = self.supported_games.get(game_id)
        if status is None:
            return False
        try:
            parsed = status if isinstance(status, GameSupport) else GameSupport(status)
        except ValueError:
            return False
        return parsed.parse_enabled

    @property
    def parse_game_ids(self) -> set[str]:
        return {game_id for game_id in self.supported_games if self.supports(game_id)}


@dataclass(frozen=True)
class GameConfig:
    id: GameId
    name: str
    short_name: str
    release_notification_prefix: str
    release_calendar_prefix: str
    lottery_schedule_prefix: str
    lottery_start_prefix: str
    include_keywords: list[str]
    box_product_keywords: list[str]
    box_evidence_patterns: list[str]
    product_exclude_keywords: list[str]
    product_code_patterns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Config:
    schema_version: int
    timezone: str
    system: dict[str, Any]
    games: dict[str, GameConfig]
    common_terms: dict[str, Any]
    sources: list[SourceConfig]
    enabled_game_ids: frozenset[str] | None = None

    @property
    def active_game_ids(self) -> frozenset[str]:
        """Return games enabled for this run.

        ``None`` keeps programmatic/test configurations backwards compatible:
        all games declared in that configuration remain active unless the
        operator-facing switch explicitly narrows them.
        """

        if self.enabled_game_ids is None:
            return frozenset(self.games)
        return self.enabled_game_ids


@dataclass(frozen=True)
class ClassifiedProduct:
    game_id: str
    product_name: str
    product_category: str
    is_box: bool
    canonical_product_key: str
    evidence: list[str]
    exclude_reasons: list[str]


@dataclass(frozen=True)
class LotteryCase:
    game_id: str
    retailer_id: str
    retailer_name: str
    product_name: str
    product_category: str
    canonical_product_key: str
    start_at: datetime | date
    official_url: str
    source_url: str
    source_tier: SourceTier
    extraction_method: str
    confidence: str
    case_id: str = ""
    opportunity_kind: OpportunityKind = OpportunityKind.LOTTERY
    end_at: datetime | date | None = None

    def with_id(self) -> LotteryCase:
        durable_retailer_url = ""
        official_parts = urlsplit(self.official_url)
        official_host = official_parts.netloc.casefold().removeprefix("www.")
        if self.retailer_id == "amazon_jp" and official_host == "amazon.co.jp":
            amazon_match = re.search(
                r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)",
                official_parts.path + ("?" if official_parts.query else ""),
                re.I,
            )
            if amazon_match:
                durable_retailer_url = (
                    "https://www.amazon.co.jp/dp/"
                    + amazon_match.group(1).upper()
                )
        elif (
            self.retailer_id == "furuichi"
            and official_host == "furu1.net"
            and re.fullmatch(
                r"/news/news_information/[A-Za-z0-9_-]+/?",
                official_parts.path,
            )
        ):
            durable_retailer_url = (
                "https://www.furu1.net" + official_parts.path.rstrip("/")
            )

        source_parts = urlsplit(self.source_url)
        source_segments = [part for part in source_parts.path.split("/") if part]
        has_article_status_id = any(
            part == "status"
            and index + 1 < len(source_segments)
            and source_segments[index + 1].isdigit()
            for index, part in enumerate(source_segments)
        )
        if self.retailer_id == "amazon_jp" and not durable_retailer_url:
            # Xの短縮URLをAmazon商品URLへ展開できない場合でも、同じBOXの
            # 再投稿を別案件にしない。商品コードはidentity_partsへ別途入る。
            article_identity = "amazon-product-key"
        else:
            identity_url = durable_retailer_url or (
                self.source_url
                if has_article_status_id
                else self.official_url or self.source_url
            )
            article_identity = stable_url_identity(identity_url)
        identity_parts = [
            self.game_id,
            self.retailer_id,
            self.canonical_product_key,
            article_identity,
        ]
        # Preserve every historical lottery ID.  Only newly introduced ordinary
        # official-store sales need a kind suffix so a sale and a lottery for the
        # same product page cannot suppress one another.
        if self.opportunity_kind != OpportunityKind.LOTTERY:
            identity_parts.append(self.opportunity_kind.value)
        raw = "|".join(identity_parts)
        return self.__class__(**{**self.__dict__, "case_id": sha256(raw.encode()).hexdigest()})


@dataclass(frozen=True)
class Release:
    game_id: str
    product_name: str
    product_category: str
    canonical_product_key: str
    release_date: date | None
    release_month: str | None
    official_url: str
    source_url: str
    source_tier: SourceTier
    extraction_method: str
    confidence: str
    release_id: str = ""

    def with_id(self) -> Release:
        raw = f"{self.game_id}|{self.canonical_product_key}"
        return self.__class__(**{**self.__dict__, "release_id": sha256(raw.encode()).hexdigest()})


@dataclass(frozen=True)
class Alert:
    game_id: str | None
    source_id: str
    target_url: str
    title: str
    related_terms: list[str]
    reason_code: str
    change_summary: str
    http_status: int | None
    manual_check_url: str
    fingerprint: str = ""

    def with_fingerprint(self) -> Alert:
        """Build an incident ID that is stable when user-facing wording changes.

        The source, reason and normalized manual-check URL identify the problem.
        Titles and summaries are display text and may change between otherwise
        identical runs, so including them would bypass notification suppression.
        """

        identity_url = stable_url_identity(self.manual_check_url or self.target_url)
        raw = "|".join([self.source_id, identity_url, self.reason_code])
        return self.__class__(**{**self.__dict__, "fingerprint": sha256(raw.encode()).hexdigest()})
