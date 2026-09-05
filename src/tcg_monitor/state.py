from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tcg_monitor.game_modes import LEGACY_ENABLED_GAME_IDS
from tcg_monitor.identity import (
    is_provisional_product_name,
    release_dedupe_key,
    release_dedupe_key_values,
    release_title_token,
)
from tcg_monitor.models import LotteryCase, Release, stable_url_identity

SCHEMA_VERSION = 2
ALERT_RETENTION_DAYS = 30
OCR_RETENTION_DAYS = 90
DELIVERY_RETENTION_DAYS = 730
HTTP_CACHE_RETENTION_DAYS = 90


def _default_data() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "baseline_complete": False,
        "armed": False,
        "seen_cases": {},
        "seen_releases": {},
        "ocr_cache": {},
        "ocr_cache_meta": {},
        "ocr_pending": {},
        "delivery_journal": {},
        "alerts": {},
        "monitors": {},
        "http_cache": {},
        "calendar_sync": {},
        "case_id_migrations": {},
        "last_run_summary": {},
        # Existing installations predate the per-game switch. Treat only the
        # original three titles as previously enabled so newly added games can
        # baseline visible lotteries once instead of sending a backlog burst.
        "enabled_game_ids": sorted(LEGACY_ENABLED_GAME_IDS),
    }


def _timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass
class MonitorState:
    path: Path
    data: dict[str, Any] = field(default_factory=_default_data)

    @classmethod
    def load(cls, path: str | Path = "monitor_state.json") -> MonitorState:
        state_path = Path(path)
        if not state_path.exists():
            return cls(state_path)
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("monitor_state.jsonのルートはJSONオブジェクトである必要があります")
        version = int(loaded.get("schema_version", 1))
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"未対応のmonitor_state schema_versionです: {version} > {SCHEMA_VERSION}"
            )
        defaults = _default_data()
        for key, value in defaults.items():
            loaded.setdefault(key, value)
        for key in (
            "seen_cases",
            "seen_releases",
            "ocr_cache",
            "ocr_cache_meta",
            "ocr_pending",
            "delivery_journal",
            "alerts",
            "monitors",
            "http_cache",
            "calendar_sync",
            "case_id_migrations",
            "last_run_summary",
        ):
            if not isinstance(loaded.get(key), dict):
                raise ValueError(f"monitor_stateの{key}はJSONオブジェクトである必要があります")
        if not isinstance(loaded.get("enabled_game_ids"), list) or not all(
            isinstance(value, str) for value in loaded["enabled_game_ids"]
        ):
            raise ValueError("monitor_stateのenabled_game_idsは文字列配列である必要があります")
        loaded["schema_version"] = SCHEMA_VERSION
        migrated_at = datetime.fromtimestamp(state_path.stat().st_mtime, UTC).isoformat()
        ocr_cache = _mapping(loaded.get("ocr_cache"))
        ocr_metadata = _mapping(loaded.get("ocr_cache_meta"))
        for cache_key in ocr_cache:
            ocr_metadata.setdefault(cache_key, {"updated_at": migrated_at})
        journal = _mapping(loaded.get("delivery_journal"))
        for record in journal.values():
            if isinstance(record, dict):
                record.setdefault("updated_at", migrated_at)
        return cls(state_path, loaded)

    def _validate_serialized(self, serialized: str) -> None:
        decoded = json.loads(serialized)
        if not isinstance(decoded, dict):
            raise ValueError("monitor_stateの直列化結果がJSONオブジェクトではありません")
        if decoded.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("monitor_state schema_versionが不正です")

    def save(self, now: datetime | None = None) -> None:
        """Atomically replace the state only after a complete JSON round-trip."""

        self.prune(now)
        serialized = json.dumps(
            self.data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
            allow_nan=False,
        )
        self._validate_serialized(serialized)
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            # os.replace is atomic when the temporary file is in the same directory.
            os.replace(temporary, self.path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def prune(self, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)

        alerts = _mapping(self.data.setdefault("alerts", {}))
        alert_cutoff = current - timedelta(days=ALERT_RETENTION_DAYS)
        for fingerprint, record in list(alerts.items()):
            if not isinstance(record, dict) or record.get("status") != "resolved":
                continue
            resolved_at = _timestamp(
                record.get("resolved_at") or record.get("last_seen_at")
            )
            if resolved_at and resolved_at < alert_cutoff:
                del alerts[fingerprint]

        ocr_cache = _mapping(self.data.setdefault("ocr_cache", {}))
        ocr_meta = _mapping(self.data.setdefault("ocr_cache_meta", {}))
        ocr_pending = _mapping(self.data.setdefault("ocr_pending", {}))
        ocr_cutoff = current - timedelta(days=OCR_RETENTION_DAYS)
        # A cached OCR result and a pending OCR failure are contradictory.
        # Heal old state even when the original social post has left the
        # provider's current search results and is no longer parsed again.
        for cache_key in list(ocr_pending):
            if str(ocr_cache.get(cache_key) or "").strip():
                del ocr_pending[cache_key]
        for cache_key, record in list(ocr_meta.items()):
            updated_at = _timestamp(record.get("updated_at")) if isinstance(record, dict) else None
            if updated_at and updated_at < ocr_cutoff:
                ocr_cache.pop(cache_key, None)
                del ocr_meta[cache_key]
        for cache_key, record in list(ocr_pending.items()):
            updated_at = (
                _timestamp(record.get("last_seen_at"))
                if isinstance(record, dict)
                else None
            )
            if updated_at and updated_at < ocr_cutoff:
                del ocr_pending[cache_key]

        http_cache = _mapping(self.data.setdefault("http_cache", {}))
        http_cutoff = current - timedelta(days=HTTP_CACHE_RETENTION_DAYS)
        for url, record in list(http_cache.items()):
            checked_at = (
                _timestamp(record.get("checked_at"))
                if isinstance(record, dict)
                else None
            )
            if checked_at and checked_at < http_cutoff:
                del http_cache[url]

        journal = _mapping(self.data.setdefault("delivery_journal", {}))
        delivery_cutoff = current - timedelta(days=DELIVERY_RETENTION_DAYS)
        for key, record in list(journal.items()):
            updated_at = _timestamp(record.get("updated_at")) if isinstance(record, dict) else None
            if (
                updated_at
                and updated_at < delivery_cutoff
                and isinstance(record, dict)
                and record.get("status") == "complete"
            ):
                del journal[key]

    def mark_baseline(self) -> None:
        self.data["baseline_complete"] = True
        self.save()

    def arm(self) -> None:
        if not self.data.get("baseline_complete"):
            raise RuntimeError("baseline is required before arm")
        self.data["armed"] = True
        self.save()

    def delivered(self, key: str) -> bool:
        return key in _mapping(self.data.setdefault("delivery_journal", {}))

    def mark_delivered(self, key: str, status: str = "complete") -> None:
        journal = _mapping(self.data.setdefault("delivery_journal", {}))
        journal[key] = {
            "status": status,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self.save()

    def record_monitor(
        self,
        source_id: str,
        values: Mapping[str, object],
        *,
        success: bool,
        recorded_at: datetime | None = None,
    ) -> None:
        now = recorded_at or datetime.now(UTC)
        monitors = _mapping(self.data.setdefault("monitors", {}))
        previous = _mapping(monitors.get(source_id))
        current_http_status = values.get("http_status")
        last_http_status = (
            current_http_status
            if current_http_status is not None
            else previous.get("last_http_status", previous.get("http_status"))
        )
        record = {
            "last_success_at": now.isoformat()
            if success
            else previous.get("last_success_at"),
            "last_fetch_at": values.get("last_fetch_at")
            or previous.get("last_fetch_at"),
            "consecutive_failures": 0
            if success
            else int(previous.get("consecutive_failures", 0)) + 1,
            # ``http_status`` is strictly the current run.  Keeping an old 200
            # beside a new connection timeout made outages look contradictory.
            # ``last_http_status`` retains the historical diagnostic value.
            "http_status": current_http_status,
            "last_http_status": last_http_status,
            "fetch_method": values.get("fetch_method"),
            "duration_ms": values.get("duration_ms", 0),
            "fetch_duration_ms": values.get("fetch_duration_ms", 0),
            "fetched_pages": values.get("fetched_pages", 0),
            "parsed_count": values.get("parsed_count", 0),
            "candidate_runs": int(previous.get("candidate_runs", 0))
            + (1 if int(str(values.get("parsed_count") or 0)) > 0 else 0),
            "last_candidate_at": now.isoformat()
            if int(str(values.get("parsed_count") or 0)) > 0
            else previous.get("last_candidate_at"),
            "evidence_since": previous.get("evidence_since") or now.isoformat(),
            "routes": values.get("routes", {}),
            "retailer_ids": values.get("retailer_ids", []),
            "release_game_ids": values.get("release_game_ids", []),
            "excluded_count": values.get("excluded_count", 0),
            "outcome": "success" if success else "failed",
            "last_error": values.get("last_error"),
            "failure_cause": values.get("failure_cause"),
            "failure_attempts": values.get("failure_attempts"),
        }
        # 過去に実際に候補を生成したURLのみ、実証済み履歴として引き継ぐ。
        evidence = dict(_mapping(previous.get("route_evidence")))
        for url, raw in _mapping(values.get("routes")).items():
            route = _mapping(raw)
            if int(route.get("parsed_count") or 0) > 0:
                evidence[url] = {"last_candidate_at": now.isoformat()}
        record["route_evidence"] = evidence
        monitors[source_id] = record
        self.save()

    def record_monitor_coverage(
        self,
        covered_sources: Mapping[str, list[str]],
    ) -> None:
        """Mark raw source failures whose verified coverage used alternatives."""

        if not covered_sources:
            return
        monitors = _mapping(self.data.setdefault("monitors", {}))
        changed = False
        for source_id, fallback_ids in covered_sources.items():
            record = _mapping(monitors.get(source_id))
            if not record:
                continue
            record["outcome"] = "degraded"
            record["coverage_status"] = "covered_by_fallback"
            record["healthy_fallbacks"] = list(fallback_ids)
            monitors[source_id] = record
            changed = True
        if changed:
            self.save()

    def record_run_summary(self, summary: Mapping[str, object]) -> None:
        self.data["last_run_summary"] = {
            **summary,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        self.save()

    def migrate_case_identity(self, case: LotteryCase) -> str | None:
        """Move one legacy start-based case to the stable article-based ID.

        The old ID is retained as the Calendar identity so an already-created
        Google event is updated instead of inserting a second event.
        """

        seen_cases = _mapping(self.data.setdefault("seen_cases", {}))
        if case.case_id in seen_cases:
            self._drop_same_event_provisional_duplicates(case, seen_cases)
            return None

        current_urls = {
            stable_url_identity(value)
            for value in (case.official_url, case.source_url)
            if value
        }
        same_article: list[tuple[str, dict[str, Any]]] = []
        same_product_without_article: list[tuple[str, dict[str, Any]]] = []
        for old_id, raw_record in seen_cases.items():
            if not isinstance(raw_record, dict):
                continue
            if (
                raw_record.get("game_id") != case.game_id
                or raw_record.get("retailer_id") != case.retailer_id
                or str(raw_record.get("opportunity_kind") or "lottery")
                != case.opportunity_kind.value
            ):
                continue
            old_urls = {
                stable_url_identity(str(value))
                for value in (
                    raw_record.get("official_url"),
                    raw_record.get("source_url"),
                )
                if value
            }
            if current_urls & old_urls:
                same_article.append((old_id, raw_record))
            same_amazon_product = (
                case.retailer_id == "amazon_jp"
                and raw_record.get("canonical_product_key")
                == case.canonical_product_key
            )
            if (
                raw_record.get("canonical_product_key")
                == case.canonical_product_key
                and (
                    not current_urls
                    or not old_urls
                    or same_amazon_product
                )
            ):
                # Amazon招待は短縮URLや記事URLが投稿ごとに変わる。同じ商品
                # コードなら既存の配信履歴を引き継ぎ、再通知を防ぐ。
                same_product_without_article.append((old_id, raw_record))

        product_ids = {
            old_id
            for old_id, raw_record in same_article
            if raw_record.get("canonical_product_key") == case.canonical_product_key
        }
        exact_candidates = [
            candidate for candidate in same_article if candidate[0] in product_ids
        ]
        current_product_token = release_title_token(case.product_name)
        title_candidates = [
            candidate
            for candidate in same_article
            if current_product_token
            and release_title_token(str(candidate[1].get("product_name") or ""))
            == current_product_token
        ]
        if exact_candidates:
            candidates = exact_candidates
        elif title_candidates:
            candidates = title_candidates
        elif len(same_article) == 1 and is_provisional_product_name(
            str(same_article[0][1].get("product_name") or "")
        ):
            candidates = same_article
        elif (
            case.retailer_id == "amazon_jp"
            and same_product_without_article
        ) or len(same_product_without_article) == 1:
            candidates = same_product_without_article
        else:
            return None

        journal = _mapping(self.data.setdefault("delivery_journal", {}))

        def candidate_score(candidate: tuple[str, dict[str, Any]]) -> tuple[int, str, str]:
            old_id, previous = candidate
            delivery_records = [
                _mapping(journal.get(f"lottery:{kind}:{old_id}"))
                for kind in ("started", "scheduled")
            ]
            delivered = any(record for record in delivery_records)
            updated_at = max(
                (str(record.get("updated_at") or "") for record in delivery_records),
                default="",
            )
            return (int(delivered), updated_at, str(previous.get("start_at") or ""))

        old_id, previous = max(candidates, key=candidate_score)
        equivalent_ids = [candidate_id for candidate_id, _ in candidates]
        migrated = {**previous, "case_id": case.case_id}
        seen_cases[case.case_id] = migrated
        for candidate_id in equivalent_ids:
            seen_cases.pop(candidate_id, None)

        migrations = _mapping(self.data.setdefault("case_id_migrations", {}))
        prior_migration = _mapping(migrations.get(old_id))
        existing_sync = _mapping(self.data.setdefault("calendar_sync", {}))
        has_calendar_history = any(
            f"lottery:{kind}:{candidate_id}" in journal
            for kind in ("started", "scheduled")
            for candidate_id in equivalent_ids
        ) or any(
            f"lottery:{candidate_id}" in existing_sync
            for candidate_id in equivalent_ids
        )
        calendar_identity = str(
            prior_migration.get("calendar_identity")
            or (old_id if has_calendar_history else case.case_id)
        )
        migrations[case.case_id] = {
            "legacy_id": old_id,
            "legacy_ids": equivalent_ids,
            "calendar_identity": calendar_identity,
            "migrated_at": datetime.now(UTC).isoformat(),
        }

        for notification_kind in ("started", "scheduled"):
            new_key = f"lottery:{notification_kind}:{case.case_id}"
            old_keys = [
                f"lottery:{notification_kind}:{candidate_id}"
                for candidate_id in equivalent_ids
            ]
            delivered_records = [
                journal[old_key] for old_key in old_keys if old_key in journal
            ]
            if delivered_records and new_key not in journal:
                journal[new_key] = max(
                    delivered_records,
                    key=lambda record: str(
                        record.get("updated_at") if isinstance(record, dict) else ""
                    ),
                )
            for old_key in old_keys:
                journal.pop(old_key, None)

        calendar_sync = existing_sync
        old_sync_keys = [
            f"lottery:{candidate_id}" for candidate_id in equivalent_ids
        ]
        new_sync_key = f"lottery:{case.case_id}"
        if new_sync_key not in calendar_sync:
            for old_sync_key in old_sync_keys:
                if old_sync_key in calendar_sync:
                    calendar_sync[new_sync_key] = calendar_sync[old_sync_key]
                    break
        for old_sync_key in old_sync_keys:
            calendar_sync.pop(old_sync_key, None)
        return old_id

    def _drop_same_event_provisional_duplicates(
        self,
        case: LotteryCase,
        seen_cases: dict[str, Any],
    ) -> None:
        """Remove stale provisional records only when no Calendar orphan can result."""
        current_urls = {
            stable_url_identity(value)
            for value in (case.official_url, case.source_url)
            if value
        }
        journal = _mapping(self.data.setdefault("delivery_journal", {}))
        calendar_sync = _mapping(self.data.setdefault("calendar_sync", {}))
        current_sync = _mapping(calendar_sync.get(f"lottery:{case.case_id}"))
        current_event_id = current_sync.get("event_id")
        for old_id, raw_record in list(seen_cases.items()):
            if old_id == case.case_id or not isinstance(raw_record, dict):
                continue
            if (
                raw_record.get("game_id") != case.game_id
                or raw_record.get("retailer_id") != case.retailer_id
                or str(raw_record.get("opportunity_kind") or "lottery")
                != case.opportunity_kind.value
                or not is_provisional_product_name(
                    str(raw_record.get("product_name") or "")
                )
            ):
                continue
            old_urls = {
                stable_url_identity(str(value))
                for value in (
                    raw_record.get("official_url"),
                    raw_record.get("source_url"),
                )
                if value
            }
            if not current_urls.intersection(old_urls):
                continue
            old_sync_key = f"lottery:{old_id}"
            old_sync = _mapping(calendar_sync.get(old_sync_key))
            old_event_id = old_sync.get("event_id")
            old_journal_keys = [
                f"lottery:{kind}:{old_id}" for kind in ("started", "scheduled")
            ]
            has_old_history = bool(old_sync) or any(
                key in journal for key in old_journal_keys
            )
            same_calendar_event = bool(
                current_event_id
                and old_event_id
                and current_event_id == old_event_id
            )
            if has_old_history and not same_calendar_event:
                continue
            seen_cases.pop(old_id, None)
            calendar_sync.pop(old_sync_key, None)
            for key in old_journal_keys:
                journal.pop(key, None)

    def calendar_case_identity(self, case_id: str) -> str:
        migration = _mapping(
            _mapping(self.data.setdefault("case_id_migrations", {})).get(case_id)
        )
        return str(migration.get("calendar_identity") or case_id)

    def canonical_release_identity(self, release: Release) -> str:
        """Reuse the oldest delivered identity for one physical BOX across runs.

        merge_releases removes duplicates that appear in the same pipeline run.
        This state-backed lookup also covers alternating official and secondary
        URLs that appear on different runs.
        """

        target_key = release_dedupe_key(release)
        seen_releases = _mapping(self.data.setdefault("seen_releases", {}))
        candidates: list[tuple[str, dict[str, Any]]] = []
        for release_id, raw_record in seen_releases.items():
            if not isinstance(raw_record, dict):
                continue
            game_id = str(raw_record.get("game_id") or "")
            if not game_id:
                continue
            saved_key = release_dedupe_key_values(
                game_id,
                str(raw_record.get("product_name") or ""),
                str(raw_record.get("canonical_product_key") or ""),
                release_id,
            )
            if saved_key == target_key:
                candidates.append((release_id, raw_record))

        if not candidates:
            return release.release_id

        journal = _mapping(self.data.setdefault("delivery_journal", {}))
        calendar_sync = _mapping(self.data.setdefault("calendar_sync", {}))
        source_order = {"official": 0, "official_indirect": 1, "secondary": 2}

        def candidate_rank(
            candidate: tuple[str, dict[str, Any]],
        ) -> tuple[int, int, str, int, str]:
            release_id, raw_record = candidate
            delivery = _mapping(journal.get(f"release:{release_id}"))
            calendar_record = _mapping(calendar_sync.get(f"release:{release_id}"))
            first_recorded = min(
                (
                    str(record.get("updated_at") or "9999")
                    for record in (delivery, calendar_record)
                    if record
                ),
                default="9999",
            )
            tier = source_order.get(str(raw_record.get("source_tier") or ""), 9)
            return (
                0 if delivery else 1,
                0 if calendar_record else 1,
                first_recorded,
                tier,
                release_id,
            )

        return min(candidates, key=candidate_rank)[0]

    def calendar_payload_changed(self, key: str, payload_hash: str) -> bool:
        previous = _mapping(
            _mapping(self.data.setdefault("calendar_sync", {})).get(key)
        )
        return previous.get("payload_hash") != payload_hash

    def mark_calendar_synced(
        self,
        key: str,
        payload_hash: str,
        result: Mapping[str, str],
    ) -> None:
        sync = _mapping(self.data.setdefault("calendar_sync", {}))
        sync[key] = {
            "payload_hash": payload_hash,
            "event_id": result.get("event_id"),
            "status": result.get("status"),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self.save()
