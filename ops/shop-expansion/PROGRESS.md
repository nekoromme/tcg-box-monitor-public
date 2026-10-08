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


## 2026-10-06 20:00 JST BIGWEB 24時間通過・ドラゴンスター再実査

- 実行ID：`20261006T105748719Z-7ud9nu`
- BIGWEB：追加後約29時間。公式一覧は53回すべて成功、毎回1通信、失敗0。GD01は5,200円・売切れを480回、GD05は6,019円・売切れを481回確認し、価格判定はいずれも上限内。
- 頻度調整：24時間以上新規ページなしの実ログに基づき、BIGWEB一覧は自動でquietモード・60分間隔になった。常時30秒巡回や予算引上げはしていない。
- 保存と既存条件：19:44 JSTのinventory-sync [run 37451728152](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37451728152) がschedule・attempt 1で成功。12:17 JST後も自動保存が継続し、health=`ok`、本番`0.14.2 / 35a194ea7e4d549090d29cdad9b7010f222f45cb`、policy v1（通常105%、通常30thのみ200%）、停止7、`monitor-gzip-v1`、送信待ち0・失敗0・連続失敗0、過去sent ID保持を確認。
- 通知：BIGWEBの2商品は売切れで実在庫の通知機会なし。新着なしと送信障害を混同せず、新規通知は送っていない。
- ドラゴンスター：公式トップ・シリーズ一覧・GD01/GD05シリーズを再実査。公開表示は参照できたが、シリーズ一覧はシングル中心で、新品欄の現行掲載はST10スタートデッキのみ。対象のGD01/GD05通常BOXがないため本番追加せず`deferred_no_target`。対象掲載時だけ1回再確認し、403回避はしない。
- 判断：BIGWEBは24時間条件を通過。安全側で48時間（2026-10-07 14:44 JST）まで最終観察を継続し、それまでは次店を本番追加しない。


## 2026-10-07 08:00 JST 夜間観察・後方候補の判定更新

- 実行ID：`20261006T225712Z-shop`。最初に最新shop-expansion-state head `6e23da45b23d17b2e3827d004fd36d85dd022d1e` と6文書を取得し、競合検出付きforce=falseコミットでlease取得。
- 本番照合：Worker mainとActions経由の本番healthは `0.14.2 / 35a194ea7e4d549090d29cdad9b7010f222f45cb` で一致。relay mainは `02280ec0b445b4e490249c451aa3ff7cafa82a1e`。両repoに関連open PRなし。本番への直接web取得は経路エラーで、障害認定には使わない。
- 自動保存：[run 37536498080](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37536498080) はworkflow_run、[run 37536837347](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37536837347) はschedule、共にattempt 1で成功。health=`ok`、lastCompletedAtは06:49:36→06:52:38 JSTに進行。夜間のscheduleには数時間の間隔欠落があるが最新保存は現行の鮮度閾値内。手動再実行/dispatchなし。
- BIGWEB：追加後約40時間。公式一覧64回すべて成功・毎回1通信、GD01は5,200円・売切れ660観測、GD05は6,019円・売切れ662観測、両対象失敗0。10/7の日付別discoveryログでも00:02〜06:04 JSTの毎時7巡回を確認。条件内の実在庫なしで配送実証はawaiting_real_opportunity。
- 保持：登録38／有効31／停止7、上限GD01 6,098円・GD05 6,300円・通常30th 14,400円、policy v1（105%/通常30th200%）、gzip 116,001 bytes/2 chunks。sent12・pending0・failed0・連続送信失敗0。既存の2受理IDをraw状態内で再確認。quota実利用量は未取得だがhealthに上限停止の証拠なし。
- 個別の注意：メディアワールド3商品にHTTP429、一部一覧失敗は待機扱い。全体は正常で、失敗を売切れに変えていない。次回の既存snapshotで回復を確認し、突破/巡回増加はしない。
- ホビーサーチ：公式GD05は5,717円・品切れ中・注文再開メールあり。最新コード/設定で既存承認済みの再入荷メール連携は確認できず、抽選経路2件も停止中。新規登録/接続は依頼範囲外なのでmanual_requiredとして今回は最終保留。規約の商用情報利用制限、メールが予約ではないことをCANDIDATESへ根拠URL付きで保存。
- 竜のしっぽ：公式新品・予約欄にGD01通常24パックBOXを特定。商品 /product/1273 は5,800円・売切れ、未開封明記。候補をresearchingへ更新した。新品欄所属が確認できたが取得条件・無通知dry-run・回帰検証は未実施で、本番追加はしていない。箱傷み条件と返品3日/7日の差も保存。
- フルコンプ：公式未開封品欄の30thはFUTURISTIC BOX・79,800円・中古A。通常BOXへ混ぜない。現在有効な新品通常BOXの掲載を今回の限定調査で特定できず、今回は根拠付き最終保留とした。新規具体的掲載時だけ再評価。
- 注意情報の実装調査：既存STORES.noteは概要があるが、最新sendDiscordに出典/確認日付きの注意リンクがなく、public/ui.jsの表示行にも注意を描画していない。公式infoページの動画条項の新しい抽出確認は未完了なので10/4の確認日を更新せず、別の小PRで仕上げる次工程として記録。
- 実際の変更：引き継ぎSTATE/CANDIDATES/EXISTING-STORES/PROGRESSだけ。本番コード、店舗設定、通知policy、送信履歴は変更せず、購入/登録/通知試験なし。
- 次回最初の操作：最新head・Actions・monitor-stateを読み直す。BIGWEB48時間は10/7 14:44 JST到達のため、それより前なら読み取り調査のみ。到達後の正常snapshotで最終判定してから竜のしっぽGD01の公開取得/規約/無通知回帰検証へ。メディアワールド429とGitHub保存鮮度も再確認する。


## 2026-10-07 14:00 JST 最終判定前の監視・候補整理

- 実行ID：`20261007T045646Z-exp`。最新shop-expansion-stateから競合検出付きでleaseを取得し、終了時に解放。
- 本番照合：Worker mainと保存された本番は `0.14.2 / 35a194ea7e4d549090d29cdad9b7010f222f45cb` で一致。relay mainは `c0e241521446c549abcd538715328436a150f614`。最新inventory-sync [run 37562751081](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37562751081) はworkflow_run・attempt 1で成功し、11:36 JSTにhealth=`ok`・lastCompletedAt進行を確認。
- 鮮度判断：13:56 JST時点で最新保存は約140分前となり、現行135分目安を約5分超過。成功runで全体healthも正常なので障害とは断定せず、14:44 JST以後の新しい自動保存を48時間最終判定の証拠にする。手動再実行なし。
- BIGWEB：一覧69回・失敗0・毎回1通信。GD01は5,200円・売切れ736観測、GD05は6,019円・売切れ737観測、両商品ページ失敗0。48時間終了は14:44 JSTのため、今回は完了扱いせず次店も追加していない。
- 条件維持：policy v1（通常105%、通常30thだけ200%）、GD01上限6,098円、GD05上限6,300円、通常30th上限14,400円、停止7商品、`monitor-gzip-v1`、sent12・pending0・failed0・連続送信失敗0を確認。通知機会なしは送信障害にしていない。
- メディアワールド：一覧は成功54・失敗0へ回復。ただし商品ページ4件にはHTTP429が1〜2回残存。短周期再試行や回避はせず、失敗を売切れに変換しない。
- あみあみ：GD05通常24パックBOXは確認できたが販売停止中。公式規約で事前承諾のない営利目的利用と監視ツールを含む自動化利用が禁止されるため、今回用途では `excluded` の最終判断。許可取り・新規登録・制限回避なし。
- カードショップセラ：現在の公式通販はMTG中心で、既存対象のGD01/GD05/通常30th新品BOXを限定的な公式検索で特定できず、対象作品を増やさない条件では追加実益なし。全商品不在の断定はせず、具体的な新品通常BOX掲載時だけ再評価する最終保留。
- 実際の変更：引き継ぎSTATE/CANDIDATES/PROGRESSのみ。本番コード・店舗設定・通知policy・履歴・sent ID・巡回頻度は変更せず、購入・登録・通知送信なし。
- 次回最初の操作：14:44 JST以後の最新head・Actions・monitor-stateを読む。新しい正常snapshotでBIGWEB48時間を最終判定し、完了後に竜のしっぽGD01の公開取得・規約・無通知回帰検証へ進む。メディアワールド商品ページ429の自然回復も確認する。


## 2026-10-07 20:20 JST BIGWEB完了・竜のしっぽ本番追加

- 実行ID：`20261007T110637Z-exp`。最新台帳へ競合検出付きでleaseを取得し、外部操作の意図と返却IDを都度STATEへ保存、終了時に解放。
- BIGWEB：48時間超の最終snapshotで一覧77回成功・失敗0・毎回1通信。GD01は5,200円・売切れ878観測、GD05は6,019円・売切れ879観測、商品ページ失敗0。health正常、実在庫なしで通知機会なしとして最終完了。
- 竜のしっぽ実装：Worker [PR #33](https://github.com/nekoromme/tcg-cross-search/pull/33) をマージ。公式「新品・予約商品」9件の固定一覧を30分起点で1通信だけ読み、広いシングル一覧や検索語別の重複取得を避ける。対象一致後も商品詳細確認前には通知しない。
- 回帰：実在のGD01商品1273を基に、通常24パックBOX・5,800円・売切れを識別し、GD03/GD04/EB01・スタートデッキ・用品を混ぜないfixtureを追加。自動同期でGD01/GD05へ店舗を追加し、停止済み弾を再開しないテストを含め、CI 193件成功・失敗0、Wrangler dry-run成功。
- 本番：`0.14.2 / 823986b3a3108ced89e76161b5de01885d066110`。main push CI [run 37612951250](https://github.com/nekoromme/tcg-cross-search/actions/runs/37612951250) 成功。本番直接取得は経路制限のため、既存inventory-sync [run 37610977429](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37610977429) をattempt 2で1回だけ再実行し、health=`ok`、main SHA一致、lastCompletedAt進行を確認。
- 状態維持：登録38／有効31／停止7、policy v1（通常105%、通常30thのみ200%）、`monitor-gzip-v1`、sent12・pending0・failed0・連続送信失敗0。竜のしっぽはGD01/GD05へ追加、ポケカ30thには追加なし。送信済み履歴は保持し、通知試験なし。
- 観察：20:19 JSTの保存では竜のしっぽが30分・通常モードで登録済みだが、初回一覧通信はまだ未実行。実巡回成功を捏造せず、観察開始を20:16:38 JST、24時間判定を10/8 20:16、48時間判定を10/9 20:16とした。それまで次店は追加しない。
- メディアワールド：一覧429は店舗別待機を継続。全体healthは正常で、頻度追加・制限回避・売切れ誤判定はしていない。
- 次回最初の操作：最新snapshotで竜のしっぽ一覧のsuccesses/lastResultと、商品1273の登録・5,800円・売切れ・失敗数を確認。未実行/失敗は売切れにせず原因分類し、24時間未満は次店を追加しない。


## 2026-10-08 08:06 JST 竜のしっぽ初回実巡回・夜間観察

- 実行ID：`20261007T230415418Z-exp`
- 最新inventory-sync：[run 37694811855](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37694811855) は2026-10-08 07:14 JSTに成功。保存healthは `ok`、lastCompletedAtは07:14:31 JST、Workerは `0.14.2 / 823986b3a3108ced89e76161b5de01885d066110` で最新mainと一致。
- 竜のしっぽの公式新品・予約一覧は本番で22回成功・0失敗。初回一覧（2026-10-07 20:20:44 JST）は1通信で14商品リンクを読み、GD01商品 `/product/1273` を1件登録。その後も毎回1件一致。
- 商品1273は5,800円、通常24パックBOX、売切れ。GD01通知上限6,098円以下だが在庫なしなので通知なしが正常。詳細ページの一時通信失敗1回は回復し、最新は `failures=0`、観測170回。
- 全体は登録38弾・有効31弾・停止7弾、active pages 77、storage `monitor-gzip-v1`、価格policy v1（通常105%、通常30thだけ200%）、sent 12・pending 0・failed 0、delivery連続失敗0を維持。
- メディアワールドは一覧HTTP 429で店舗別待機中（一覧success 60 / failure 2、個別3ページは各連続失敗1）。全体healthは `ok` であり、失敗を売切れ扱いせず既存の待機・再試行に任せる。
- 竜のしっぽ追加から24時間は2026-10-08 20:16 JST、48時間は2026-10-09 20:16 JST。まだ24時間未到達なので次店舗は追加していない。
- 次回：24時間までは同じ本番巡回と全体healthを再確認。到達後も正常なら最低観察通過を記録し、48時間まで観察を続ける。


## 2026-10-08 14:05 JST 竜のしっぽ24時間前確認

- 実行ID：`20261008050416676Z-exp`。本番変更なし。
- 最新inventory-sync [run 37716864033](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37716864033) は11:14 JSTに成功。保存healthは `ok`、lastCompletedAtは11:14:51 JST、Workerは `0.14.2 / 823986b3a3108ced89e76161b5de01885d066110` でmainと一致。
- 竜のしっぽ一覧は30回成功・0失敗へ進行。GD01商品1273は5,800円・売切れ・価格条件内、商品ページの最新failuresは0、観測234回。条件内在庫がないため通知なしは正常。
- メディアワールドの一覧429は自然回復し、一覧success 61 / failure 0、quiet・60分へ移行。個別2ページの単発429は残るため既存待機を継続し、売切れ扱い・頻度引上げ・制限回避は行わない。
- 条件維持：登録38／有効31／停止7、active pages 77、policy v1（通常105%、通常30thのみ200%）、`monitor-gzip-v1`、sent12・pending0・failed0・連続送信失敗0。
- 追加24時間は本日20:16 JST。判定前のため次店舗は追加せず、次回の新しい保存記録で通過可否を確認する。最終48時間は10月9日20:16 JST。


## 2026-10-08 20:06 JST 竜のしっぽ24時間判定直前

- 実行ID：`20261008110542883Z-exp`。本番変更なし。
- 最新inventory-sync [run 37756490293](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37756490293) は18:25 JSTに成功。health=`ok`、lastCompletedAtは18:25:47 JST、Workerは `0.14.2 / 823986b3a3108ced89e76161b5de01885d066110` でmainと一致。
- 竜のしっぽ一覧は44回成功・0失敗。GD01商品1273は5,800円・売切れ・価格条件内、商品ページfailures=0、観測349回。条件内在庫なしのため通知なしは正常。
- メディアワールド一覧429は回復後に再発。最新保存は一覧success 65 / failure 3・店舗別待機、個別2ページは各単発429。正常取得と429を往復しているため、売切れ扱い・高頻度化・制限回避をせず既存待機を継続。全体healthは正常。
- 条件維持：登録38／有効31／停止7、active pages77、policy v1（通常105%、通常30thのみ200%）、`monitor-gzip-v1`、sent12・pending0・failed0・連続送信失敗0。
- 最新保存が24時間到達（本日20:16 JST）より前のため、10分早く通過扱いせず次店舗も追加していない。次回の24時間超snapshotで最低観察を判定する。最終48時間は10月9日20:16 JST。


## 2026-10-09 07:56 JST 竜のしっぽ24時間最低観察通過

- 実行ID：`20261008225554977Z-exp`。本番コード・通知設定の変更なし。
- 最新inventory-sync [run 37853172935](https://github.com/nekoromme/tcg-box-monitor-public/actions/runs/37853172935) は07:24 JSTにattempt 1で成功。health=`ok`、lastCompletedAtは07:24:19 JST、Workerは `0.14.2 / 823986b3a3108ced89e76161b5de01885d066110` でmainと一致。
- 竜のしっぽ一覧は24時間超で59回成功・0失敗。24時間以上新規ページなしの実績によりquiet・60分間隔へ自動移行。全店高頻度化や予算引上げなし。
- GD01商品1273は5,800円・売切れ・価格条件内、商品ページのcurrent failures=0、正常観測555回。一時通信失敗1回は回復済み。在庫なしのため通知なしは正常で、送信障害と混同していない。
- 条件維持：登録38／有効31／停止7、active pages 77、policy v1（通常105%、通常30thのみ200%）、`monitor-gzip-v1`、sent12・pending0・failed0・連続送信失敗0。
- メディアワールドは一覧HTTP429で店舗別待機中（success 67 / failure 1）。商品ページのcurrent failuresは0、全体healthは正常。売切れ誤判定・頻度引上げ・制限回避はしていない。
- 判断：竜のしっぽは最低24時間観察を正常通過。最終48時間は本日20:16 JSTのため、それまでは次店舗を追加しない。到達後の新しい正常snapshotで最終判定する。
