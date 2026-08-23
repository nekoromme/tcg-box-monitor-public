# Codexへそのまま渡す実装プロンプト v2

下のコードブロックを最初から最後までコピーし、7つの成果物を置いたGitHubリポジトリでCodexへ渡してください。質問に答えなくても、認証情報以外はCodexが合理的に判断して完成させる指示になっています。

```text
あなたはこのリポジトリの実装担当です。設計や雛形だけで終わらせず、ポケモンカードゲームとONE PIECEカードゲームの「BOX抽選受付開始」と「BOX新弾発売日」を監視するシステムを、実行可能なコード、テスト、GitHub Actions、初心者向けREADMEまで完成させてください。

ユーザーはプログラミング初心者です。公開情報と同梱文書から合理的に判断できる点を質問で止めないでください。Discord・Googleの秘密値がなくても、モック、fixture、dry-runまで完成させ、最後にユーザー本人しかできない設定だけを具体的に示してください。

最初に、必ず次を順番に読んでください。

1. START-HERE.md
2. implementation-spec.md
3. sites.yaml
4. site-research.md
5. source-index.md
6. unresolved-issues.md

sites.yamlはschema_version 2が正です。文書間に軽微な表現差がある場合、機械設定はsites.yaml、動作はimplementation-spec.md v2、事実関係はsite-research.mdとsource-index.md、不確実性はunresolved-issues.mdを優先してください。URLや日時を推測で追加しないでください。

## 完成させる機能

対象ゲーム:

- pokemon_card（ポケモンカードゲーム）
- one_piece_card（ONE PIECEカードゲーム）

対象イベント:

1. 新弾・再販を問わないBOX商品の抽選受付開始
2. 公式商品カタログに掲載されるBOX新商品の発売日

除外:

- スターター、スタートデッキ、構築済み・アルティメットデッキ
- スペシャルセット、カードセット、ポケモンセンターセット等、販売単位がセットの商品
- 単品パック、束パックだけでBOXと確認できないもの
- スリーブ、ケース、プレイマット等の周辺用品
- 通常販売、先着入荷だけ、当選発表、購入・支払・受取期限、キャンペーン、大会

通知・Calendar:

- 抽選を将来日時で発見したらDiscordへ「抽選予定」、開始時刻到来時に「抽選開始」を各1回
- 開始後に初めて見つけ、受付中なら「抽選開始済み」を即時通知
- 正確な抽選開始日時をGoogle Calendarへ登録。受付終了日時は登録しない
- 公式に日付だけある抽選は終日予定。二次情報で時刻なしは警告のみ
- 公式新弾発売日はDiscord通知＋終日Calendar
- 発売月しかない場合はDiscord予告だけ。日付確定後に同じrelease_idへCalendar登録
- 発売日訂正時は同じCalendarイベントを更新し、「発売日変更」を通知
- 同じ通知種類、同じ案件、同じCalendar予定を重複させない

件名:

- 【ポケカ抽選予定】店舗／商品
- 【ポケカ抽選開始】店舗／商品
- 【ワンピカード抽選予定】店舗／商品
- 【ワンピカード抽選開始】店舗／商品
- 【ポケカ新弾発売日】商品
- 【ワンピカード新弾発売日】商品
- Calendarは【ポケカ抽選開始】、【ワンピカード抽選開始】、【ポケカ発売】、【ワンピカード発売】

正常通知には、ゲーム、店舗、商品、商品分類、開始または発売日、検出日時、公式応募／商品URL、情報掲載URL、抽出方法、確度、情報源区分、Calendar結果、内部IDを含めてください。二次情報の場合は「二次情報・公式ページで最終確認」と明示してください。

異常通知には、ゲーム、店舗または情報源、対象URL、タイトル、関連語、理由コード、従来との変更点、HTTP状態、手動確認URLを含めてください。

## 情報源の優先順位

必ず次の順にします。

1. official: ゲーム公式・小売店公式
2. official_indirect: ゲーム公式からリンクされた販売先情報
3. secondary: SNKRDUNK MAGAZINE

SNKRDUNKは公式と同格にしないでください。公式ウェブで開始を把握しにくいヤマダ、コジマ等の代替と、新弾記事の発見補助です。

- 正確な年月日・時刻がある二次抽選だけ確度mediumでCalendar登録可
- 記事内の公式応募リンクを優先表示
- 後から公式で同じ案件を確認したら、新規案件を作らず出典・確度・説明を更新
- 公式と二次情報が違う場合は無言で片方を採らず、secondary_official_conflict
- 二次記事の店舗行を公式固定ページで確認できない場合はsecondary_claim_not_visible_on_official_page
- 日付と曜日が不一致ならweekday_date_mismatch
- 未設定店舗はunknown_retailerとして警告し、自動Calendar登録しない
- Amazonの招待リクエストは開始日時なしとしてCalendar禁止

## 必須の実装構成

Python 3.12、src layout、パッケージ名tcg_monitorを使ってください。最低限次を実装します。

- 設定: sites.yaml v2の型付き読込、スキーマ検証、重複ID・URL・enum検証
- 取得: httpx、条件付きGET、最低ホスト間隔、timeout、限定retry、サイズ上限、秘密マスク
- ブラウザ: render_modeで明示された時だけPlaywright。HTTPが殻の場合に1回。CAPTCHA、Cloudflare、人間確認、ログインを回避しない
- 発見: 一覧、新規リンク、固定ページ意味ハッシュ、商品カタログ、SNKRDUNK記事内店舗ブロック差分
- 分類: game_id別のBOX正例・除外語、商品ブロック単位の証拠付き結果
- 日時: 日本語日時、全角記号、午前午後、正午、年省略、曜日検証、日付のみ、月のみ
- パーサー: 共通、ポケカ公式商品、ONE PIECE公式商品／トピックス、SNKRDUNK、ゲオ、ポケモンセンター、楽天、ヨドバシ、キッズ、イオン、健康監視
- 優先順位: official > official_indirect > secondaryの統合と競合検出
- 状態: monitor-stateブランチ、スキーマversion、意味ハッシュ、構造指紋、case/release、配信ジャーナル、異常抑制、移行処理
- Discord: Webhook、wait=true、正常／予定／開始／発売／変更／異常、payload長制限、秘密マスク
- Google Calendar: サービスアカウント、決定的event ID、extendedProperties、insert 409冪等、発売日のupdate
- CLI: validate-config、baseline、dry-run、run、arm、status。サイト・ゲーム・情報源の絞込オプション
- ログ: 1行1JSON。run_id、source_id、game_id、phase、outcome、reason_codeを含む
- Actions: test.ymlとmonitor.yml。毎日05:00・17:00（日本時間）のschedule、workflow_dispatch、concurrency、最小権限、Secrets検査
- README: GitHub画面、Discord、Google Cloud、Calendar共有、Secrets、baseline、dry-run、arm、障害対応を初心者向けに説明

外部サービスの実処理はadapter interfaceにし、テストでは必ずモックできるようにしてください。通常実行でOpenAI API、他の生成AI、有料検索API、スクレイピング代行APIを一切使わないでください。

## データ識別と配信

抽選:

case_id = sha256(game_id | retailer_id | canonical_product_key | normalized_start)

発売日:

release_id = sha256(game_id | canonical_product_key)

情報源URLをcase_idへ入れないでください。二次情報から公式へ昇格しても同じ案件にするためです。ワンピはOP/EB/PRBコードをcanonical_product_keyの第一候補にします。ポケカは公式商品URL内の安定ID、なければ厳格な公式商品名を使います。曖昧な文字列類似度だけで別商品を統合しないでください。

配信は状態ジャーナルを使い、Calendar作成→Discord送信→Calendar説明更新→completeの順で冪等にします。将来抽選のscheduledと開始時のstartedは別notification_kindです。同じkindは1回だけです。Discord応答前に落ちて送信有無が不明なら、正常通知を無条件再送せずdelivery_unknown異常にします。

## 「沈黙しない」必須ルール

次は候補なしとして捨てず、異常を作ってください。

- 新しい対象ゲーム／BOXらしいページなのに発売日または抽選開始を取れない
- 抽選、応募、受付があるのに開始を取れない
- 複数開始候補を一意にできない
- 当選・購入・発売日時しか取れない
- expected_elementsやJSONキーが消えた
- 本文・構造が大きく変化した
- HTTP 403、429、5xx、空本文が連続
- ログイン、CAPTCHA、アクセス確認、エラーページに置換
- 日時が不自然に過去・未来
- SNKRDUNKの店舗見出し・表が消えた
- 公式と二次情報が食い違う
- OP/EB/PRBコードと商品名が競合

サイト固有抽出が失敗したら、安定要素→開始／発売ラベル周辺→一般日時補助→異常の順です。フォールバックが成功しても従来要素が消えた警告は消さないでください。異常はfingerprintで抑制し、初回、24時間未解決、回復を通知します。

## 実装順

この順で進め、各段階でテストを通してください。

1. 設定、models、HTTP、状態、日時、ゲーム別BOX分類、Discord／Calendar adapter
2. ポケカ公式商品一覧とONE PIECE公式商品一覧の発売日
3. ONE PIECE公式トピックス／商品ページとプレミアムバンダイ抽選
4. ポケモンセンターとゲオの公式ポケカ抽選
5. 楽天ブックスとヨドバシの固定ページ
6. SNKRDUNKのポケカ／ワンピ発売記事、店舗ブロック差分、ヤマダ／コジマ代替
7. キッズリパブリック、イオン、健康監視
8. GitHub Actions、README、全受入テスト

Amazonは手動ASIN警告を任意機能としてよく、開始日時Calendarは実装しません。麦わらストアはsites.yamlで無効のままにし、検証fixtureがない状態で有効化しないでください。

## 必須テスト

ネットワークと実Secretsなしで全テストが通るよう、調査文書にある公式URLから解析に必要な最小HTML断片fixtureを作ってください。ページ全文を大量保存しないでください。各fixtureに元URL、取得／調査日、元ハッシュが取れる場合はハッシュ、期待値をmetadataとして残します。

最低限:

- ポケカ公式発売日3件、スターター除外、発売日変更、販売日要素消失
- ONE PIECE公式OP-16/15/14/13、EB-05月のみ、デッキ除外、URL形式3種
- ONE PIECE公式の発売日・応募・当選日時混在、OP-16とOP-13抽選
- ポケモンセンターBOX3件＋セット負例
- ゲオBOX＋スターター混在、デッキのみ負例
- 楽天の混在表、ワンピ二次情報との公式不一致
- ヨドバシの申込・結果・注文日時混在
- キッズのBOX／5パック、アプリ／ウェブ、地域、年省略
- SNKRDUNKポケカのヤマダ／コジマ複数回、ワンピ32599型、Amazon招待除外
- SNKRDUNKの記事内店舗追加、未知店舗、曜日不一致、公式リンク欠落、再販通常入荷除外
- 表・ラベル・JSON項目消失、空ページ、403、ログイン、Cloudflare、日時複数
- case_id／release_id、二次→公式昇格、競合、予定→開始、発売日update、3回再実行の冪等性
- Secrets・Webhook・秘密鍵がログ、例外、fixtureへ出ないこと

ruff、mypy、pytestを実行し、カバレッジ85%以上にしてください。実サイトをCIテストから呼ばないでください。必要ならfixtureの現行性確認用の手動workflowを別にし、正常CIとは分離してください。

## 初期化と安全性

- baselineは現在見える抽選を既知化し、正常通知・Calendar登録しない
- `--include-future-releases`時だけ未来の公式発売日を初期Calendar登録できる
- baseline完了後だけarm可能
- armedでないschedule runは配信せず明示エラー
- dry-runはSecretsなしで、候補、除外理由、異常、予定payloadを表示
- 初回から全過去案件を通知しない
- 同一ホスト最低5秒、条件付きGET、サイト別pollを守る
- WAF・CAPTCHA・ログインを突破しない
- robots.txtと規約URLをREADMEに残し、運用者が定期確認できるようにする

## 最後まで実行すること

1. リポジトリを確認し、既存のユーザー変更を壊さない
2. 上記を実装する。TODO、pass、ダミー成功、未接続の主要経路を残さない
3. 設定検証、ruff、mypy、pytestを実行し、失敗を直す
4. Secretsなしでvalidate-config、dry-run、fixtureベースのデモを実行する
5. READMEの手順と実コマンドが一致するか確認する
6. 実装ファイル一覧、テスト結果、実サイト未検証箇所、ユーザーが次に行うSecrets設定を最終報告する

認証情報がないことを理由に質問して止まらないでください。実Webhook・Calendarへの送信だけ未実行として明記し、それ以外を完成させてください。公開情報で断定できない仕様はunresolved-issues.mdの安全側方針に従ってください。
```
