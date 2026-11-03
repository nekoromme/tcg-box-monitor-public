"""大きな画像キャッシュを含まない、外部確認用の監視・配信台帳を保存する。"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def diagnostics(state: dict[str, Any]) -> dict[str, Any]:
    summary = state.get("last_run_summary", {})
    active = set(summary.get("monitored_source_ids", []))
    monitor_fields = (
        "outcome", "coverage_status", "healthy_fallbacks", "checked_at", "last_success_at",
        "last_candidate_at", "consecutive_failures", "http_status", "reason_code",
        "fetch_method", "lottery_candidates", "release_candidates",
        "last_error", "failure_cause", "failure_attempts",
    )
    return {
        "schema_version": 1,
        "code_sha": os.getenv("GITHUB_SHA", "local"),
        "recorded_at": datetime.now(UTC).isoformat(),
        "armed": state.get("armed", False),
        "last_run_summary": summary,
        # 通知済み・予定IDは本体から複写するだけ。大きい取得本文や画像は出さない。
        "seen_cases": state.get("seen_cases", {}),
        "delivery_journal": state.get("delivery_journal", {}),
        "calendar_sync": state.get("calendar_sync", {}),
        "case_id_migrations": state.get("case_id_migrations", {}),
        # 画像キャッシュで本体が大きくなっても、障害経路は小さい診断ファイルで追える。
        # 正常経路の本文・大量の過去ログは複写せず、失敗のある監視先だけ残す。
        "monitors": {
            key: {
                **{field: value[field] for field in monitor_fields if field in value},
                **({"routes": value.get("routes", {})}
                   if value.get("last_error") or value.get("outcome") != "success" else {}),
            }
            for key, value in state.get("monitors", {}).items() if key in active
        },
        "ocr_pending_count": len(state.get("ocr_pending", {})),
    }


def main() -> None:
    source, destination = map(Path, sys.argv[1:3])
    state = json.loads(source.read_text(encoding="utf-8"))
    destination.write_text(json.dumps(diagnostics(state), ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")


if __name__ == "__main__":
    main()
