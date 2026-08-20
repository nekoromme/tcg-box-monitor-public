# TCG BOX抽選・発売日モニター

ポケモンカードゲーム、ONE PIECEカードゲーム、ドラゴンボールスーパーカードゲーム フュージョンワールド、遊戯王OCG、ディズニー・ロルカナのBOX抽選受付開始と新弾BOX発売日を公開ページから監視し、DiscordとGoogle Calendarへ重複なく通知するPython 3.12製ツールです。

## 🎴 作品ごとの監視切り替え

リポジトリ直下の **`GAME_MONITOR_MODES.txt`** で、5作品を個別にON/OFFできます。

1. GitHubで`GAME_MONITOR_MODES.txt`を開きます。
2. 鉛筆アイコンの編集を押します。
3. 対象作品の右側を`ON`または`OFF`にして保存します。

```text
pokemon_card=ON
one_piece_card=ON
dragon_ball_fusion_world=ON
yu_gi_oh=ON
lorcana=ON
```

OFFの作品しか扱わない監視先は、通知後ではなく通信前に除外します。行の削除、未知の作品ID、重複、`ON`/`OFF`以外の値は設定エラーとして停止するため、タイプミスで意図しない作品が動くことはありません。再びONにした初回は、その時点ですでに見えている抽選を既知扱いにして一斉通知を防ぎ、その後に見つかった新規抽選から通知します。未来の公式発売日は通常どおり取得します。

遊戯王は「コンセプトパック」全体を雑に捨てず、現行・近年BOXの買取相場が低めになりやすい`デッキビルドパック`、`WORLD PREMIERE PACK`、`ANIMATION CHRONICLE`、`デュエリストパック`、`TERMINAL WORLD`、`COLLECTION PACK`をシリーズ名で除外します。基本パック、限定パック、スペシャル系、`REVOLUTION BOOSTER`などは対象に残します。構築済みデッキ、ラッシュデュエル、周辺商品も対象外です。

## 🚗 東北遠征モードの切り替え

リポジトリ直下の **`TOHOKU_EXPEDITION_MODE.txt`** が、盛岡・仙台方面の遠征監視をまとめて切り替えるスイッチです。

1. GitHubで`TOHOKU_EXPEDITION_MODE.txt`を開きます。
2. 鉛筆アイコンの編集を押します。
3. ファイル末尾の`OFF`を`ON`へ変更して保存します。
4. 遠征監視を止める時は`ON`を`OFF`へ戻します。

`OFF`が初期値です。OFF中は遠征用監視先を通信前に除外するため、ページ取得・画像OCR・状態保存を一切行わず、通常実行時間を増やしません。切り替えファイルの変更は`monitor` workflowを自動起動します。Actionsの実行結果上部にも現在のON/OFFが表示されます。

TCバトロコ盛岡大通は常時監視へ移したため、遠征モードの対象外です。ONで追加されるのは、現在確認できる範囲で「拠点からWeb応募でき、当選後の店頭訪問が購入・受取の1回だけ」で済む次の7監視先です。

| 方面 | 監視先 | 応募上の注意 |
|---|---|---|
| 仙台 | TCバトロコ仙台駅東口 | 事前にバトロコ会員カード番号が必要 |
| 仙台 | トレーディングカードピット仙台駅東口店 | Web購入権抽選 |
| 仙台 | santy仙台クリスロード店 | X・Instagram等のSNS応募 |
| 仙台 | TSUTAYAヤマト屋書店東仙台店 | LivePocket応募 |
| 仙台 | TSUTAYA BOOKSTORE仙台長命ヶ丘 | LivePocket応募 |
| 仙台方面 | 駿河屋イオンモール新利府南館店 | X応募 |
| 仙台 | おもちゃの王様 | 公式SNSから応募 |

カードラボ仙台店は、当選後の店頭予約・全額前金と、発売後の引き取りで通常2回来店が必要なため対象外です。ホビーゾーン盛岡南店も店頭QR応募と当選後の受取で2回来店になるため対象外です。方式が弾ごとに変わるTSUTAYA仙台南店・TSUTAYA岩沼店・BOOKOFF PLUS仙台南バイパス店も、安全側に倒して登録していません。

設定検証では、遠征グループの各監視先が`Web応募`かつ`必要来店回数1回`として明示されていなければエラーにします。後からうっかり二度来店の店を混ぜる事故も防ぎます。

## できること

- `sites.yaml` schema_version 2を型付き検証します。
- `GAME_MONITOR_MODES.txt`で作品別に監視をON/OFFし、OFF作品の専用監視先は取得前に除外します。
- 遊戯王OCG公式の商品区分とタカラトミーのロルカナ公式商品ページから、対象BOXの発売日を取得します。
- 公式情報を優先し、SNKRDUNKは二次情報として扱います。
- BOX商品だけを抽出し、スターター、デッキ、セット、周辺用品、一般小売店の通常販売、当選発表などを除外します。メーカー公式通販だけは、期間が明記された受注販売と、タカラトミーモールで実際に購入可能になった未開封BOXを「公式販売」として抽選とは別表示します。
- ホビーステーション、TSUTAYAあけぼの店、フルコンプはLivePocket個別ページの応募期間を監視します（検索結果の開催日は使いません）。フルコンプは公式Xも併用します。
- MINT仙台店、TSUTAYA一関店・一関中央店、Vidaway佐沼店、トレカノ奥州水沢店に加え、TSUTAYA中里店、トレカプラザ55通販店、シーガル仙台駅前店、晴れる屋2、ふるいち、萬屋紫波店・盛岡店、ザ・グレートヨロズヤ盛岡高松店、万代古川店、HMV、トレカ道楽仙台駅前店、フルコンプ仙台駅前店は、Yahooリアルタイム検索を通常経路とし、取得・HTML確認・解析の失敗時だけ公開Xプロフィールミラーへフォールバックします。ふるいちはこれに加えて公式お知らせ一覧を直接監視し、個別記事の公式画像から応募開始・締切をOCRします。
- ホビーリンク・ジャパン、セブンネット、ノジマオンライン、ドラゴンスター通販、DMM通販、DMMマイカ、エディオン、ファミリーマートは各社公式Xも監視します。シーガルは既存の仙台駅前店公式Xを全店共通抽選の入口として重複なく使います。
- ホビーサーチはポケモンカード商品一覧から「抽選販売」中のBOXだけを個別ページまで追います。GitHub実行環境から403になる場合は、店舗名と受付開始を明記したポケゲトの投稿を中確度の独立経路として使います。
- ヤマダデンキとコジマは公式アプリ内だけに出る告知を補うため、店舗名を含む特定の二次情報投稿も監視します。日時が明示された抽選だけを中確度で登録し、延期・中止・日程変更は抽選開始として登録せず異常通知します。
- ONE PIECEカードゲーム公式ショップは、バンダイナムコの全国向け公式記事を先に確認し、ナムコパークスの仙台店・宮城名取店購入権と同一案件として統合します。ファミマオンライン、DMM通販、エディオンネットショップ、イトーヨーカドーネット通販は公式一覧からBOX抽選の個別ページまで追って応募開始日時を取得します。DMM通販がログイン画面を返す場合は、公式X、DMM通販名を明記したワンピース入荷情報X、入荷NowのDMM通販欄の3経路で復旧し、入荷NowではDMM用ページを最初に取得します。
- Tokyo Otaku Modeは公式お知らせから個別抽選記事を追い、ポケカ・ワンピカード・ドラゴンのBOXを分類します。受付期間が終了日時しか示さない記事では終了日時を開始日と誤認せず、「抽選応募を開始」と明記された記事の掲載日を開始日として扱います。
- ポケモンセンターはオンラインと実店舗公式お知らせを別々に監視し、明示された応募期間だけを開始日として登録します。当選結果発表日は登録しません。
- ゲオ、ヨドバシ、ポケモンセンター各店は、公式ページが取得制限された場合に備えて各社公式XのYahooリアルタイム検索も独立監視します。
- 受付開始日は本文を優先し、不足時だけ添付画像を無料OCRします。画像取得やOCRが失敗しても、公式商品カタログの商品名と一致すればゲームを補完して初回検知日で通知します。X添付画像とふるいち公式記事画像のOCR結果は状態ファイルへ保存し、同じ画像を毎回読み直しません。判定不能な投稿は保留し、同じ投稿でOCR失敗が繰り返された時だけ異常通知します。
- プレミアムバンダイのワンピBOX抽選は公式Xと入荷Nowのプレバン欄を併用し、OP/EB/PRBの過去弾再抽選も拾います。
- 遊戯王はKONAMI STYLEのBOX抽選と期間付き受注販売、ロルカナはタカラトミーモールの「BOX販売」・DP-BOX、ドラゴンボールはプレミアムバンダイの通常ブースターBOX抽選を監視します。遊戯王サテライトショップは対象外です。メーカー共通キャンペーン日、カートン、単品パック、周年セット、構築済みデッキ、サプライは通知しません。
- 抽選IDはゲーム・店舗・商品・公式URL（Xは投稿ID）から決定し、開始日時の訂正では変わりません。Amazon招待はASIN、ふるいち抽選は公式記事URLを優先して、複数の発見経路を同じ案件へ統合します。旧IDは次回検出時に移行し、既存のCalendar予定を更新します。
- `render_mode`は全監視先で共通処理され、HTTP本文が空またはJavaScriptシェルの場合だけ設定に従ってPlaywrightへ切り替えます。Cloudflare、CAPTCHA、ログイン画面の迂回は行いません。
- 監視先ごとに取得・解析・状態保存を分離します。同一ホストで403、429、Cloudflare、CAPTCHA、ログイン画面が2回続くと、その実行中は同ホストの残りを遮断します。
- HTTP接続は1回最大20秒、最大3回、1 URL合計最大60秒で打ち切ります。別ホストの先頭ページは最大6系統まで先読みし、ある接続を待つ間も他サイトの取得を進めます。同一ホストとPlaywrightは直列のままにし、遮断器の順序とGitHub Actionsのメモリを守ります。
- 取得先が複数ある監視は先頭から順にフォールバックし、最後まで失敗した時だけ監視異常にします。
- ETag／Last-Modifiedによる条件付きGET、Google Calendar接続再利用、未変更予定の更新省略に対応します。
- 公式投稿を検出したのにゲーム・BOX・開始日を解析できない場合や、取得先で障害が起きた場合は、監視異常通知をDiscordへ送ります。同じ取得先・理由・確認URLの異常は継続中に再通知せず、2回連続で見えなくなった後に再発した場合だけ新しい異常として通知します。単一監視先だけの手動実行では、実行していない監視先を解消済みにしません。
- 状態ファイルには監視先ごとの最終成功・取得時刻、連続失敗、HTTP状態、取得方法、処理時間、ページ・解析・除外件数を原子的に保存し、Actionsの実行サマリーへ表で表示します。
- Secretsなしでも`dry-run`とfixtureデモを実行できます。
- CAPTCHA、Cloudflare、人間確認、ログインは突破しません。異常として扱います。

`supported_games`は`verified`、`prospective`、`discovery_only`、`unsupported`の4状態だけを受け付けます。前2つだけが通常解析対象で、`discovery_only`は取得・発見用途、`unsupported`は明示的な対象外です。未知の値やゲームIDは`validate-config`でエラーになります。

### 開始日が曖昧な公式X発信元を追加する

通常の`lottery_start_policy`は`auto`です。本文の受付期間を優先し、不足時だけ画像OCRを使います。発売日・締切・当選発表日・購入期限を同じ画像へ載せ、開始日だけを安定して判別できない発信元には、監視先の設定へ次の1行を追加します。

```yaml
lottery_start_policy: first_detection_next_day
```

この設定では画像内の日付を開始日に使わず、最初に検知した日の翌日を予定日として固定します。以後の実行で投稿が再検出されても、最初のDiscord配信時刻から同じ日付を復元します。既存予定は同じイベントIDのまま訂正し、配信済み通知は再送しません。値のタイプミスや未対応値は`validate-config`で停止します。

このポリシーは「本当に開始日を判定できない発信元」だけに指定してください。明示された開始時刻まで捨てるため、普通の発信元へ雑に設定すると情報精度が落ちます。

## GitHubで最初に設定するSecrets

`Settings` → `Secrets and variables` → `Actions`で登録します。値をREADMEやチャットへ貼らないでください。

| 種類 | 名前 | 内容 |
|---|---|---|
| Secret | `DISCORD_WEBHOOK_URL` | DiscordチャンネルのWebhook URL |
| Secret | `GOOGLE_SERVICE_ACCOUNT_JSON` | Google CloudサービスアカウントJSON全文 |
| Secret | `GOOGLE_CALENDAR_ID` | 監視専用Google Calendar ID |
| Secret | `STATE_REPO_TOKEN` | 非公開の`nekopone/tcg-box-monitor`だけにContents読み書きを許可したfine-grained token |

監視状態は公開リポジトリへ保存せず、非公開リポジトリの`monitor-state`ブランチを引き続き使います。`STATE_REPO_TOKEN`は対象リポジトリを`nekopone/tcg-box-monitor`だけに限定し、権限はContentsのRead and writeだけにしてください。トークン値をREADME、Issue、Actionsログ、チャットへ貼らないでください。

Google Calendarは専用カレンダーを作り、サービスアカウントのメールアドレスへ「予定の変更」権限で共有してください。個人カレンダー全体は共有しないでください。

抽選予定は専用カレンダーの既定色、発売日予定は赤（Tomato）で登録します。既存の発売日予定も次回監視時に赤へ更新します。

`monitor` workflowのUser-Agentは公開リポジトリURLを自動使用します。個人メールをGitHub Variableへ登録する必要はありません。

Secretsの値はリポジトリ、Pull Request、forkには保存されません。公開リポジトリではActionsの過去ログも誰でも読めるため、アプリ側でもWebhook URLとGoogle Calendar識別子をエラーへ出さない実装にしています。Pull Requestごとに`python scripts/check_public_safety.py`を実行し、秘密鍵、実Webhook、アクセストークン、個人メールなどの混入を止めます。

## ローカル実行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
tcg-monitor validate-config
tcg-monitor --fixture-dir tests/fixtures dry-run
tcg-monitor --fixture-dir tests/fixtures baseline --include-future-releases
tcg-monitor arm
```

本番送信はbaseline完了後にだけ有効化してください。`armed`でない`schedule run`は配信せずエラーになります。

## GitHub Actionsの使い方

移行直後は誤作動と二重実行を防ぐため、`monitor` workflowを手動実行だけに制限しています。Secretsと非公開状態リポジトリへの接続を確認し、手動の`dry-run`と`run`が成功してから定期実行を有効化します。

1. `test` workflowを実行し、ruff、mypy、pytestが成功することを確認します。
2. `monitor` workflowを`baseline`モードで手動実行します。
3. 必要なら`include_future_releases=true`で未来の公式発売日を初期Calendar登録します。
4. `dry-run`で通知予定・除外理由・異常を確認します。
5. `arm`を実行して定期配信を有効化します。
6. 以後は毎日06:04、11:04、16:04、18:04、20:04、22:04（日本時間）に`run`します。監視コードや設定を`main`へ反映した直後にも、取りこぼし防止のため自動実行します。

GitHub Actionsの予約実行は混雑により数分以上遅れる場合があり、指定時刻ちょうどの開始は保証されません。

## コマンド

- `tcg-monitor validate-config`: 設定検証。
- `tcg-monitor baseline [--include-future-releases]`: 現在見える案件を既知化。通常通知しません。
- `tcg-monitor dry-run`: Secretsなしで候補、異常、予定payloadを表示。
- `tcg-monitor run`: armed状態の時だけ配信。
- `tcg-monitor arm`: baseline後にschedule配信を有効化。
- `tcg-monitor status`: 状態JSONを表示。
- `tcg-monitor summary`: 状態JSONからActions用の監視結果表を出力。

共通オプションとして`--source SOURCE_ID`、`--game GAME_ID`、`--fixture-dir tests/fixtures`、`--config sites.yaml`、`--state monitor_state.json`が使えます。`--game`はその1回だけ、`GAME_MONITOR_MODES.txt`でONの作品をさらに絞る確認用オプションです。

## 運用上の注意

- 定期実行は毎日06:04、11:04、16:04、18:04、20:04、22:04（日本時間）の6回です。
- 同一ホスト最低5秒間隔、条件付きGET、20秒×最大3回（合計60秒上限）の限定再試行、別ホスト最大6系統の先読み、実行単位の遮断器を前提にしています。
- robots.txtと規約は運用者が定期確認してください。代表: `https://geo-online.co.jp/robots.txt`, `https://www.pokemoncenter-online.com/robots.txt`, `https://books.rakuten.co.jp/robots.txt`, `https://www.amazon.co.jp/robots.txt`。
- 二次情報通知には「二次情報・公式ページで最終確認」と明示し、公式ページやアプリで最終確認してください。
- Amazon招待リクエストは新規ASINの公式一覧がなく開始日時も公開しないため、ONE PIECEについては実績のある2つの告知アカウントとSNKRDUNKを併用します。Amazon名・招待リクエスト受付・対象BOXが揃う個別投稿だけを採用し、ASINで重複排除して「招待受付を確認した日」としてDiscord通知します。ふるいち公式・公式Xを含む今回の5経路は専用の軽量ジョブで2時間ごとに確認します。Amazonの開始日時は確定できないためCalendarには登録しません。
- 麦わらストアは検証fixture不足のため初期無効のままです。

## 障害対応

Discord異常通知やActionsログで`reason_code`を確認します。代表例は`lottery_text_without_start`、`secondary_official_conflict`、`weekday_date_mismatch`、`empty_body`、`login_or_error_replacement`です。構造変更時は該当ページの最小HTML fixtureを追加し、parserとテストを更新してください。
