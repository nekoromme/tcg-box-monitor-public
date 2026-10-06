# 店舗追加の進捗記録

最新の再開地点：[STATE.json](STATE.json)。日時は日本時間または明示されたUTC。

## 2026-10-04 初期設定

- 実行ID：`setup-20261004`
- 依頼：明日から定期起動し、GitHub台帳を最初に読み、少数ずつ作業して結果を次回へ引き継ぐ。
- 作成：優先順位付き候補10件、既存店14系列の調査メモ、実行手順、進捗状態。
- 今回は店舗追加・通知条件変更を行っていない。
- Worker最新main：`46e9d4b32671be31b06bbb51ab52c455b7a2d07f`（PR #29）。
- relay最新main：`5abf295477083e5ca86839779bf1c0966f3573ec`（PR #56）。
- 読み取れた最新inventory-sync：[run 37178593796](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37178593796)、2026-10-04 14:00:58 JSTに成功。
- 保存記録は14:00:53 JST、lastCompletedAtは14:00:52 JST。17時台の設定時点では古く、現在の健全性の証拠としては不足。
- 本番healthの直接取得は実行環境から403、検索経由も取得不可。アクセス経路の問題と本番障害を区別し、復旧済みとも故障とも断定しない。
- 次回最初の操作：最新Actions一覧・保存記録を読み、継続巡回、ログ鮮度、価格設定、日次境界をまたぐ24時間以上の安定を確認。必要なら既存inventory-syncを1回だけ実行し、そのIDを追う。
- 安定確認後の第一候補：ホビーステーション公式Yahoo!店。既存対象弾の新品BOXがあることを確認してから実装。
- 定期起動：明日2026-10-05から日本時間8時・14時・20時ごろを予定。作成結果は次の記録に追記。
- モデル希望：6.1 sol／極高。APIに指定欄がないため設定済みとはしていない。

## 今後の記録の形

各回、実行ID／対象／実際の変更／証拠URL・SHA・run ID／完了か未完了か／未完了理由／次回最初に行う具体的操作を追記。待機は待機と記録し、結果を捏造しない。

## 2026-10-04 定期起動の登録完了

- 実行ID：`setup-20261004`
- タスク「カード監視の段階的店舗追加」を作成し、有効状態・指示全文・Asia/Tokyo設定を再取得して確認した。識別子はSTATEに保存。
- 開始設定：2026-10-05 08:00 JST。毎日8時・14時・20時を基準とするflexible_schedule（各基準時刻から1時間以内の柔軟実行）。
- APIのnext_run_timeは未提示。上記は保存済みDTSTARTとRRULEで確認した設定であり、将来の実行済み報告ではない。
- 引き継ぎ6ファイルをGitHubから読み戻し、本文・候補ID・価格条件・内部リンクを確認した。
- 明日からの実装、候補店の通知実証、長時間観察は未着手。初回はSTATE.nextActionに従う。
- モデルと推論強度はAPIから変更できなかった。6.1 sol／極高への手動変更をユーザーへ案内する。

## 2026-10-05 08:14 JST 初回自律確認

- 実行ID：`20261005T0757JST-2s5ih7`
- 復旧確認：2026-10-04 10:51:38 JSTの復旧通知は `sent`。healthは10:53、23:29、翌7:29の3スナップショットで `ok`、lastCompletedAtが進行。最新inventory-sync [run 37240182291](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37240182291) も成功。
- 最新状態：Worker mainと稼働buildは `46e9d4b32671be31b06bbb51ab52c455b7a2d07f`／0.13.0で一致。relay mainは `f0f92a63a67754c7b4ce6f0d48f04e9dac8dd9f6`。保存は `monitor-gzip-v1`、価格policy v1（通常105%、通常30thだけ200%）、送信待ち0・失敗0・連続失敗0。
- 未完了：復旧から約21時間で、2026-10-05 09:00 JSTの無料枠リセットをまだ越えていない。24時間到達は10:51 JST。よって店舗の本番追加は行っていない。
- ホビーステーション：公式Yahoo!店内検索を実査。GD01/GD05/30thは0件で、他ゲームを含めても現行の有効対象は確認できず `deferred_no_target`。停止中GD02だけを理由に追加しない。
- BIGWEB：公式Angular画面の公開APIを特定。GD01通常BOX（5,200円）とGD05通常BOX（6,019円）が登録済みだが両方売切れ。売切れ、8パックセット、SC01、海外30thを区別できる専用アダプタの設計情報をSTATEへ保存し `ready` とした。
- 変更：引き継ぎ台帳だけ。店舗設定、通知条件、送信済み履歴、本番コードは変更していない。
- 次回最初の操作：10:51 JST以後の新しいhealthとinventory-syncを確認。無料枠リセット後も正常なら、最新Worker mainからBIGWEB専用APIアダプタの実装・テストへ進む。


## 2026-10-05 20:01 JST BIGWEB本番追加・初回実動作確認

- 実行ID：`20261005T105734776Z-9q4m2c`
- 実装：Worker [PR #30](https://github.com/nekoromme/tcg-cross-search/pull/30) でBIGWEB公開JSON API用アダプタ、[PR #31](https://github.com/nekoromme/tcg-cross-search/pull/31) で既存automatic ruleへの新店舗移行を追加。全186テスト成功。本番は `0.14.1 / 06426bb5c16c029bb8004a227ae6df9465e50fa7`、`/api/health` とmainが一致。
- 実巡回：2026-10-05 14:44〜19:48 JSTにBIGWEB一覧を11回、毎回1リクエスト・`status=ok`・対象2件。GD01は5,200円・売切れ（85観測、上限6,098円）、GD05は6,019円・売切れ（86観測、上限6,300円）。用品、8パックセット、スタートデッキ、海外版は対象へ追加していない。
- 既存状態：登録38弾／有効31／停止7、通常105%、通常30thだけ200%、`monitor-gzip-v1`、送信待ち0・失敗0・連続失敗0を維持。GD02/GD03/GD04/EB01等は停止のまま。過去送信済みIDも保持。
- 通知：BIGWEBの2商品は価格条件内だが売切れで、実在庫の通知機会なし。新規通知は送らず `awaiting_real_opportunity`。送信障害とは扱わない。
- 状態保存：定刻inventory-syncの記録が16:39〜20:00 JSTに空いたため、同じ成功run [37278868343](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37278868343) をattempt 2で一度だけ再実行し成功。20:00:59 JSTにhealth=`ok`、lastCompletedAt=20:00:57、gzip保存を確認。欠落時間中もCloudflare側のBIGWEB巡回は継続していたため、監視停止ではなくGitHub上の状態保存鮮度の問題として区別した。
- 観察：BIGWEBの観察開始は2026-10-05 14:44 JST。最短の24時間判定は2026-10-06 14:44 JST以後。それまでは次の店を本番追加しない。次回は定刻inventory-syncの自動復帰を先に確認する。


## 2026-10-06 08:00 JST BIGWEB夜間観察・保存鮮度確認

- 実行ID：`20261005T225635812Z-4m7h2x`
- BIGWEB実巡回：追加後約17時間。2026-10-05 14:44〜10-06 07:56 JSTに一覧35回、全て1リクエスト・`status=ok`・対象2件。GD01は5,200円・売切れを285回、GD05は6,019円・売切れを285回確認し、両対象とも取得失敗0。
- 条件維持：本番 `0.14.1 / 06426bb5c16c029bb8004a227ae6df9465e50fa7`、登録38／有効31／停止7、通常105%、通常30thのみ200%、`monitor-gzip-v1`、通知待ち0・失敗0・連続失敗0。停止商品と過去送信済みIDを保持。
- 通知：BIGWEBでは条件内の実在庫がまだ現れておらず、新規通知なし。送信障害ではなく `awaiting_real_opportunity` を継続。
- 保存起動：定刻inventory-syncは前回後に02:22 JSTで一度自動成功したが、以後07:59まで5時間超の記録欠落。workflow自体はactive、確認時のGitHub Statusは正常。GitHub公式にはscheduleが負荷時に遅延・破棄され得るとの説明がある。最新run [37347861347](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37347861347) をattempt 2で一度だけ再実行し、07:59:51 JSTにhealth=`ok`・lastCompletedAt=07:59:49・gzip保存を確認した。
- 判断：Cloudflare側のBIGWEB巡回は欠落時間中も継続しており、監視停止ではない。ただしGitHubへの自動保存安定性は未確認のため、次店追加は保留。24時間到達は2026-10-06 14:44 JST、無料枠の日次境界は09:00 JSTなので、次回は両方を越えた自動巡回・自動保存を確認する。


## 2026-10-06 14:08 JST BIGWEB 24時間判定前・定刻保存の自動復帰確認

- 実行ID：`20261006T050346908Z-jbypul`
- 定刻保存：12:17 JSTのinventory-sync [run 37408287617](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37408287617) がscheduleイベント・attempt 1で自動成功。07:59 JSTの手動再実行後、少なくとも1回は手動介入なしで保存できた。
- 一時失敗の区別：08:23 JSTの [run 37387910622](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37387910622) はWorker 0.14.2切替中の本番health HTTP403。直後のworkflow_run [37388131888](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37388131888) と12:17の定刻runでhealth=`ok`へ戻り、継続障害ではない。
- BIGWEB：一覧43回すべて成功・毎回1通信・対象2件。GD01は5,200円・売切れを354回、GD05は6,019円・売切れを355回確認し、両方とも取得失敗0。条件内の実在庫はまだなく通知機会なし。
- 条件維持：Worker mainと保存された本番は `0.14.2 / 35a194ea7e4d549090d29cdad9b7010f222f45cb` で一致。価格policy v1（通常105%、通常30thのみ200%）、停止7商品、`monitor-gzip-v1`、送信済み12・待機0・失敗0・連続失敗0。既存の送信済みIDも保持。
- 判断：取得時点は24時間到達の14:44 JSTより前。次店は追加せず、14:44以後の新しいhealth・定刻保存・BIGWEB観測で判定する。
