# はじめに

通常運用はGitHub Actionsの`monitor` workflowだけで完結します。定期実行は毎日6回です。

- 作品別の監視切り替えは`GAME_MONITOR_MODES.txt`を編集します。
- 手動確認は`Actions` → `monitor` → `Run workflow`から`dry-run`または`run`を選びます。
- `baseline`と`arm`は初回設定用です。既存状態を移行済みなら再実行しません。
- 通知先とGoogleカレンダー連携の変更は、GitHub Actions Secretsで行います。
- 監視先は`sites.yaml`、監視状態は同じリポジトリの`monitor-state`ブランチで管理します。

詳しい構成、Secrets、ローカル実行方法は`README.md`を参照してください。
