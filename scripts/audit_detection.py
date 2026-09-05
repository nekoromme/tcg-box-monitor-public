"""Read-only inventory: candidate evidence is not inferred from HTTP success.

PYTHONPATH=src python scripts/audit_detection.py --state-ref origin/monitor-state
Add --state-file FILE to overlay a newer downloaded state without changing it.
No network, notifications, calendar writes, or monitor state mutations occur.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path

from tcg_monitor.config import load_config
from tcg_monitor.social_discovery import social_discovery_urls


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-ref", default="origin/monitor-state")
    parser.add_argument("--since", default="2026-08-01")
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--config", default="sites.yaml")
    args = parser.parse_args()
    ref = git("rev-parse", "--verify", "--end-of-options", args.state_ref).strip()
    commits = git("log", "--reverse", f"--since={args.since}", "--format=%H",
                  ref, "--", "monitor_state.json").splitlines()
    history: dict[str, dict[str, dict]] = defaultdict(dict)
    state: dict = {}
    for commit in commits:
        state = json.loads(git("show", f"{commit}:monitor_state.json"))
        for source_id, monitor in state.get("monitors", {}).items():
            timestamp = monitor.get("last_fetch_at")
            if timestamp:
                # A saved state can retain a source from earlier/partial runs.
                history[source_id][timestamp] = monitor
    if args.state_file:
        state = json.loads(args.state_file.read_text(encoding="utf-8"))
    config = load_config(args.config)
    enabled = [s for s in config.sources if s.enabled and any(
        s.supports(game_id) for game_id in config.active_game_ids)]
    print("# トレカ検知・経路別実証棚卸し\n")
    print(f"履歴参照: `{ref}`。保存スナップショット: {len(commits)}件。")
    print(f"設定: {len(config.sources)}経路、実行対象: {len(enabled)}経路。\n")
    print("『候補あり』はそのソースの解析実績。通知成功や全URLの検証を意味しない。")
    print("履歴にURL別記録がない期間は、ソース実績から個別URLの作動を推定しない。")
    print("候補ゼロは、未開催・期限切れ・対象外条件・取得不良のいずれもあり得る。\n")
    print("| ソース | 有効 | 保存履歴で候補あり/実取得回数 | 今回候補 | 今回の取得状態 |")
    print("|---|---|---:|---:|---|")
    for source in config.sources:
        records = list(history[source.id].values())
        positive = sum(int(record.get("parsed_count") or 0) > 0 for record in records)
        current = state.get("monitors", {}).get(source.id, {})
        enabled_label = "ON" if source in enabled else "OFF"
        print(f"| {source.id} | {enabled_label} | {positive}/{len(records)} | "
              f"{current.get('parsed_count', '未実行')} | {current.get('outcome', '未実行')} |")
    print("\n## URL別の今回の確認（旧履歴は記録なし）\n")
    for source in enabled:
        current = state.get("monitors", {}).get(source.id, {})
        routes = current.get("routes", {})
        print(f"### {source.name}\n")
        urls = social_discovery_urls(source) if config.system.get("social_account_fallback") \
            else source.discovery_urls
        for url in dict.fromkeys([*urls, *routes]):
            route = routes.get(url, {})
            status = route.get("status", "今回未実行・実証なし")
            count = route.get("parsed_count", 0)
            extra = {key: value for key, value in route.items()
                     if key in {"error", "diagnostics", "alerts", "discovered_urls"} and value}
            print(f"- [{url}]({url}): `{status}`、候補{count}件。"
                  + (json.dumps(extra, ensure_ascii=False) if extra else ""))
        print()


if __name__ == "__main__":
    main()
