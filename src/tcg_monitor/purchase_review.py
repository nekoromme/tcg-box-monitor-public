"""Exactly two purchase-review phases per physical product, in Japan time."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from tcg_monitor.discord import DiscordAdapter
from tcg_monitor.http_client import HttpFetcher
from tcg_monitor.identity import release_dedupe_key
from tcg_monitor.logging_config import log_event
from tcg_monitor.models import Config, Release, SourceTier
from tcg_monitor.release_sources import is_accepted_release
from tcg_monitor.review_modes import (
    PurchaseReviewModes,
    ReviewModeError,
    load_purchase_review_modes,
)
from tcg_monitor.review_sources import ContentEvidence, PriceEvidence, ReviewSource
from tcg_monitor.state import MonitorState


def family_assessment(release: Release) -> tuple[str, str, str]:
    """An explicit heuristic prior, not a backtested profit probability."""
    name = release.product_name.upper()
    if release.game_id == "yu_gi_oh":
        families = (
            (
                ("ARTWORK", "アートワーク"),
                "ARTWORK／原作・イラストコレクション",
                "高め",
                "原作絵・人気キャラのコレクター需要を確認する種別",
            ),
            (
                ("LIMIT OVER", "リミットオーバー"),
                "LIMIT OVER COLLECTION",
                "高め",
                "豪華仕様・特殊レアを確認するコレクション種別",
            ),
            (
                ("RARITY COLLECTION", "レアリティコレクション", "レアリティ・コレクション"),
                "RARITY COLLECTION",
                "高め",
                "汎用再録＋高レア仕様を確認する種別",
            ),
            (
                ("LIMITED", "リミテッド", "LIMITED PACK"),
                "LIMITED系",
                "条件付き",
                "名称だけで限定生産とは判断しない。販路・受付期間・再販を確認",
            ),
            (
                ("ANNIVERSARY", "QUARTER CENTURY", "記念"),
                "周年・記念系",
                "高め",
                "記念仕様・人気カード・供給条件を確認する種別",
            ),
        )
        for keywords, label, rank, reason in families:
            if any(keyword in name for keyword in keywords):
                return label, rank, reason
        if "スペシャル" in release.product_category or "SPECIAL" in name:
            return "その他スペシャルパック", "条件付き", "再録内容・特殊仕様次第"
        return "基本パック／その他", "標準", "新テーマ・汎用カード・初回特典を中身で判断"
    if any(word in name for word in ("ハイクラス", "記念", "ANNIVERSARY", "プレミアム")):
        return "豪華・記念・プレミアム系", "条件付き", "特別仕様・収録内容・供給条件を確認"
    return (
        release.product_category or "通常ブースター",
        "標準",
        "収録カードの強さとコレクター需要を中身で判断",
    )


def early_message(
    release: Release,
    evidence: ContentEvidence,
    now: datetime,
    lead: int,
    *,
    price_enabled: bool = True,
) -> str:
    family, rank, reason = family_assessment(release)
    lines = [
        f"商品: {release.product_name}",
        f"発売日: {release.release_date}",
        "フェーズ1/2: 中身を見て応募・購入を判断",
        f"種別: {family}",
        f"種別期待度（暫定ルール）: {rank} — {reason}",
        "※過去相場を集計した利益確率・開封期待値ではありません。",
    ]
    if evidence.complete:
        lines.append(
            f"収録公開: {evidence.card_count}/{evidence.total_cards}種確認・目安より前倒し可"
        )
    else:
        lines.append(f"収録公開: 全公開か未確認（このゲームの確認目安は発売{lead}日前）")
        if evidence.card_count is not None:
            lines.append(
                f"一覧の確認数: {evidence.card_count} / 総種類 {evidence.total_cards or '不明'}"
            )
    lines += [
        f"収録確認ページ: {evidence.card_list_url or evidence.url}",
        f"ページ種別: {evidence.card_list_label}",
    ]
    if evidence.card_index_url:
        lines.append(f"公式カード一覧（商品名で絞込み）: {evidence.card_index_url}")
    lines.extend(f"□ {label}: {value}" for label, value in evidence.features.items())
    if not evidence.features:
        lines.append("□ 初回限定・シリアル・特殊レア: 不明（取得できず）")
    if evidence.rarity_details:
        lines.append("公式の数量・レア仕様: " + " / ".join(evidence.rarity_details))
    if evidence.msrp:
        lines.append(f"定価: {evidence.msrp:,}円（BOX／セット単位）")
    if evidence.error:
        lines.append(f"情報取得: 未確認（{evidence.error}）")
    lines += [
        f"公式／情報元: {evidence.url}",
        (
            "次回: 発売2日前のスニダン価格判定。未掲載・取得不能なら前日に再確認。"
            if price_enabled
            else "直前価格通知: OFF（早期チェックのみ試運転）"
        ),
        f"確認時刻: {now:%Y-%m-%d %H:%M} JST",
    ]
    return "\n".join(lines)


def price_message(
    release: Release,
    evidence: PriceEvidence,
    content: ContentEvidence,
    now: datetime,
) -> tuple[str, str]:
    lines = [
        f"商品: {release.product_name}",
        f"発売日: {release.release_date}",
        "フェーズ2/2: 発売直前価格で応募・購入を判断",
    ]
    msrp = content.msrp or evidence.msrp
    conflict = bool(content.msrp and evidence.msrp and content.msrp != evidence.msrp)
    valid = (
        evidence.status == "found"
        and evidence.price is not None
        and msrp is not None
        and not conflict
    )
    decision = "判定不能"
    if valid:
        assert msrp is not None and evidence.price is not None
        passed = evidence.price * 100 > msrp * 130  # Strict, integer comparison.
        decision = "応募・購入候補（価格基準達成）" if passed else "価格基準未達"
        premium = (evidence.price / msrp - 1) * 100
        lines += [
            f"スニダン事前価格: {evidence.price:,}円",
            f"価格の単位: {evidence.basis}",
            f"定価: {msrp:,}円（{'公式仕様' if content.msrp else 'スニダン商品欄'}）",
            f"定価比: {premium:+.2f}%",
            f"判定: {decision}",
        ]
    else:
        reason = (
            "公式とスニダンの定価不一致" if conflict else evidence.error or "価格または定価が不明"
        )
        lines += ["判定: 判定不能（未達とは別）", f"理由: {reason}"]
        if evidence.price:
            lines.append(f"取得価格: {evidence.price:,}円")
    lines += [
        "判定条件: 定価＋30%を超える（＋30%ちょうどは未達）",
        "価格は最安出品。成約価格・手数料控除後の利益ではありません。",
        f"価格ページ: {evidence.url or '未発見'}",
        f"確認時刻: {now:%Y-%m-%d %H:%M} JST",
    ]
    return decision, "\n".join(lines)


def _restore(raw: dict[str, Any]) -> Release | None:
    try:
        return Release(
            game_id=str(raw["game_id"]),
            product_name=str(raw["product_name"]),
            product_category=str(raw["product_category"]),
            canonical_product_key=str(raw["canonical_product_key"]),
            release_date=date.fromisoformat(str(raw["release_date"]))
            if raw.get("release_date")
            else None,
            release_month=raw.get("release_month"),
            official_url=str(raw.get("official_url", "")),
            source_url=str(raw["source_url"]),
            source_tier=SourceTier(raw["source_tier"]),
            extraction_method=str(raw.get("extraction_method", "")),
            confidence=str(raw.get("confidence", "")),
            release_id=str(raw.get("release_id", "")),
        )
    except (ValueError, KeyError, TypeError):
        return None


def run_purchase_reviews(
    config: Config,
    state: MonitorState,
    releases: list[Release],
    discord: DiscordAdapter,
    now: datetime,
    *,
    source: ReviewSource | None = None,
    modes: PurchaseReviewModes | None = None,
) -> list[dict[str, str]]:
    settings = config.system.get("purchase_review", {})
    if not isinstance(settings, dict) or not settings.get("enabled", False):
        return []
    if modes is None:
        try:
            modes = load_purchase_review_modes()
        except (ReviewModeError, OSError, UnicodeError) as exc:
            log_event(
                phase="purchase_review",
                status="disabled",
                reason_code="invalid_trial_switch",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return []  # A broken trial switch cannot stop lotteries/releases.
    if not modes.early_content and not modes.pre_release_price:
        return []
    now = now.astimezone(ZoneInfo(config.timezone))
    products: dict[str, Release] = {}
    excluded = config.system.get("runtime", {}).get("confirmed_false_positive_releases", {})
    for raw in state.data["seen_releases"].values():
        if isinstance(raw, dict) and (release := _restore(raw)):
            products[release_dedupe_key(release)] = release
    # Today's pipeline is authoritative for postponed dates and newly found products.
    for release in releases:
        products[release_dedupe_key(release)] = release
    source = source or ReviewSource(
        HttpFetcher(
            timeout=float(config.system.get("request_timeout_seconds", 20)),
            max_retries=1,
            request_budget_seconds=30,
            minimum_host_interval=float(config.system.get("minimum_host_interval_seconds", 5)),
        )
    )
    records = state.data.setdefault("purchase_reviews", {})
    results: list[dict[str, str]] = []
    leads = settings.get("early_lead_days", {})
    for key, release in sorted(products.items(), key=lambda pair: str(pair[1].release_date)):
        if (
            release.game_id not in config.active_game_ids
            or not release.release_date
            or release.release_id in excluded
            or not is_accepted_release(release)
        ):
            continue
        days = (release.release_date - now.date()).days
        if not 1 <= days <= int(settings.get("content_check_window_days", 21)):
            continue  # Never send a pre-release signal after the release date.
        record = records.setdefault(key, {})
        early_pending = modes.early_content and not record.get("early_sent")
        price_pending = modes.pre_release_price and not record.get("price_sent") and days <= 2
        if not early_pending and not price_pending:
            continue
        record["release_date"] = release.release_date.isoformat()
        lead = int(leads.get(release.game_id, 7))
        content = ContentEvidence(**record.get("content", {}))
        if (early_pending or price_pending) and (
            record.get("content_checked_on") != now.date().isoformat() or content.error
        ):
            refreshed = source.content(release)
            if not refreshed.error or not content.url:
                content = refreshed
            record["content"] = asdict(content)
            record["content_checked_on"] = now.date().isoformat()
        if (
            early_pending
            and (days <= lead or content.complete)
            and (not content.error or days < lead or now.hour >= 20)
        ):
            try:
                result = discord.send(
                    f"【{config.games[release.game_id].short_name}早期・中身チェック】{release.product_name}",
                    early_message(
                        release,
                        content,
                        now,
                        lead,
                        price_enabled=modes.pre_release_price,
                    ),
                )
                if result.get("status") == "sent":
                    record["early_sent"] = now.isoformat()
                    state.save()
                    results.append(
                        {"product": release.product_name, "phase": "early", "status": "sent"}
                    )
            except Exception as exc:
                log_event(
                    phase="purchase_review",
                    status="failed",
                    reason_code="early_delivery_failed",
                    product=key,
                    error_type=type(exc).__name__,
                )
        if not price_pending:
            continue
        if days == 2 and record.get("price_missing_on") == now.date().isoformat():
            continue  # An absent page explicitly switches this product to the D-1 phase.
        # Fetch anew on every attempt: no cached retail-market price is a pre-release observation.
        price = source.price(release, str(record.get("snkr_url", "")))
        if price.status == "missing":
            record["price_missing_on"] = now.date().isoformat()
        if price.status in {"found", "unpriced"}:
            record["snkr_url"] = price.url
        record["last_price_attempt"] = {**asdict(price), "checked_at": now.isoformat()}
        decision, description = price_message(release, price, content, now)
        if decision == "判定不能" and not (days == 1 and now.hour >= 20):
            log_event(
                phase="purchase_review",
                status="pending",
                reason_code="price_retry_before_release",
                product=key,
                evidence_status=price.status,
            )
            continue  # D-2 missing/error -> D-1; final missing notice after 20:00 JST.
        try:
            result = discord.send(
                f"【{config.games[release.game_id].short_name}直前価格・{decision}】{release.product_name}",
                description,
            )
            if result.get("status") == "sent":
                record["price_sent"] = now.isoformat()
                record["decision"] = decision
                state.save()
                results.append(
                    {"product": release.product_name, "phase": "price", "status": "sent"}
                )
        except Exception as exc:
            log_event(
                phase="purchase_review",
                status="failed",
                reason_code="price_delivery_failed",
                product=key,
                error_type=type(exc).__name__,
            )
    return results
