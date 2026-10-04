# 2026年10月4日 自動在庫通知の対象整理

## 今回の変更

38弾の登録を保持し、定価割れ・定価近辺の7弾を一時停止する。停止した弾のルール・商品ページ・過去の履歴・送信済みID・個別の価格上限は削除しない。停止中はその弾の個別巡回・在庫通知を行わない。ほかの弾と共有する店舗一覧は従来どおり確認する。

実際に適用する設定は [`config/inventory-notification-policy.json`](../config/inventory-notification-policy.json)。既存の inventory-sync が既存の認証情報で `toggle` を適用する。設定変更を main に取り込むと同じ同期処理が起動する。自動同期が停止済みルールを再開することはない。対象リストにないルールを強制的に再開することもない。

今回の選別は確認時点の判断であり、相場の常時収集や自動再開を実装したものではない。発売前の商品は将来の相場が未確定なので、今回の停止リストに含めない。定価未確認の商品の在庫通知を保留する既存条件も維持する。

## 停止対象

税込1BOXの商品代金で比較する。送料・手数料は別。二次出品価格は成約価格ではない。店舗の買取価格は査定条件に依存する。

|対象|定価|確認した販売・買取価格|判断|
|---|---:|---|---|
|ガンダム GD02|5,808円|店舗販売5,280円・在庫6点|定価以下の在庫|
|ガンダム GD03|5,808円|店舗販売5,808円・在庫4点|定価の在庫|
|ガンダム GD04|5,808円|二次出品5,700円～|定価以下|
|ガンダム EB01|5,808円|店舗販売3,500円・在庫11点、別店3,600円|定価割れ|
|ロルカナ 大いなるアズライト|5,280円|二次出品4,799円～|定価割れ|
|遊戯王 UTILITY SELECTION|5,940円|二次出品3,100円～、店舗買取1,000円|定価割れ|
|遊戯王 LIMITED PACK WORLD CHAMPIONSHIP 2026|3,960円|二次出品4,000円～、店舗買取2,000円|定価比約101%。通常の購入上限105%より低く、プレミアムがほぼないため停止|

根拠ページと価格種別は設定ファイルの各 `evidence` に保存している。マスターズスクウェアの検索側キャッシュは在庫なしだったが、店舗ページの直接取得と稼働中の監視の両方で在庫数を確認した。売り切れページの旧価格だけでは停止していない。

## 残した主な対象と確認根拠

- ガンダム GD01・GD05、ポケカ30th CELEBRATIONは利用者の指定対象を維持。購入上限は順に6,098円、6,300円、14,400円。
- ポケカの対象5弾は[ホムラの未開封BOX買取表](https://kaitori-homura.com/products?q%5Bproduct_sub_category_id_eq%5D=128&q%5Bproduct_sub_category_product_category_id_eq%5D=14)で定価超えを確認。30thは26,700円、ストームエメラルダ9,400円、アビスアイ・ニンジャスピナー・ムニキスゼロは各8,100円。
- ワンピースの発売済み対象5弾も[ホムラのBOX買取表](https://kaitori-homura.com/products?q%5Bproduct_sub_category_id_eq%5D=132&q%5Bproduct_sub_category_product_category_id_eq%5D=14)で定価超え。OP17は10,800円、OP16は8,600円、OP15は7,500円、EB04は11,500円、OP14は8,000円。
- ドラゴンボールは既存監視でFB09・FB10・ST01の定価超えの販売在庫を確認。FB08も[ルデヤ](https://kaitori-rudeya.com/product/item/6669)の9月27日付買取が7,000円。FB11は[比較サイト](https://pokeca-box-hikaku.com/dragonball/box/fb-11.html)の10月3日表示で最高7,700円（比較情報であり店舗への査定依頼ではない）。定価以下と断定する材料がなく維持。
- ロルカナの[未知なる彼方へ!](https://snkrdunk.com/apparels/834779)、[アーケイジアと魔法の島](https://snkrdunk.com/apparels/745426)、[ジャファーの王権](https://snkrdunk.com/apparels/834771)とヴァインズ・アタック!は二次出品が定価超え。ジャファーとアーケイジアは特典プロモを含む仕様に注意。古い相場記事や売切れ店の価格だけでは除外しない。
- 遊戯王 ORIGINAL ARTWORK COLLECTIONは[ホムラ](https://kaitori-homura.com/products?q%5Bproduct_sub_category_id_eq%5D=159&q%5Bproduct_sub_category_product_category_id_eq%5D=14)買取7,100円、[BEYOND THE BRAVE](https://snkrdunk.com/apparels/855165)は二次出品7,000円～のため維持。

## 設定が二つに分かれている点

サイトのブラウザに保存した合言葉の手動監視と、GitHub経由のDiscord自動監視は別の保存領域。今回変更するのは後者であり、ブラウザの合言葉やWebhookを公開・コピーしない。自動監視の実際の有効／停止／定価未確認を [稼働状況](https://github.com/nekoromme/tcg-box-monitor-public/blob/monitor-state/inventory_status.md) の商品表に表示し、停止理由・出典・設定ファイルへのリンクも付ける。

価格上限の設定は別途維持する。通常は税込定価105%以下、通常の日本語版30th CELEBRATION BOXのみ200%以下。既存の個別上限や送料別の扱いも変更しない。
