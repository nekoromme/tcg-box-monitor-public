# ポケカ／ワンピカード BOX抽選開始・新弾発売日監視システム 実装仕様書

## 1. 目的と完成条件

公式の公開ウェブ情報を定期監視し、ポケモンカードゲームとONE PIECEカードゲームについて、次を検出する。

1. 新弾・再販を問わない、BOXとして販売される商品の抽選受付開始
2. BOX新商品の公式発売日

抽選開始と発売日はDiscordへ通知し、Googleカレンダーへ登録する。抽選終了日時は登録しない。公式ウェブで開始を把握できない店舗は、SNKRDUNK MAGAZINEを明示的な二次情報フォールバックにできる。運用中にOpenAI APIその他の有料AI APIは使わない。

完成条件は次の通り。

- `sites.yaml` で有効な通常監視サイトをGitHub Actionsから定期実行できる
- ポケカとワンピカードを`game_id`で分離し、商品分類・通知名・発売元を設定で切り替えられる
- 新規抽選と新規発売日はDiscordへ1回、Googleカレンダーへ1回だけ登録される
- 同じページでも商品または開始日時が変われば新しい案件として扱う
- 発売日が訂正された時は、同じ商品を重複登録せず既存予定を更新して変更通知する
- スターター、デッキ、セット、単品パック、通常販売などを正常通知しない
- 抽出失敗・構造変更・アクセス拒否を沈黙させず、Discordへ異常通知する
- 二次情報は公式と区別し、公式との不一致、曜日矛盾、根拠不足を異常通知する
- 初回起動時に既存案件を一斉通知しない
- 初回でも未来の公式発売日はカレンダーへ基準登録できる
- テストはネットワークや実Secretsなしで再現できる
- READMEの手順だけで、初心者がSecrets設定・初期化・手動実行・障害確認を行える

## 2. 推奨技術

- Python 3.12
- HTTP: `httpx`
- HTML: `beautifulsoup4` と `lxml`
- YAML: `PyYAML`
- 日時: 標準 `datetime`、`zoneinfo`、サイト固有の正規表現。曖昧な自然言語ライブラリへ丸投げしない
- Google Calendar: `google-api-python-client`、`google-auth`
- ブラウザ補助: `playwright`。ヨドバシでHTTPが空殻の場合だけ使用し、他サイトのWAF/CAPTCHA回避には使わない
- テスト: `pytest`、`pytest-cov`、`respx`、`freezegun`
- 品質: `ruff`、`mypy`
- 状態保存: GitHubの専用 `monitor-state` ブランチ
- 実行: GitHub Actions `schedule` と `workflow_dispatch`

ランタイムで生成AI、外部検索API、スクレイピング代行APIを呼ばない。公式を優先する判断、本文分類、日付抽出、重複統合はすべて決定的なルールで行う。

## 3. リポジトリ構成

```text
.
├── README.md
├── pyproject.toml
├── sites.yaml
├── site-research.md
├── implementation-spec.md
├── source-index.md
├── unresolved-issues.md
├── codex-build-prompt.md
├── START-HERE.md
├── .env.example
├── .gitignore
├── src/tcg_monitor/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── canonical.py
│   ├── http_client.py
│   ├── discovery.py
│   ├── pipeline.py
│   ├── classifier.py
│   ├── source_priority.py
│   ├── release_pipeline.py
│   ├── japanese_datetime.py
│   ├── structure.py
│   ├── state.py
│   ├── health.py
│   ├── logging_config.py
│   ├── discord.py
│   ├── google_calendar.py
│   └── parsers/
│       ├── __init__.py
│       ├── base.py
│       ├── common.py
│       ├── pokemon_official_products.py
│       ├── onepiece_official.py
│       ├── snkrdunk.py
│       ├── geo.py
│       ├── pokemon_center.py
│       ├── rakuten_books.py
│       ├── yodobashi.py
│       ├── kids_republic.py
│       ├── aeon_style.py
│       └── health_only.py
├── tests/
│   ├── fixtures/
│   │   ├── README.md
│   │   ├── pokemon_official/
│   │   ├── onepiece_official/
│   │   ├── snkrdunk/
│   │   ├── geo/
│   │   ├── pokemon_center/
│   │   ├── rakuten_books/
│   │   ├── yodobashi/
│   │   ├── kids_republic/
│   │   └── failures/
│   ├── test_classifier.py
│   ├── test_release_pipeline.py
│   ├── test_source_priority.py
│   ├── test_japanese_datetime.py
│   ├── test_discovery.py
│   ├── test_parsers.py
│   ├── test_structure_alerts.py
│   ├── test_state_and_dedupe.py
│   └── test_delivery.py
└── .github/workflows/
    ├── test.yml
    └── monitor.yml
```

## 4. データモデル

`dataclasses` または型付きモデルで、最低限次を定義する。

### `FetchedPage`

- `source_id`
- `source_tier`: `official | official_indirect | secondary`
- `game_ids`
- `site_id`
- `url`
- `canonical_url`
- `status_code`
- `retrieved_at`
- `title`
- `html`
- `visible_text`
- `etag`
- `last_modified`
- `content_hash`
- `is_challenge_or_login`

### `DiscoveredItem`

- `source_id`
- `source_tier`
- `game_id`
- `site_id`
- `canonical_url`
- `title`
- `published_at`（不明可）
- `first_seen_at`
- `source_discovery_url`

### `ProductCandidate`

- `game_id`: `pokemon_card | one_piece_card`
- `canonical_product_key`（ワンピはOP/EB/PRBコードを優先）
- `product_code`（不明可）
- `raw_name`
- `normalized_name`
- `category`: `expansion_box | enhanced_expansion_box | high_class_box | booster_box | extra_booster_box | premium_booster_box | excluded | ambiguous`
- `pack_count`（不明可）
- `is_restock`
- `evidence`: 判定に使った短い文字列の配列
- `source_block_id`

### `StartCandidate`

- `datetime` または `date`
- `timezone`
- `raw_text`
- `label`
- `method`: `json | structured_data | site_selector | label_range | general_fallback | secondary_heading_block`
- `confidence`: `high | medium | low`
- `year_inferred`
- `weekday_validated`
- `source_block_id`

### `LotteryCase`

- `case_id`
- `game_id`
- `retailer_id`
- `site_id`
- `site_name`
- `source_id`
- `source_tier`
- `source_url`
- `application_url`
- `page_title`
- `products`: BOXだけ
- `start`
- `detected_at`
- `extraction_method`
- `confidence`
- `region_text`（不明可）
- `warnings`

### `ReleaseCase`

- `release_id`: `sha256(game_id | canonical_product_key)`
- `game_id`
- `canonical_product_key`
- `product_code`（不明可）
- `product_name`
- `product_category`
- `release_date`: 正確な日、または`null`
- `announced_month`: 月しかない場合、または`null`
- `source_id`
- `source_tier`
- `source_url`
- `detected_at`
- `extraction_method`
- `confidence`
- `calendar_event_id`（未登録可）
- `previous_release_date`（変更時のみ）
- `warnings`

### `Anomaly`

- `fingerprint`
- `site_id`
- `url`
- `page_title`
- `detected_keywords`
- `reason_code`
- `reason_detail`
- `structure_diff`
- `snippet`
- `detected_at`
- `manual_url`
- `severity`: `warning | error | critical`

## 5. データの流れ

1. `sites.yaml` v2を読み、ゲーム、情報源、URL、優先順位を検証する
2. 情報源ごとの最低アクセス間隔とpoll間隔を守って条件付きGETする
3. 新規リンク、商品カード、または固定ページ／記事内店舗ブロックの意味差分を`DiscoveredItem`にする
4. ログイン、エラー、チャレンジ、空本文への置換を判定する
5. `game_id`ごとの関連語と商品語を判定する
6. 公式商品カタログは発売日パイプラインへ、抽選・応募・受付を含むものは抽選パイプラインへ渡す。1ページが両方に入ってもよい
7. サイト別パーサーで商品ブロック、発売値、抽選開始、販売先、公式リンクを抽出する
8. ゲーム別BOX分類器で対象商品だけを残す
9. サイト別抽出に失敗したらラベル解析、次に一般日時解析へ進む
10. 日時と商品を同じブロック、見出し階層、または明示的なページ全体期間で関連付ける
11. 一意なら`LotteryCase`または`ReleaseCase`を作り、不明なら`Anomaly`を作る
12. 公式・公式間接・二次の順で同一案件を統合し、食い違いは異常にする
13. 状態に配信ジャーナルを記録し、Google Calendarへ冪等登録／更新する
14. Discordへ正常・予定・変更・異常の適切な通知を送る
15. カレンダー説明欄と状態を最終結果へ更新する

どの段階でも関連候補を単純に捨てない。対象ゲーム語、BOX候補語、抽選語、発売日ラベルのいずれかを十分検出したのに次段階へ進めない場合は異常になる。ただし、ワンピカードの開催実績を確認できない特定店舗にページがないこと自体は異常ではない。

### 5.1 抽選の通知時点

- 将来の開始日時を先に発見: Calendarを作成し、Discordへ「抽選予定」を1回通知する
- 現在時刻が開始を越えた最初のrun: Discordへ「抽選開始」を1回通知する。予定通知済みでも開始通知は別ライフサイクルとして送る
- 発見時点ですでに開始済みで受付中: 「抽選開始済み」を即時通知し、Calendarを作る
- 受付終了ページをbaselineで初めて見つけた: 正常通知・Calendar登録なし

予定通知と開始通知は重複ではなく、`notification_kind`を`scheduled | started | started_late | release_announced | release_changed`で分けて状態保存する。

## 6. 発見処理

### 6.1 一覧型

ゲオ、ポケモンセンターオンライン、キッズリパブリックで使う。

- 設定された `discovery_urls` だけを取得する
- `page_url_patterns` に一致するリンクだけを正規化する
- フラグメント、追跡クエリ、末尾スラッシュ差を正規化する
- 初見URLだけ詳細取得する。ただし過去にエラーだったURLはバックオフ期限後に再試行する
- 一覧から既知リンクが大量に消えても即削除せず、構造変更として扱う

### 6.2 固定ページ型

ヨドバシ、楽天ブックスで使う。

- HTML全体ではなく、ナビゲーション・時刻・広告などを除いた本文を正規化する
- `semantic_hash = sha256(title + product blocks + period blocks)` を保存する
- 同じハッシュなら解析を省略できるが、HTTP健康状態は更新する
- 新しい意味ハッシュなら必ず再解析する
- 前回案件が終了表示へ変わっただけなら、新規正常通知はしない。ただし期待要素消失があれば構造警告を出す

### 6.3 商品カタログ型

ポケカ公式商品一覧とONE PIECEカード公式商品一覧で使う。

- 一覧の各商品カードを`game_id | canonical_product_key`で識別する
- 商品名、カテゴリ、発売値、個別リンクを同じカード内で関連付ける
- ポケカは公式商品URLと正規化名、ワンピはOP/EB/PRBコードを優先キーにする
- `2026.10`のような月だけの値も状態へ保存するが、Calendarは作らない
- 後日正確な日に変わった時は同じ`release_id`へ昇格する
- 発売日だけ変わった時は新規イベントではなく既存イベントを更新する
- 商品リンク形式を推測せず、必ず一覧の実リンクを使う

### 6.4 二次まとめ記事型

SNKRDUNKのポケカ／ワンピカード発売スケジュールと商品別まとめ記事で使う。

- 発売スケジュールから新しい「予約・抽選情報まとめ」記事を6時間ごとに発見する
- 商品別記事は発売日＋7日まで、毎日2回の定期実行ごとに意味差分を監視する
- 記事公開後も「現在予約・抽選受付中の店舗」と店舗別見出しが追記される前提にする
- 店舗ブロックは見出し階層で分割し、店舗名、抽選期間、公式詳細リンク、状態を同じブロックから取る
- 同じ記事の広告、相場、買取、当選発表、発売日を開始日時候補から除く
- 二次情報だけの正確な日時は確度`medium`。日付だけ、`-`、招待リクエスト、未定はCalendarへ入れない
- 既知の小売店は設定IDへ正規化し、未知店舗は`unknown_retailer`警告とする
- 公式情報を取得できれば同一案件へ統合し、公式を優先する

### 6.5 健康監視型

ヤマダ、コジマ、イオン直接ページで使う。

- 1時間間隔
- アプリ案内または既知固定ページの期待語・期待要素だけを見る
- 公式ページだけで日時の完全性を確認できない場合は、同じ案件のSNKRDUNK店舗ブロックへフォールバックする
- 新しい対象ゲームの抽選らしい変更は、開始を一意に取れなければ「手動確認」異常通知にする

Amazonは既定で無効。利用者がASINを明示登録して有効化した時だけ健康監視する。

## 7. HTTP・ブラウザ取得

### 7.1 HTTP

- 接続・読み取りを合わせて20秒でタイムアウト
- 5xx、429、一時的ネットワークエラーだけ最大2回再試行
- 403は同じ実行内で連打しない
- `ETag`、`Last-Modified` を保存し、`If-None-Match`、`If-Modified-Since` を使う
- 同一ホストのリクエスト間隔は最低5秒
- 連絡先を含む正直なUser-AgentをREADMEで設定させる
- レスポンスサイズに上限を設ける（例: 5 MiB）
- リダイレクト先のホストを検証し、ログイン・外部広告へ飛んだら異常にする
- HTML以外や空本文を異常候補にする

### 7.2 ブラウザ

- `render_mode: http_then_browser_if_shell` のサイトだけ許可
- HTTP本文に十分な可視テキストがなく、スクリプト殻と判定した場合に1回だけ実行
- CAPTCHA、Cloudflareチェック、人間確認、ログインを操作しない
- Cookieや認証状態を保存しない
- ブラウザ結果もチャレンジなら異常通知して終了

## 8. サイト別パーサー

### ポケカ公式商品情報

- 拡張商品フィルタ一覧と全商品一覧から商品カードを抽出する
- 商品カード内の名称、区分、「販売日」、個別商品リンクを関連付ける
- 拡張、強化拡張、ハイクラス、再拡張だけを発売日対象にする
- 専用要素が消えたら「販売日」ラベル補助解析へ進み、成功しても構造警告を併送する
- 公式ニュースは商品一覧の先行告知・変更検出の補助にし、曖昧な発売表現だけではCalendar登録しない

### ONE PIECEカード公式商品情報・トピックス

- 商品一覧のブースター分類から商品名、OP/EB/PRBコード、発売値、実リンクを抽出する
- ブースターパック、エクストラブースター、プレミアムブースターだけを対象にする
- `.html`、`.php`、末尾ディレクトリのURL形式を許容し、URLを組み立てない
- 日まである発売値は終日Calendar、月だけならDiscord予告のみ
- 個別商品ページとトピックスの「抽選販売」「応募受付期間」を抽選パイプラインへも渡す
- プレミアムバンダイへの公開リンクを`application_url`にする。日付だけなら公式情報として終日開始予定
- 発売日、応募期間、当選、購入期間が同じページにあってもラベルスコープを越えて関連付けない

### SNKRDUNK

- ポケカ用・ワンピ用を同じ汎用パーサーとゲーム別語彙で処理する
- `現在予約・抽選受付中の店舗`以下を店舗見出し単位に分割する。上部表も補助に使うが、詳細ブロックと不一致なら警告する
- 商品名、発売日、店舗名、抽選期間、抽選詳細リンクを抽出し、公式リンクと二次記事URLの両方を保持する
- 年省略は記事更新日と公式発売日を候補にし、曜日があれば必ず検算する
- 記事行の追加・変更・削除を店舗単位の意味ハッシュで検出する
- 再販記事は抽選語と期間ラベルが同じ店舗ブロックにあるものだけ採用する
- Amazonの招待リクエストは開始日時がないため手動確認扱いにし、Calendarへ入れない
- 公式ページが二次記事の主張を確認できない時は`secondary_claim_not_visible_on_official_page`を生成する

### ゲオ

- 一覧から `/news/\d+` を発見
- `h1` と `main` 本文を取得
- 「応募期間」ラベルを含む文・段落から範囲先頭を取る
- 年省略は掲載日年で補い、曜日を検証する
- 商品列挙からゲーム別BOXだけを選ぶ。記事770のような混在を想定する
- ONE PIECEカード関連ページが現れれば共通判定するが、見つからないこと自体は異常にしない

### ポケモンセンターオンライン

- タイトルの `[抽選販売]` と「各種期間」ブロックを確認
- 「抽選応募受け付け期間」の直後だけを開始候補にする
- 商品詳細の `1BOX＝Nパック` とカテゴリ語を同時に確認
- 「ポケモンセンターセット」「スペシャルセット」は除外
- ニュースだけ先に出て日時がない場合は異常通知し、商品ページ出現を待つ

### 楽天ブックス

- 表の各行を見出しセルと値セルの組に正規化
- `抽選受付期間` の値から先頭日時を取る
- `対象商品` のリンク・テキストを商品単位に分割
- `[30パック]` は拡張系、`[10パック]` はハイクラス文脈がある場合だけBOX
- 固定ページの前回意味ハッシュと比較する
- ポケカとワンピカードのゲーム語を行単位で判定する。SNKRDUNKにあるワンピ案件が公式本文で見えない場合は二次情報のままにし、競合警告を出す

### ヨドバシカメラ

- 固定ページから商品名、1BOX表記、申込期間を取得
- 「抽選結果」「注文」「購入」ブロックの日時は候補から除外
- HTTPが殻の場合だけPlaywright
- 固定URLでも `case_id` は開始日時と商品で変わる
- 検索キャッシュは本番データ源にしない
- ワンピカード語が出れば同じラベル処理へ渡すが、ポケカ専用の期待語をワンピ案件に強制しない

### キッズリパブリック

- `■対象商品`、`■応募受付期間` などの見出しでブロック化
- 「キッズリパブリックアプリ」と「イオンスタイルオンライン」を別チャネルとして扱う
- パック数と商品分類を同じチャネルブロックで対応させる
- 年省略は掲載日で補い、曜日を検証
- 地域文を抽出し、東北が含まれるか否かを説明欄へ残す。曖昧でも日時が確実なら正常通知に警告を付け、明確に対象外なら除外設定を可能にする
- 403・チャレンジは回避せず健康異常

### イオンスタイルオンライン

- キッズリパブリック公式記事内の「イオンスタイルオンライン」ブロックだけが正常抽出元
- 直接 `k-lottery.aspx` は健康確認のみ
- 直接ページを取得できても、サイト別パーサーを有効化するには保存fixtureとレビューを必要とする

### ヤマダ・コジマ

- `health_only.py` で期待語と構造だけ監視
- 公式本文から一意に取れなければ、同じゲーム・商品・店舗のSNKRDUNK店舗ブロックを探す
- 二次情報に日付と時刻が揃い、曜日検証に通れば確度`medium`で通知・Calendar登録を許可する
- 後から公式確認できたら同じ`case_id`を公式へ昇格し、重複登録しない
- コジマのワンピは実績未確認なので、SNKRDUNKに店舗行が出た時だけ候補化する

### Amazon

- 既定無効
- 手動ASINだけを対象に、商品名、招待表示、販売元を確認
- 変化は手動確認警告だけ。Calendar登録禁止

### 麦わらストア

- 初期設定は無効
- 応募開始ラベルを含む複数fixtureが揃うまで、`商品販売期間`を抽選開始として採用しない
- 有効化前に正常、終了、当選、発売日の負例テストを追加する

## 9. 日時解析

### 9.1 正規化

- 全角数字、全角コロン、ノーブレークスペースを正規化
- `午前12時` は00時、`午後12時` と `正午` は12時
- `昼12時` は12時。それ以外の「昼」は曖昧として警告
- 分省略の `10時` は10:00としてよいが、元表記と解析方法を保存する
- すべて `Asia/Tokyo` のaware datetimeにする

### 9.2 年省略

- 公式掲載日がある場合だけ、その年を第一候補にする
- 12月掲載・1月開始などは前後1年を候補にし、掲載日または公式発売日から妥当な範囲かつ曜日一致だけを採用
- 曜日が書かれている場合は必ず検証
- 候補が複数なら異常。現在年を無条件に入れない

### 9.3 妥当性

- 公式掲載日または初回発見より著しく古い開始は警告
- 抽選開始が発見時点から365日超の未来は警告。公式発売日は商品カタログに基づく限り365日超でも即除外せず、予告値として警告付き保存
- 開始ラベルに一致する候補が複数あり、一方を構造で選べない場合は異常
- 終了日時、当選日時、購入期限を開始にしない

### 9.4 日付だけ

- 公式／公式間接で年月日が明確: 終日イベント
- 二次情報だけで日付はあるが時刻なし: 手動確認警告、Calendarなし
- 発売日の年月だけ、`○月予定`: Discord予告、Calendarなし
- 抽選日の年月だけ、`後日`: Discord異常のみ
- 時刻を過去事例から補わない

## 10. BOX分類

ルールベースで、`game_id`と商品ブロックごとにスコアと証拠を返す。

共通:

1. ゲーム別除外語が販売商品名にあれば原則`excluded`
2. `1BOX＝Nパック`または同等のBOX構成は正の証拠
3. 特別セットに「BOX×2」が含まれても、販売SKUがセットなら除外
4. 再販・再入荷・再抽選は抽選監視では除外理由にしない
5. ページに抽選語がなければ抽選候補にはしない。ただし公式商品カタログなら発売日候補にはできる
6. 正負の根拠が競合したら`ambiguous`として異常通知

ポケカ:

- `BOX`と拡張・強化拡張・ハイクラス・再拡張のカテゴリ語があれば採用
- 拡張系＋30パック、ハイクラス＋10パックは採用
- `10パック`だけでは採用しない
- スターターセット、デッキ、スペシャルセット、ポケモンセンターセットは除外

ワンピカード:

- ブースターパック、エクストラブースター、プレミアムブースターとBOX証拠を要求する
- OP/EB/PRBコードを商品識別の強い証拠にするが、コードだけではBOX判定しない
- スタートデッキ、アルティメットデッキ、カードコレクション、セット、サプライを除外

分類結果と証拠はログ・通知・fixture期待値に残す。

## 11. 重複防止と状態保存

### 11.1 一意識別子

次をUTF-8で連結しSHA-256にする。

```text
game_id | retailer_id | canonical_product_key | normalized_start
```

`case_id` は完全な16進SHA-256。固定URLでも開始日時または商品が変われば別案件になる。情報源URLはIDに入れないため、SNKRDUNKで先に見つけた案件を後から公式情報へ昇格できる。追跡クエリやフラグメントはURLから除くが、意味を持つ商品IDやニュースIDは残す。

発売日は次で`release_id`を作る。

```text
game_id | canonical_product_key
```

`canonical_product_key`はワンピカードではOP/EB/PRBコードを最優先し、ポケカでは公式商品URLの安定ID部分、なければ厳格に正規化した公式商品名を使う。同じ`release_id`の発売日が変わったら既存Calendarイベントを更新し、`release_changed`を1回通知する。

同一抽選・発売日に複数情報源がある時は`official > official_indirect > secondary`で主情報を選ぶ。別情報源を`corroborating_sources`に残す。商品名の表記差はゲームコード、公式URL、厳格な別名表でのみ統合し、曖昧な類似度だけで別商品を統合しない。

異常通知は次で `fingerprint` を作る。

```text
site_id | canonical_url | reason_code | relevant_content_hash
```

同一異常は初回と未解決24時間後だけ通知する。解消時には回復通知を1回送る。

### 11.2 状態ブランチ

Actions cacheやartifactを唯一の状態にしない。消える可能性があるため、`monitor-state` ブランチへ次を保存する。

```text
state/
├── state.json
└── snapshots/
    └── <site_id>/<semantic_hash>.json.gz
```

`state.json` の主な項目:

- スキーマバージョン
- 既知URL、初回・最終確認時刻
- ETag、Last-Modified、本文・意味ハッシュ
- サイト別連続エラー回数と直近成功時刻
- 前回の期待要素・構造指紋
- `case_id` ごとの `pending | calendar_created | complete | failed`
- `release_id`ごとの発売値、Calendar event ID、変更履歴
- `notification_kind`ごとの送信済み状態
- 主情報源、補助情報源、情報源の格付け、公式へ昇格した時刻
- Calendar event ID
- Discord message ID
- 異常fingerprint、初回・最終通知・解消時刻

workflowは `concurrency` を使い、同時実行を許さない。状態ブランチの更新競合時はfetchして1回だけ再マージし、解決できなければ異常ログを残して失敗終了する。

### 11.3 初回基準化

初回は `python -m tcg_monitor.cli baseline` を実行する。

- 現在見えるページと案件を既知として保存
- Discord正常通知とCalendar登録はしない
- ただし未来の公式新弾発売日は、`--include-future-releases`を明示したbaselineでCalendarへ登録できる。過去発売日は登録しない
- アクセスエラー、ログイン置換、構造不明はコンソールへ出し、任意でDiscord異常通知できる
- 完了後に `armed: true` を状態へ保存
- `armed` でない通常runは通知せず失敗終了する

これにより、初回だけ過去案件が花火のように大量通知される事故を防ぐ。

## 12. Discord通知

WebhookへJSONをPOSTし、`?wait=true` でmessage IDを取得する。本文はDiscordの長さ制限を超えないよう切り詰め、詳細はログと公式URLへ誘導する。SecretsやHTML全文を送らない。

### 12.1 正常通知

Embedに最低限次を含める。

- ゲーム名
- 店舗・サービス名
- 商品名（BOX対象だけ。複数可）
- 商品分類
- 抽選開始日時（JST、元表記も説明に残す）
- 検出日時
- 公式応募ページURL
- 情報掲載ページURLが別なら両方
- 抽出方法
- 抽出確度
- 情報源区分（公式／公式間接／二次情報）
- 地域条件
- Googleカレンダー登録結果とevent ID
- `case_id` の先頭12文字

色は正常を緑、確度mediumまたは付随警告ありを黄にする。

抽選通知の件名:

```text
【ポケカ抽選予定】<店舗>／<商品>
【ポケカ抽選開始】<店舗>／<商品>
【ワンピカード抽選予定】<店舗>／<商品>
【ワンピカード抽選開始】<店舗>／<商品>
```

発売日通知の件名:

```text
【ポケカ新弾発売日】<商品>
【ワンピカード新弾発売日】<商品>
【発売日変更】<ゲーム>／<商品>：<旧日> → <新日>
```

発売日通知には商品名、分類、発売日または発売月、検出日時、公式商品URL、抽出方法、確度、Calendar結果、`release_id`を含める。月だけの場合は「日付未確定・Calendar未登録」と明記する。

### 12.2 異常通知

- 店舗・サービス名
- 対象URL
- ページタイトル
- 検出した関連語
- 解析できなかった理由コードと説明
- 前回構造との変更点
- HTTP状態・連続失敗回数
- 手動確認用URL
- 情報源区分と、公式・二次情報の競合内容
- 異常fingerprintの先頭12文字

構造差分はタグ名やラベルの追加・消失を要約し、ページ本文を丸ごと送らない。criticalはログイン画面・CAPTCHA置換、連続403/5xx、状態保存失敗など。

## 13. Googleカレンダー

### 13.1 認証

専用Google Calendarを作り、サービスアカウントのメールアドレスへ「予定の変更」権限を付ける。個人のメインカレンダー全体は共有しない。

Secrets:

- `GOOGLE_SERVICE_ACCOUNT_JSON`: サービスアカウントJSON全文。ログに出さない
- `GOOGLE_CALENDAR_ID`: 専用カレンダーID

JSONを一度Pythonで構文検証し、秘密鍵やメールアドレスをログへ出さない。Apps Scriptは既定実装に含めない。

### 13.2 イベント

件名:

```text
【ポケカ抽選開始】<店舗名>／<商品名>
【ワンピカード抽選開始】<店舗名>／<商品名>
【ポケカ発売】<商品名>
【ワンピカード発売】<商品名>
```

複数BOXなら最初の商品名＋`ほかN件`。説明欄:

- 公式応募ページURL
- 情報掲載ページURL
- 商品分類
- 検出日時
- 抽出方法
- 抽出確度
- 情報源区分と主情報源URL
- 地域条件
- Discord通知状態
- `case_id`
- 「表示上の終了は開始＋15分であり、抽選受付終了日時ではありません」

抽選は時刻ありなら開始から15分。公式情報で日付だけなら終日。二次情報で時刻なしは登録しない。発売日は正確な年月日があれば終日で、月だけなら登録しない。抽選終了日時はどの場合も登録しない。

Calendarの`extendedProperties.private`へ`case_id`または`release_id`、`game_id`、`source_tier`を保存する。Calendar event IDには内部IDからAPI仕様に適合する決定的な英数字IDを作り、同じイベントをinsertすると409になる性質も重複防止に使う。発売日変更はevent IDを保ったまま`events.update`し、説明に旧日と変更検出日を追記する。

### 13.3 配信順序と障害

DiscordとCalendarを完全な分散トランザクションにはできない。次のジャーナル方式で通常の重複を防ぐ。

1. 状態に `pending` を記録
2. Calendarを決定的IDでinsert。既存409は成功扱い
3. 状態を `calendar_created` に更新
4. Discordを `wait=true` で送信
5. Calendar説明を「Discord通知済み」に更新
6. 状態を `complete` に更新

Discord送信の応答を受け取る前にプロセスが落ちると、送信済みかをWebhookだけで照会できない。`pending` が30分以上残った場合は正常通知を無条件再送せず、「配信状態不明」の異常通知または手動確認ログにする。この限界をREADMEに明記する。

## 14. GitHub Actions

### `test.yml`

- pull request、mainへのpush、手動実行
- Python 3.12
- 依存キャッシュ
- `ruff check .`
- `mypy src`
- `pytest --cov --cov-fail-under=85`
- 実サイトへアクセスしない

### `monitor.yml`

- `schedule`: 毎日05:00と17:00（日本時間）の2回。GitHub cronはUTCのため `0 8,20 * * *`
- `workflow_dispatch`: `baseline`、`dry_run`、`site_id` 入力
- `permissions`: `contents: write`（状態ブランチのみ）、その他は最小
- `concurrency`: `tcg-monitor-state`、`cancel-in-progress: false`
- mainと`monitor-state`をcheckout
- Python依存をインストール
- Playwrightはブラウザフォールバックを使う実行だけインストールするか、専用extraに分離
- 正常終了・異常終了にかかわらず状態変更をcommit/push
- Secretsが足りない通常runは明示エラー。dry-runは通知なしで動ける
- GitHubのログ保持だけに頼らず、構造化JSONログをActions artifactとして短期間保存してもよい。ただし秘密情報・HTML全文は含めない

Actionsは毎日05:00と17:00（日本時間）の2回だけ実行する。各実行では有効な監視先を最大1回確認し、同一実行内のホスト間隔と条件付きGETを守る。GitHub Actionsの混雑による開始遅延は許容し、秒単位の即時性は保証しない。

## 15. GitHub Secretsと環境変数

必須Secrets:

- `DISCORD_WEBHOOK_URL`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_CALENDAR_ID`

通常のVariablesまたは設定:

- `MONITOR_USER_AGENT_CONTACT`: リポジトリURLまたは連絡先
- `MONITOR_LOG_LEVEL`: 既定 `INFO`
- `MONITOR_DRY_RUN`: 既定 `false`

`.env.example` はキー名だけを含め、値はダミーにする。`.env`、サービスアカウントJSON、stateのローカルコピー、Playwright保存状態を`.gitignore`へ入れる。例外やHTTPヘッダーをそのままログに出さず、Webhook URL、Authorization、Cookieをマスクする。

## 16. ログとエラー処理

1行1JSONの構造化ログとし、次を含める。

- timestamp、level、run_id、site_id、phase
- url（秘密クエリは除去）
- status_code、elapsed_ms
- item/case/anomaly ID
- extraction_method、confidence
- outcome、reason_code

ログレベル:

- INFO: 304、変更なし、正常抽出、重複スキップ
- WARNING: フォールバック成功、期待要素欠落、日付補完
- ERROR: 解析失敗、HTTP連続失敗、通知失敗
- CRITICAL: 状態破損、ログイン/CAPTCHA置換、状態保存競合未解決

サイト1件の失敗で他サイトを止めない。ただし状態読込失敗、設定不正、Secrets漏洩のおそれは全体停止する。終了コードは「正常」「一部サイト異常」「全体失敗」を区別する。

## 17. 構造変更検出

サイトごとに期待要素を名前付きで保存する。前回との差を次で判定する。

- 要素の存在・件数
- ラベル文字列の存在
- JSONキーの存在
- タイトル、商品、期間ブロックを正規化したtoken setのJaccard類似度
- 可視本文長の急減（例: 前回の30%未満）

類似度0.55未満は警告候補。ただし固定ページが新案件へ全面更新されること自体は正常なので、商品・開始日時を高確度で取れた場合は「正常通知＋構造変更警告」とする。期待要素が消えて共通フォールバックが成功した場合も警告を消さない。

追加の専用異常:

- `new_box_product_without_exact_release_date`: 新BOXだが発売日を取れない
- `release_date_changed`: 公式発売日の変更。異常ではなく変更通知だが履歴へ保存
- `secondary_official_conflict`: 公式と二次情報の日時・商品・販売先が矛盾
- `secondary_claim_not_visible_on_official_page`: 二次記事の店舗行を公式ページで確認できない
- `weekday_date_mismatch`: 数値日付と曜日が不一致
- `unknown_retailer`: 二次記事に未設定の店舗が追加
- `retailer_lottery_block_without_start`: 関連する店舗ブロックに抽選語はあるが開始を取れない
- `product_code_name_conflict`: 同じOP/EB/PRBコードに異なる商品名

SNKRDUNKの記事テンプレートが変わり、上部表または店舗見出しが消えた場合、一般補助解析で値を取れても構造警告を併送する。公式監視系は独立して続行する。

ログイン・エラー置換の代表語:

- ログインしてください、サインイン、認証が必要
- Access Denied、Forbidden、Sorry, you have been blocked
- CAPTCHA、私はロボットではありません
- ただいまサイトへ接続しています
- Service Unavailable、メンテナンス中

## 18. テスト方針

### 18.1 fixture

公式ページの全文を無制限に保存せず、解析に必要なタイトル・ラベル・商品・期間・リンクを含む最小HTML fixtureを作る。各fixtureのREADMEまたはmetadata JSONに、公式URL、取得日、元本文ハッシュ、期待結果を記録する。

最低限の回帰fixture:

- ポケカ公式商品一覧: 発売日3件、スターター除外、販売日ラベル消失、発売日変更
- ONE PIECEカード公式商品一覧: OP-16、OP-15、OP-14、OP-13、EB-05月のみ、デッキ除外、URL形式3種
- ONE PIECEカード公式抽選: OP-16応募受付期間、OP-13再抽選、発売日・応募・当選日時混在
- SNKRDUNKポケカ: 32581型の店舗追加、30468、29945、曜日矛盾、公式リンク欠落
- SNKRDUNKワンピ: 32599の楽天／カードボックス／Amazon招待、店舗ブロック追加、再販記事の通常入荷除外
- ゲオ: 記事770（BOX＋スターター混在）、771（デッキのみ）
- ポケモンセンター: ロケット団の栄光、テラスタルフェスex、メガブレイブBOX、メガブレイブのセンターセット除外
- 楽天ブックス: BOX3種＋デッキ＋スペシャルセット混在、全角コロン
- ヨドバシ: 2026-07-13案件、申込・結果・注文日時混在
- キッズ: BOX、5パック除外、アプリとウェブの開始日時が別、年省略
- 失敗: 表消失、ラベル変更、空ページ、403、ログイン画面、Cloudflare、日時複数、曜日不一致

### 18.2 単体テスト

- 日本語日時: 年あり/なし、曜日、午前午後、正午、分省略、全角記号、年またぎ
- BOX分類: 各正例・除外例・競合例・再販
- URL正規化とcase_idの決定性
- `release_id`の決定性、発売日変更時の同一event更新
- 情報源優先順位、二次から公式への昇格、公式・二次競合
- ポケカとワンピカードで同名風の商品を誤統合しないこと
- ONE PIECEのOP/EB/PRBコード抽出、月だけの発売値
- 状態スキーマ移行、破損検知、異常の24時間抑制
- Calendar event ID、409再実行
- Discord payloadの必須項目と秘密マスク

### 18.3 構造変更テスト

- サイト固有要素を削除し、共通解析が成功しても警告が出る
- ラベルを未知語へ変更し、いずれかの対象ゲーム語・抽選語が残る場合は解析失敗警告が出る
- SNKRDUNKの店舗見出しを削除しても候補を沈黙させず構造警告を出す
- 二次記事に未知店舗を追加し、`unknown_retailer`を出してCalendar登録しない
- 公式商品カードから発売日要素を削除し、商品発見＋発売日解析失敗警告を出す
- 本文をログイン画面へ置換し、正常候補を生成しない
- HTTPエラー1回では記録だけ、2回連続で通知
- 開始日時を当選日時だけに置換し、誤登録しない

### 18.4 結合テスト

HTTP、Calendar、Discordをモックし、次を確認する。

- 新規案件のCalendar→Discord→complete
- 将来抽選の予定通知→開始時刻通過後の開始通知（各1回）
- 公式新弾の終日Calendar→発売日変更で同じevent更新
- 月だけの発売予告はDiscordのみ、日確定後にCalendar作成
- 二次抽選を登録後、公式確認で重複せずsource tierだけ昇格
- 2回目実行で両方スキップ
- Calendar成功・Discord失敗からの保留処理
- 状態push競合の1回再試行
- 複数サイトのうち1サイト失敗でも残りを処理

## 19. 運用手順

READMEには画面操作を含む次の手順を書く。

1. GitHubで非公開リポジトリを作成
2. DiscordサーバーでWebhookを作成しSecretへ保存
3. Google CloudでCalendar APIを有効化
4. サービスアカウントを作成しJSONを取得
5. Google Calendarで専用カレンダーを作成
6. サービスアカウントへ専用カレンダーの予定変更権限を共有
7. 3つのGitHub SecretsとUser-Agent連絡先を設定
8. `test` workflowを実行
9. `monitor`を`baseline=true`で手動実行し、既存抽選を既知化する。未来の公式発売日は`include_future_releases=true`で登録する
10. `dry_run=true` で候補・異常を確認
11. 状態をarmし、scheduleを有効化
12. 最初の1週間はDiscord異常通知とActions実行結果を毎日確認

障害時:

- 403/チャレンジ: 間隔を短くせず、URLを手動で開き、サイト側制限なら当該サイトを一時無効化
- 構造変更: Actions artifact/状態スナップショットと公式ページを比較し、fixture→parser→expected_elementsの順で更新
- 重複: `case_id`、Calendar extended property、stateを確認。手動でstateだけ削除しない
- 通知なし: Actions schedule遅延、armed状態、Secrets、Discord webhook、サイト健康状態を順に確認

## 20. サイト追加手順

1. 公式運営者、一覧、個別ページ、規約、robots、ログイン要否を調査
2. 過去または現行の公式ページを最低2件、なければ不足を明記
3. BOX正例と除外例を最小fixture化
4. `sites.yaml` に発見URL、URLパターン、期待要素、日時ラベル、制約を追加
5. 共通パーサーで足りるか確認し、必要な場合だけサイト別パーサーを追加
6. 正常、日時なし、構造変更、ログイン置換、重複のテストを追加
7. dry-runを最低3回行い、既存案件をbaseline化
8. 初めは `health_only`、問題がなければ `normal` に昇格

新しいゲームを追加する場合は、`games`へゲーム語、BOX種別、除外語、商品コード規則、通知接頭辞、公式発売元を追加する。既存の小売店をそのゲームで`verified`にするのは公式fixtureが得られた時だけとし、実績不明なら`discovery_only_unverified`にする。

二次情報源を追加する場合は、公式とは別の`source_tier`、利用条件、取得間隔、公式リンク抽出、競合テストを必須にする。二次情報を使っている事実を通知から隠さない。

ログイン必須、アプリ限定、WAF回避が必要なサイトは、無理に通常監視へ昇格しない。

## 21. 受入テスト

- 公式fixtureのBOX正例が正しいJST開始日時になる
- ポケカ／ワンピカード公式新弾が正しい終日発売予定になる
- 月だけの発売値はCalendarへ入らず、日確定後に同じrelease_idへ昇格する
- デッキ、セット、5パック、通常販売がCalendarに入らない
- 開始と当選の日時が同居しても開始だけを選ぶ
- 日時解析不能時にDiscord異常payloadが生成される
- 期待要素削除時に、フォールバック成功でも構造警告が生成される
- 2回連続HTTPエラーで異常、回復後に回復通知が生成される
- 同じ入力を3回処理してもCalendar/Discord正常送信は1回
- 予定通知と開始通知は各1回、同じ種類は再送されない
- 二次情報から公式へ昇格してもCalendarが増えず、説明と確度が更新される
- 公式と二次情報の日時が違う時は異常となり、無言でどちらかを選ばない
- date-onlyは終日、曖昧日はCalendarなし
- Secretsがログ・例外・fixtureに出ない
- `pytest`、`ruff`、`mypy` が成功し、カバレッジ85%以上
