# TCG BOX抽選・発売日モニター

ポケモンカードゲーム、ONE PIECEカードゲーム、ドラゴンボールスーパーカードゲーム フュージョンワールド、遊戯王OCG、ディズニー・ロルカナ、ガンダムカードゲームのBOX抽選受付開始と発売日を監視し、DiscordとGoogle Calendarへ重複なく通知するPython 3.12製ツールです。

## 運用構成

- 共通ルールと全監視先は`sites.yaml`で一元管理します。
- 監視状態は、このリポジトリ自身の`monitor-state`ブランチへ`monitor_state.json`として保存します。別リポジトリには依存しません。
- 通知先などの認証情報だけをGitHub Actions Secretsへ保存します。
- 設定・状態とも通常のテキストなので、復号作業なしで確認、修正、テストできます。

## 監視方針

- 汎用の店舗・通販・抽選サイトは、6作品すべてを監視対象として設定します。
- メーカー公式、作品公式ショップ、ポケモンセンターなど作品が限定されるサイトだけは、扱う作品へ限定します。
- 全監視先の確認間隔は120分に統一しています。
- 定期実行は毎日06:04、11:04、16:04、18:04、20:04、22:04（日本時間）の6回です。
- 通常はBOXを対象にします。構築済みデッキ、スターター、単品パック、周辺用品は除外し、`additional_products`に明示した商品だけを抽選監視に追加できます。当選発表だけの告知は対象外です。
- ヤマダデンキ・古本市場／ふるいち・イオンキッズリパブリック・コジマアプリ抽選・TSUTAYA公式LINE合同抽選（一関店／築館店）は、応募告知に結果発表日時が明記されていれば、応募開始とは別にカレンダー予定を登録し、発表日当日にDiscordで一度だけ確認を促します。合同抽選の結果発表日がフォームから読めない場合、特定のフォームと商品名で確認した日付だけを使用します。日付が不明な場合は推測しません。カレンダーの通知時刻は登録先カレンダーの通知設定に従います。
- 公式情報を優先し、二次情報は補完経路として扱います。
- 発売日・発売月はメーカー公式を優先します。公式が未掲載・発売月のみの場合は、検証済みのカードラボ発売日カレンダーの確定日を補完に使います。公式と月が違う場合は採用しません。
- 補完先でも日にちを確認できない場合は、Discordへ「日にち未確定」と一度通知します。仮の日付で予定は作りません。販売店の日付を使う予定には参照先を明示し、後からメーカーの確定日が出たら同じ予定を更新します。
- カードラボはトップの「発売日カレンダー」を自動発見し、通常のHTML取得だけで読みます。記事番号・月別URLの手動更新やブラウザー操作は不要です。列構成・更新日・曜日を検証し、120日を超える未更新、取得失敗、構造変更は既存の監視ログ・異常通知に残します。取得失敗だけでは登録済み予定を削除しません。
- CAPTCHA、Cloudflare、人間確認、ログイン画面は突破せず、監視異常として扱います。

作品ごとのON/OFFは`GAME_MONITOR_MODES.txt`で切り替えます。OFFの作品しか扱わない監視先は、ページ取得前に除外します。

`EXPEDITION_MODE.txt`は、当選時に1回来店すればよい遠征先を地域別に切り替えるファイルです。`EXPEDITION_SENDAI`、`EXPEDITION_TOKYO_ROUTE`、`EXPEDITION_TOKYO`をそれぞれ`ON`または`OFF`にできます。`OFF`の地域は、対象ページへの通信、画像読み取り、監視状態処理を行いません。

- `EXPEDITION_SENDAI`: 従来の仙台遠征5店
- `EXPEDITION_TOKYO_ROUTE`: 福島・郡山・小山・大宮の駅近店
- `EXPEDITION_TOKYO`: 秋葉原・池袋・渋谷・新宿の駅近店

TCバトロコ盛岡大通・仙台駅東口とトレーディングカードピット仙台駅東口店は通常監視のため、地域スイッチに関係なく動きます。リポスト応募、店頭掲示QRだけの応募、当選後に店頭予約と受取の2回来店が必要な回は通知対象から除外します。

## BOX以外の商品を選択して監視する

`sites.yaml` の `games` → 対象作品 → `additional_products` が追加監視商品リストです。
現在はポケモンの「30th CELEBRATION カードセット」全9種を有効にしています。
公式商品情報: https://www.30th.pokemon-card.com/product/cardset

- `id`: 商品群の固定識別子。一度運用した値は変更しないでください。
- `enabled: true`: 監視する。`false`で停止します。
- `name`: 正式商品名の共通部分。通常のBOX名だけを入れると混同するため、商品種別まで書きます。
- `category`: カードセット、デッキセットなど、実際の商品種別。
- `aliases`: 店舗が使う略称・別表記。全角半角、空白、中点は自動で吸収します。
- `variants`: 種類別の名称。種類の区別がない商品は省略できます。
- `selected_variants: []`: 全種類。特定の種類だけ拾う場合は`variants`の名称をここに列挙します。

商品群だけの告知は1件として通知し、明記された種類は個別に判定します。
「30th CELEBRATION カードセット」は全9種を同じ店舗・同じ開始日の抽選ごとに1件へまとめて通知します。
旧版でいずれかの種類を通知済みなら配信履歴を引き継ぎ、残りの種類を再通知しません。
種類を限定した場合、種類不明の告知を選択種類と推測して通知しません。
追加商品はBOXとして偽装せず、同名の拡張パックとは別の商品として重複を管理します。
追加した商品は既存の有効な店舗・作品・地域・応募条件の範囲で監視します。
通常のBOX判定・他商品の除外・発売日監視は従来のままです。

設定保存後の本番反映で監視が動き、以後は既存の定期実行で再確認します。
`baseline`（既知化）のやり直しは不要です。受付中の既存告知も通常の期間判定で拾います。
新しい販売サイトの追加、サイト構造変更、読み取れない画像は別途対応が必要です。

## GitHub Actions Secrets

`Settings` → `Secrets and variables` → `Actions`で次を登録します。値をIssue、Pull Request、Actionsログ、READMEへ貼らないでください。

| Secret | 内容 |
|---|---|
| `DISCORD_WEBHOOK_URL` | 通知先DiscordチャンネルのWebhook URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | GoogleサービスアカウントJSON全文 |
| `GOOGLE_CALENDAR_ID` | 監視専用Google Calendar ID |

状態ブランチへの読み書きには、このリポジトリの`GITHUB_TOKEN`を使います。追加の状態保存用トークンは不要です。

## GitHub Actionsの使い方

1. `test` workflowで設定検証、静的解析、全テストを確認します。
2. 初回だけ`monitor` workflowを`baseline`で実行します。
3. `dry-run`で通知候補を確認します。
4. `arm`を実行し、定期通知を有効化します。
5. 以後は定期実行と、監視コード・設定を`main`へ反映した直後の実行に任せます。

既存の`monitor_state.json`を移行済みなら、`baseline`と`arm`のやり直しは不要です。

## ローカル実行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
tcg-monitor validate-config
pytest
```

監視状態を指定して外部送信なしで確認する場合は次を使います。

```bash
tcg-monitor --state monitor_state.json dry-run
tcg-monitor --state monitor_state.json summary
```

## コマンド

- `tcg-monitor validate-config`: 設定検証
- `tcg-monitor baseline [--include-future-releases]`: 現在見える案件を既知化
- `tcg-monitor dry-run`: 外部送信せず候補を確認
- `tcg-monitor run`: armed状態の時だけ通知
- `tcg-monitor arm`: 定期通知を有効化
- `tcg-monitor status`: 状態JSONを表示
- `tcg-monitor summary`: Actions用の監視結果を生成

共通オプションとして`--source SOURCE_ID`、`--game GAME_ID`、`--fixture-dir tests/fixtures`、`--config sites.yaml`、`--state monitor_state.json`、`--game-switch GAME_MONITOR_MODES.txt`、`--expedition-switch EXPEDITION_MODE.txt`が使えます。

### TSUTAYA公式LINEの応募フォーム

店舗Xと並行して公式フォームを直接監視します。一関店・築館店が選択肢にある場合だけ通知します。
2026年9月21日受付開始の「30th CELEBRATION カードセット」9種も登録済みです。
種類名だけの選択肢は、フォーム名に設定済み商品名がある場合に限り判定します。

新しい応募フォームが別URLで公開された場合は、該当ソースの `discovery_urls` と
`always_fetch_urls` にAPI URLを追加し、`tsutaya_line_forms` に同じ `api_url`・
`public_form_url`・`application_url`（LINE経由）を登録します。複数の応募期間を並行監視できます。
フォームURLの自動更新は行いません。応募リンクに個人のLINE UIDやウォレット情報を保存せず、
LINE側で本人の情報を入力する `LINE_UID`・`WALLET_ADDRESS` を使用します。
