# トレカ検知・経路別実証棚卸し

履歴参照: `82b4c0b4438666878f03ee82b2cfa07fa560d5ad`。保存スナップショット: 86件。
設定: 112経路、実行対象: 104経路。

今回の状態記録: `2026-09-05T23:37:53.617396+00:00`。

『候補あり』はそのソースの解析実績。通知成功や全URLの検証を意味しない。
履歴にURL別記録がない期間は、ソース実績から個別URLの作動を推定しない。
候補ゼロは、未開催・期限切れ・対象外条件・取得不良のいずれもあり得る。

取得専用（health_only）やアプリ案内ページの候補ゼロは、抽選検知の実証にはならない。
OFFの記録は過去値であり、今回実行したという意味ではない。

| ソース | 解析種別 | 有効 | 保存履歴で候補あり/実取得回数 | 今回候補 | 取得状態 |
|---|---|---|---:|---:|---|
| pokemon_official_products | 既定 | ON | 78/86 | 0 | degraded |
| onepiece_official_products | 既定 | ON | 86/86 | 1 | success |
| onepiece_official_topics | 既定 | ON | 86/86 | 22 | success |
| dragonball_official_products | 既定 | ON | 86/86 | 7 | success |
| yugioh_official_products | 既定 | ON | 86/86 | 5 | success |
| lorcana_official_products | 既定 | ON | 53/86 | 0 | success |
| gundam_official_products | 既定 | ON | 42/42 | 3 | success |
| konami_style_yugioh | 既定 | ON | 0/86 | 0 | failed |
| yahoo_realtime_konami_style | yahoo_realtime | ON | 0/86 | 0 | failed |
| takaratomy_mall_lorcana | 既定 | ON | 0/86 | 0 | failed |
| yahoo_realtime_lorcana_official | yahoo_realtime | ON | 0/86 | 0 | failed |
| onepiece_official_shop_news | 既定 | ON | 37/86 | 0 | success |
| premium_bandai_dragonball | 既定 | ON | 0/86 | 0 | success |
| dragonball_official_store | 既定 | ON | 30/86 | 1 | success |
| yahoo_realtime_dragonball_official_store | yahoo_realtime | ON | 0/86 | 0 | failed |
| geo | 既定 | ON | 0/86 | 0 | success |
| yahoo_realtime_geo_official | yahoo_realtime | ON | 86/86 | 1 | success |
| pokemon_center_online | 既定 | ON | 0/86 | 0 | failed |
| pokemon_center_store | 既定 | ON | 0/86 | 0 | degraded |
| yahoo_realtime_pokemon_center_store | yahoo_realtime | ON | 50/86 | 2 | success |
| rakuten_books | retailer_lottery | ON | 0/86 | 0 | success |
| yodobashi | 既定 | ON | 0/86 | 0 | failed |
| yahoo_realtime_yodobashi | yahoo_realtime | ON | 0/86 | 0 | success |
| kids_republic | 既定 | ON | 0/86 | 0 | failed |
| yahoo_realtime_kids_republic_official | yahoo_realtime | ON | 0/86 | 0 | failed |
| yamada_denki | 既定 | ON | 0/86 | 0 | success |
| kojima | 既定 | ON | 0/86 | 0 | success |
| yahoo_realtime_yamada_secondary | yahoo_realtime | OFF | 1/1 | 2 | success |
| yahoo_realtime_kojima_secondary | yahoo_realtime | OFF | 0/1 | 0 | success |
| amazon_jp | 既定 | OFF | 0/0 | 未実行 | 未実行 |
| yahoo_realtime_amazon_onepiece_secondary | yahoo_realtime | OFF | 1/1 | 2 | success |
| yahoo_realtime_amazon_gamegetnavi_secondary | yahoo_realtime | OFF | 0/1 | 0 | success |
| snkrdunk_pokemon | snkrdunk | ON | 86/86 | 26 | success |
| snkrdunk_onepiece | snkrdunk | ON | 86/86 | 7 | success |
| premium_bandai_onepiece | 既定 | ON | 86/86 | 22 | success |
| mugiwara_store_onepiece | 既定 | OFF | 0/0 | 未実行 | 未実行 |
| livepocket_hobby_station | livepocket | ON | 86/86 | 5 | success |
| livepocket_fullcomp | livepocket | ON | 0/86 | 0 | degraded |
| livepocket_hmv | livepocket | ON | 0/86 | 0 | failed |
| nyuka_now_fullcomp_livepocket | 既定 | ON | 79/86 | 5 | success |
| yahoo_realtime_premium_bandai_onepiece | yahoo_realtime | ON | 13/86 | 0 | failed |
| nyuka_now_premium_bandai_onepiece | 既定 | ON | 0/79 | 0 | success |
| yahoo_realtime_torecaplaza55 | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_torecaplaza55_secondary | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_seagull_common | yahoo_realtime | ON | 79/86 | 7 | success |
| yahoo_realtime_hareruya2 | yahoo_realtime | ON | 37/86 | 1 | success |
| furuichi_official_lottery | 既定 | ON | 25/86 | 2 | success |
| yahoo_realtime_furuichi | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_hmv | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_hmv_secondary | yahoo_realtime | ON | 86/86 | 0 | failed |
| famima_online_lottery | retailer_lottery | ON | 0/86 | 0 | degraded |
| ministop_online_lottery | retailer_lottery | ON | 0/18 | 0 | failed |
| dmm_hobby_lottery | retailer_lottery | ON | 0/86 | 0 | failed |
| hobby_search_lottery | retailer_lottery | ON | 0/86 | 0 | degraded |
| edion_online_lottery | retailer_lottery | ON | 0/86 | 0 | success |
| itoyokado_online_lottery | retailer_lottery | ON | 0/86 | 0 | failed |
| hobbylink_japan_lottery | retailer_lottery | ON | 0/86 | 0 | failed |
| yahoo_realtime_hobbylink_japan | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_seven_net | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_nojima_online | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_dragonstar_online | yahoo_realtime | ON | 62/86 | 3 | success |
| yahoo_realtime_dmm_tsuhan | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_dmm_onepiece_secondary | yahoo_realtime | OFF | 1/1 | 1 | success |
| yahoo_realtime_hobby_search_secondary | yahoo_realtime | OFF | 1/1 | 1 | success |
| yahoo_realtime_dmm_myca | yahoo_realtime | ON | 86/86 | 6 | success |
| yahoo_realtime_edion | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_famima | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_ministop_secondary | yahoo_realtime | ON | 4/18 | 0 | success |
| tokyo_otaku_mode_lottery | retailer_lottery | ON | 86/86 | 16 | success |
| aeon_style_online | 既定 | ON | 0/86 | 0 | degraded |
| livepocket_tsutaya_akebono | livepocket | ON | 0/86 | 0 | degraded |
| yahoo_realtime_tsutaya_akebono | yahoo_realtime | ON | 19/86 | 1 | success |
| yahoo_realtime_tsutaya_ichinoseki | yahoo_realtime | ON | 14/86 | 2 | success |
| yahoo_realtime_tsutaya_sanuma | yahoo_realtime | ON | 17/86 | 0 | failed |
| yahoo_realtime_mint_sendai | yahoo_realtime | ON | 86/86 | 0 | failed |
| yahoo_realtime_tsutaya_ichinoseki_store | yahoo_realtime | ON | 86/86 | 2 | success |
| yahoo_realtime_torecano_mizusawa | yahoo_realtime | ON | 86/86 | 2 | success |
| yahoo_realtime_tsutaya_nakazato | yahoo_realtime | ON | 13/86 | 0 | failed |
| yahoo_realtime_yorozuya_shiwa | yahoo_realtime | ON | 60/86 | 0 | failed |
| yahoo_realtime_yorozuya_morioka | yahoo_realtime | ON | 60/86 | 0 | failed |
| yahoo_realtime_great_yorozuya_morioka | yahoo_realtime | ON | 60/86 | 0 | failed |
| yahoo_realtime_mandai_furukawa | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_toreca_douraku_sendai | yahoo_realtime | ON | 6/86 | 0 | failed |
| yahoo_realtime_magi_sendai | yahoo_realtime | ON | 13/86 | 0 | failed |
| meli_melo_toreca_douraku_current | curated_store_campaign | ON | 86/86 | 1 | success |
| yahoo_realtime_fullcomp_sendai | yahoo_realtime | ON | 33/86 | 2 | success |
| yahoo_realtime_pokedou_morioka | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_pokedou_kitakami | yahoo_realtime | ON | 0/86 | 0 | failed |
| yahoo_realtime_tsutaya_tsukidate | yahoo_realtime | ON | 86/86 | 2 | success |
| namco_onepiece_official_shop_miyagi | retailer_lottery | ON | 52/86 | 0 | success |
| yahoo_realtime_batoloco_morioka | yahoo_realtime | ON | 17/86 | 3 | success |
| yahoo_realtime_batoloco_sendai | yahoo_realtime | ON | 30/66 | 1 | success |
| yahoo_realtime_tcgpit_sendai | yahoo_realtime | ON | 66/66 | 0 | failed |
| yahoo_realtime_santy_sendai | yahoo_realtime | ON | 46/46 | 0 | failed |
| yahoo_realtime_tsutaya_higashi_sendai | yahoo_realtime | ON | 0/46 | 2 | success |
| yahoo_realtime_tsutaya_chomeigaoka | yahoo_realtime | ON | 9/46 | 2 | success |
| yahoo_realtime_surugaya_rifu | yahoo_realtime | ON | 0/46 | 0 | failed |
| yahoo_realtime_omocha_no_ousama | yahoo_realtime | ON | 23/46 | 0 | failed |
| yahoo_realtime_batoloco_fukushima | yahoo_realtime | ON | 0/38 | 2 | success |
| yahoo_realtime_batoloco_oyama | yahoo_realtime | ON | 12/38 | 2 | success |
| yahoo_realtime_pao_omiya | yahoo_realtime | ON | 9/38 | 0 | failed |
| yahoo_realtime_cardwings_akihabara_pokemon | yahoo_realtime | ON | 0/38 | 0 | failed |
| yahoo_realtime_bigmagic_akihabara | yahoo_realtime | ON | 0/38 | 0 | failed |
| yahoo_realtime_fukufuku_akihabara | yahoo_realtime | ON | 38/38 | 1 | success |
| yahoo_realtime_fukufuku_akihabara_onepiece | yahoo_realtime | ON | 0/38 | 1 | success |
| yahoo_realtime_batoloco_ikebukuro | yahoo_realtime | ON | 0/38 | 0 | failed |
| yahoo_realtime_bigmagic_ikebukuro_pokemon | yahoo_realtime | ON | 38/38 | 4 | success |
| yahoo_realtime_bigmagic_ikebukuro | yahoo_realtime | ON | 0/38 | 0 | failed |
| yahoo_realtime_batoloco_shibuya_satellite | yahoo_realtime | ON | 0/38 | 0 | failed |
| yahoo_realtime_pokemon_card_lounge_shibuya | yahoo_realtime | ON | 38/38 | 0 | failed |
| yahoo_realtime_tierone_shibuya | yahoo_realtime | ON | 38/38 | 3 | success |
| yahoo_realtime_batoloco_shibuya_center | yahoo_realtime | ON | 0/38 | 0 | failed |

## URL別の今回の確認（旧履歴は記録なし）

### ポケモンカードゲーム公式 商品情報

- [https://www.pokemon-card.com/products/index.html?productType=expansion](https://www.pokemon-card.com/products/index.html?productType=expansion): `fetch_failed`、候補0件。{"error": "expected_rendered_content_missing"}
- [https://www.pokemon-card.com/products/](https://www.pokemon-card.com/products/): `fetch_failed`、候補0件。{"error": "expected_rendered_content_missing"}
- [https://www.pokemon-card.com/info/](https://www.pokemon-card.com/info/): `fetch_failed`、候補0件。{"error": "browser_fetch_failed:TimeoutError"}

### ONE PIECEカードゲーム公式 商品情報

- [https://www.onepiece-cardgame.com/products/](https://www.onepiece-cardgame.com/products/): `parsed`、候補1件。

### ONE PIECEカードゲーム公式 トピックス

- [https://www.onepiece-cardgame.com/topics/](https://www.onepiece-cardgame.com/topics/): `parsed`、候補22件。

### フュージョンワールド公式 商品情報

- [https://www.dbs-cardgame.com/fw/jp/products/](https://www.dbs-cardgame.com/fw/jp/products/): `parsed`、候補7件。

### 遊戯王OCG公式 商品情報

- [https://www.yugioh-card.com/japan/products/](https://www.yugioh-card.com/japan/products/): `parsed`、候補5件。

### ディズニー・ロルカナ公式 商品情報

- [https://www.takaratomy.co.jp/products/disneylorcana/product/](https://www.takaratomy.co.jp/products/disneylorcana/product/): `discovery`、候補0件。{"discovered_urls": ["https://www.takaratomy.co.jp/products/disneylorcana/product/attack-of-the-vine/", "https://www.takaratomy.co.jp/products/disneylorcana/product/wilds-unknown/", "https://www.takaratomy.co.jp/products/disneylorcana/product/reign-of-jafar/", "https://www.takaratomy.co.jp/products/disneylorcana/product/archazias-island/", "https://www.takaratomy.co.jp/products/disneylorcana/product/azurite-sea/", "https://www.takaratomy.co.jp/products/disneylorcana/product/shimmering-skies/", "https://www.takaratomy.co.jp/products/disneylorcana/product/ursulas-return/", "https://www.takaratomy.co.jp/products/disneylorcana/product/into-the-inklands/"]}
- [https://www.takaratomy.co.jp/products/disneylorcana/product/archazias-island/](https://www.takaratomy.co.jp/products/disneylorcana/product/archazias-island/): `discovery`、候補0件。{"discovered_urls": ["https://www.takaratomy.co.jp/products/disneylorcana/product/archazias-island/booster-pack/"]}
- [https://www.takaratomy.co.jp/products/disneylorcana/product/archazias-island/booster-pack/](https://www.takaratomy.co.jp/products/disneylorcana/product/archazias-island/booster-pack/): `parsed_empty`、候補0件。
- [https://www.takaratomy.co.jp/products/disneylorcana/product/attack-of-the-vine/](https://www.takaratomy.co.jp/products/disneylorcana/product/attack-of-the-vine/): `discovery`、候補0件。{"discovered_urls": ["https://www.takaratomy.co.jp/products/disneylorcana/product/attack-of-the-vine/booster-pack/"]}
- [https://www.takaratomy.co.jp/products/disneylorcana/product/attack-of-the-vine/booster-pack/](https://www.takaratomy.co.jp/products/disneylorcana/product/attack-of-the-vine/booster-pack/): `parsed_empty`、候補0件。
- [https://www.takaratomy.co.jp/products/disneylorcana/product/azurite-sea/](https://www.takaratomy.co.jp/products/disneylorcana/product/azurite-sea/): `discovery`、候補0件。{"discovered_urls": ["https://www.takaratomy.co.jp/products/disneylorcana/product/azurite-sea/booster-pack/"]}
- [https://www.takaratomy.co.jp/products/disneylorcana/product/azurite-sea/booster-pack/](https://www.takaratomy.co.jp/products/disneylorcana/product/azurite-sea/booster-pack/): `parsed_empty`、候補0件。
- [https://www.takaratomy.co.jp/products/disneylorcana/product/into-the-inklands/](https://www.takaratomy.co.jp/products/disneylorcana/product/into-the-inklands/): `discovery`、候補0件。{"discovered_urls": ["https://www.takaratomy.co.jp/products/disneylorcana/product/into-the-inklands/booster-pack/"]}
- [https://www.takaratomy.co.jp/products/disneylorcana/product/into-the-inklands/booster-pack/](https://www.takaratomy.co.jp/products/disneylorcana/product/into-the-inklands/booster-pack/): `parsed_empty`、候補0件。
- [https://www.takaratomy.co.jp/products/disneylorcana/product/reign-of-jafar/](https://www.takaratomy.co.jp/products/disneylorcana/product/reign-of-jafar/): `discovery`、候補0件。{"discovered_urls": ["https://www.takaratomy.co.jp/products/disneylorcana/product/reign-of-jafar/booster-pack/"]}
- [https://www.takaratomy.co.jp/products/disneylorcana/product/reign-of-jafar/booster-pack/](https://www.takaratomy.co.jp/products/disneylorcana/product/reign-of-jafar/booster-pack/): `parsed_empty`、候補0件。
- [https://www.takaratomy.co.jp/products/disneylorcana/product/shimmering-skies/](https://www.takaratomy.co.jp/products/disneylorcana/product/shimmering-skies/): `discovery`、候補0件。{"discovered_urls": ["https://www.takaratomy.co.jp/products/disneylorcana/product/shimmering-skies/booster-pack/"]}
- [https://www.takaratomy.co.jp/products/disneylorcana/product/shimmering-skies/booster-pack/](https://www.takaratomy.co.jp/products/disneylorcana/product/shimmering-skies/booster-pack/): `parsed_empty`、候補0件。
- [https://www.takaratomy.co.jp/products/disneylorcana/product/ursulas-return/](https://www.takaratomy.co.jp/products/disneylorcana/product/ursulas-return/): `discovery`、候補0件。{"discovered_urls": ["https://www.takaratomy.co.jp/products/disneylorcana/product/ursulas-return/booster-pack/"]}
- [https://www.takaratomy.co.jp/products/disneylorcana/product/ursulas-return/booster-pack/](https://www.takaratomy.co.jp/products/disneylorcana/product/ursulas-return/booster-pack/): `parsed_empty`、候補0件。
- [https://www.takaratomy.co.jp/products/disneylorcana/product/wilds-unknown/](https://www.takaratomy.co.jp/products/disneylorcana/product/wilds-unknown/): `discovery`、候補0件。{"discovered_urls": ["https://www.takaratomy.co.jp/products/disneylorcana/product/wilds-unknown/booster-pack/"]}
- [https://www.takaratomy.co.jp/products/disneylorcana/product/wilds-unknown/booster-pack/](https://www.takaratomy.co.jp/products/disneylorcana/product/wilds-unknown/booster-pack/): `parsed_empty`、候補0件。

### ガンダムカードゲーム公式 商品情報

- [https://www.gundam-gcg.com/jp/products/list.php?page=1&subcategory=product&tag=BOOSTERPACK](https://www.gundam-gcg.com/jp/products/list.php?page=1&subcategory=product&tag=BOOSTERPACK): `parsed`、候補3件。

### KONAMI STYLE（遊戯王OCG）

- [https://www.konamistyle.jp/products/list.php?category_id=1001087&mode=search](https://www.konamistyle.jp/products/list.php?category_id=1001087&mode=search): `fetch_failed`、候補0件。{"error": "http_status_403"}

### KONAMI STYLE公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Akonamistyle%20%E9%81%8A%E6%88%AF%E7%8E%8B%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Akonamistyle%20%E9%81%8A%E6%88%AF%E7%8E%8B%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。
- [https://search.yahoo.co.jp/realtime/search?p=id%3Akonamistyle&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Akonamistyle&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 41, "not_application_announcement": 37}}
- [https://twstalker.com/konamistyle](https://twstalker.com/konamistyle): `fetch_failed`、候補0件。{"error": "http_status_403"}

### タカラトミーモール（ロルカナ）

- [https://takaratomymall.jp/shop/goods/search.aspx?all=0&category=Lorcana&ismodesmartphone=on&optionalcategory=trading&release=0&search=true&sort=spd](https://takaratomymall.jp/shop/goods/search.aspx?all=0&category=Lorcana&ismodesmartphone=on&optionalcategory=trading&release=0&search=true&sort=spd): `fetch_failed`、候補0件。{"error": "browser_fetch_failed:Error"}
- [https://takaratomymall.jp/shop/c/cLorcana/](https://takaratomymall.jp/shop/c/cLorcana/): `fetch_failed`、候補0件。{"error": "browser_fetch_failed:Error"}

### ディズニーロルカナ公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ADisneyLOR_JP%20%E7%99%BA%E5%A3%B2%20%E4%BA%88%E7%B4%84%E9%96%8B%E5%A7%8B&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ADisneyLOR_JP%20%E7%99%BA%E5%A3%B2%20%E4%BA%88%E7%B4%84%E9%96%8B%E5%A7%8B&ei=UTF-8): `parsed_empty`、候補0件。
- [https://search.yahoo.co.jp/realtime/search?p=id%3ADisneyLOR_JP&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ADisneyLOR_JP&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/DisneyLOR_JP](https://twstalker.com/DisneyLOR_JP): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ONE PIECEカードゲーム公式ショップ 公式お知らせ

- [https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/](https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/): `discovery`、候補0件。{"discovered_urls": ["https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/news/important/20260823.html", "https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/news/important/20260123.html", "https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/news/important/20260508.html"]}
- [https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/news/important/20260123.html](https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/news/important/20260123.html): `parsed_empty`、候補0件。{"alerts": ["official_store_start_missing"]}
- [https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/news/important/20260508.html](https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/news/important/20260508.html): `parsed_empty`、候補0件。{"alerts": ["official_store_start_missing"]}
- [https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/news/important/20260823.html](https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/news/important/20260823.html): `parsed_empty`、候補0件。{"alerts": ["official_store_start_missing"]}

### プレミアムバンダイ（フュージョンワールド）

- [https://p-bandai.jp/brand/b0062/](https://p-bandai.jp/brand/b0062/): `discovery`、候補0件。

### フュージョンワールド オフィシャルストア

- [https://bandainamco-am.co.jp/official_shop/dbs-cardgame/](https://bandainamco-am.co.jp/official_shop/dbs-cardgame/): `discovery`、候補0件。{"discovered_urls": ["https://bandainamco-am.co.jp/official_shop/dbs-cardgame/news/important/20260901.html", "https://bandainamco-am.co.jp/official_shop/dbs-cardgame/news/important/20260714.html"]}
- [https://bandainamco-am.co.jp/official_shop/dbs-cardgame/news/important/20260714.html](https://bandainamco-am.co.jp/official_shop/dbs-cardgame/news/important/20260714.html): `parsed_empty`、候補0件。
- [https://bandainamco-am.co.jp/official_shop/dbs-cardgame/news/important/20260901.html](https://bandainamco-am.co.jp/official_shop/dbs-cardgame/news/important/20260901.html): `parsed`、候補1件。

### フュージョンワールド公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Adbfw_cardgameJP%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Adbfw_cardgameJP%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 6, "not_application_announcement": 6}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Adbfw_cardgameJP&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Adbfw_cardgameJP&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/dbfw_cardgameJP](https://twstalker.com/dbfw_cardgameJP): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ゲオ

- [https://geo-online.co.jp/news/](https://geo-online.co.jp/news/): `discovery`、候補0件。{"discovered_urls": ["https://geo-online.co.jp/news/779", "https://geo-online.co.jp/news/780"]}
- [https://geo-online.co.jp/news/779](https://geo-online.co.jp/news/779): `parsed_empty`、候補0件。{"diagnostics": {"application_ended": 1, "validated_application_period": 1, "validated_product": 1}}
- [https://geo-online.co.jp/news/780](https://geo-online.co.jp/news/780): `parsed_empty`、候補0件。{"diagnostics": {"application_ended": 1, "validated_application_period": 1, "validated_product": 1}}

### ゲオ公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3AGEO_official%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AGEO_official%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 26, "application_ended": 5, "disallowed_application": 19, "old_post": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3AGEO_official&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AGEO_official&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 4, "not_application_announcement": 36}}
- [https://search.yahoo.co.jp/realtime/search/tweet/2072968946731594147?detail=1&ifr=tl_twdtl&rkf=1](https://search.yahoo.co.jp/realtime/search/tweet/2072968946731594147?detail=1&ifr=tl_twdtl&rkf=1): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 1, "old_post": 1}}

### ポケモンセンターオンライン

- [https://www.pokemoncenter-online.com/news/](https://www.pokemoncenter-online.com/news/): `fetch_failed`、候補0件。{"error": "http_status_403"}
- [https://www.pokemoncenter-online.com/lottery/landing-page.html](https://www.pokemoncenter-online.com/lottery/landing-page.html): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://www.pokemoncenter-online.com/pokemon-card-game/?q=%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2&srule=top-new-product](https://www.pokemoncenter-online.com/pokemon-card-game/?q=%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2&srule=top-new-product): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://www.pokemoncenter-online.com/pokemon-card-game/booster-packs/](https://www.pokemoncenter-online.com/pokemon-card-game/booster-packs/): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ポケモンセンター各店 公式お知らせ

- [https://shop.pokemon.co.jp/ja/shop/common/news/](https://shop.pokemon.co.jp/ja/shop/common/news/): `fetch_failed`、候補0件。{"error": "http_status_403"}

### ポケモンセンター公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ApokemoncenterPR%20%E3%83%9D%E3%82%B1%E3%83%A2%E3%83%B3%E3%82%AB%E3%83%BC%E3%83%89%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ApokemoncenterPR%20%E3%83%9D%E3%82%B1%E3%83%A2%E3%83%B3%E3%82%AB%E3%83%BC%E3%83%89%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 4, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ApokemoncenterPR&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ApokemoncenterPR&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 40, "disallowed_application": 1, "not_application_announcement": 36}}

### 楽天ブックス

- [https://books.rakuten.co.jp/event/game/card/entry/](https://books.rakuten.co.jp/event/game/card/entry/): `discovery`、候補0件。
- [https://books.rakuten.co.jp/rb/18595282/](https://books.rakuten.co.jp/rb/18595282/): `parsed_empty`、候補0件。{"diagnostics": {"application_ended": 1, "validated_application_period": 1, "validated_product": 1}}

### ヨドバシカメラ

- [https://limited.yodobashi.com/](https://limited.yodobashi.com/): `fetch_failed`、候補0件。{"error": "http_status_403"}

### ヨドバシカメラ公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3AYodobashi_X%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AYodobashi_X%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 31, "not_application_announcement": 9}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3AYodobashi_X&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AYodobashi_X&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 3, "not_application_announcement": 37}}

### イオンキッズリパブリック

- [https://www.kidsrepublic.jp/campaign](https://www.kidsrepublic.jp/campaign): `fetch_failed`、候補0件。{"error": "challenge"}

### キッズリパブリック公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Akidsrepublicjp%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Akidsrepublicjp%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 2, "not_application_announcement": 2}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Akidsrepublicjp&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Akidsrepublicjp&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/kidsrepublicjp](https://twstalker.com/kidsrepublicjp): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ヤマダデンキ

- [https://www.yamada-denki.jp/information/](https://www.yamada-denki.jp/information/): `parsed_empty`、候補0件。
- [https://www.yamada-denki.jp/service/pointservice/digital-kaiin.html](https://www.yamada-denki.jp/service/pointservice/digital-kaiin.html): `今回未実行・実証なし`、候補0件。

### コジマ

- [https://www.kojima.net/shop/app/kojima_appli.html](https://www.kojima.net/shop/app/kojima_appli.html): `parsed_empty`、候補0件。

### スニーカーダンク ポケモンカード抽選・発売情報

- [https://snkrdunk.com/articles/32581/](https://snkrdunk.com/articles/32581/): `parsed`、候補11件。
- [https://snkrdunk.com/articles/15950/](https://snkrdunk.com/articles/15950/): `discovery`、候補0件。{"discovered_urls": ["https://snkrdunk.com/articles/32892/", "https://snkrdunk.com/articles/32425/"]}
- [https://snkrdunk.com/articles/32425/](https://snkrdunk.com/articles/32425/): `parsed`、候補11件。
- [https://snkrdunk.com/articles/32892/](https://snkrdunk.com/articles/32892/): `parsed`、候補4件。

### スニーカーダンク ワンピースカード抽選・発売情報

- [https://snkrdunk.com/articles/32599/](https://snkrdunk.com/articles/32599/): `parsed`、候補7件。
- [https://snkrdunk.com/articles/14006/](https://snkrdunk.com/articles/14006/): `discovery`、候補0件。

### プレミアムバンダイ（ワンピースカード）

- [https://www.onepiece-cardgame.com/topics/](https://www.onepiece-cardgame.com/topics/): `parsed`、候補22件。
- [https://www.onepiece-cardgame.com/products/](https://www.onepiece-cardgame.com/products/): `今回未実行・実証なし`、候補0件。

### ホビーステーション公式抽選情報

- [https://www.hbst.net/category/news/](https://www.hbst.net/category/news/): `parsed`、候補5件。
- [https://livepocket.jp/event/search?word=%E3%83%9B%E3%83%93%E3%83%BC%E3%82%B9%E3%83%86%E3%83%BC%E3%82%B7%E3%83%A7%E3%83%B3&pref=%E5%85%A8%E5%9B%BD%E5%90%84%E5%9C%B0&timespec=1&button=](https://livepocket.jp/event/search?word=%E3%83%9B%E3%83%93%E3%83%BC%E3%82%B9%E3%83%86%E3%83%BC%E3%82%B7%E3%83%A7%E3%83%B3&pref=%E5%85%A8%E5%9B%BD%E5%90%84%E5%9C%B0&timespec=1&button=): `今回未実行・実証なし`、候補0件。

### フルコンプ LivePocket抽選

- [https://livepocket.jp/event/search?word=%E3%83%95%E3%83%AB%E3%82%B3%E3%83%B3%E3%83%97&pref=%E5%85%A8%E5%9B%BD%E5%90%84%E5%9C%B0&timespec=1&button=](https://livepocket.jp/event/search?word=%E3%83%95%E3%83%AB%E3%82%B3%E3%83%B3%E3%83%97&pref=%E5%85%A8%E5%9B%BD%E5%90%84%E5%9C%B0&timespec=1&button=): `fetch_failed`、候補0件。{"error": "challenge"}
- [https://t.livepocket.jp/event/search?word=%E3%83%95%E3%83%AB%E3%82%B3%E3%83%B3%E3%83%97&pref=%E5%85%A8%E5%9B%BD%E5%90%84%E5%9C%B0&timespec=1&button=](https://t.livepocket.jp/event/search?word=%E3%83%95%E3%83%AB%E3%82%B3%E3%83%B3%E3%83%97&pref=%E5%85%A8%E5%9B%BD%E5%90%84%E5%9C%B0&timespec=1&button=): `discovery`、候補0件。

### HMVトレカショップ LivePocket抽選

- [https://livepocket.jp/event/search?word=HMV%E3%83%88%E3%83%AC%E3%82%AB%E3%82%B7%E3%83%A7%E3%83%83%E3%83%97&pref=%E5%85%A8%E5%9B%BD%E5%90%84%E5%9C%B0&timespec=1&button=](https://livepocket.jp/event/search?word=HMV%E3%83%88%E3%83%AC%E3%82%AB%E3%82%B7%E3%83%A7%E3%83%83%E3%83%97&pref=%E5%85%A8%E5%9B%BD%E5%90%84%E5%9C%B0&timespec=1&button=): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://t.livepocket.jp/event/search?word=HMV%E3%83%88%E3%83%AC%E3%82%AB%E3%82%B7%E3%83%A7%E3%83%83%E3%83%97&pref=%E5%85%A8%E5%9B%BD%E5%90%84%E5%9C%B0&timespec=1&button=](https://t.livepocket.jp/event/search?word=HMV%E3%83%88%E3%83%AC%E3%82%AB%E3%82%B7%E3%83%A7%E3%83%83%E3%83%97&pref=%E5%85%A8%E5%9B%BD%E5%90%84%E5%9C%B0&timespec=1&button=): `discovery`、候補0件。

### 入荷Now ポケカ抽選補完欄

- [https://nyuka-now.com/archives/97393](https://nyuka-now.com/archives/97393): `parsed`、候補1件。
- [https://nyuka-now.com/archives/2459](https://nyuka-now.com/archives/2459): `parsed`、候補4件。

### プレミアムバンダイ公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Ap_bandai%20ONE%20PIECE%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ap_bandai%20ONE%20PIECE%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 5, "excluded_product": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Ap_bandai&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ap_bandai&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 35}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Ap_bandai%20%E3%83%AF%E3%83%B3%E3%83%94%E3%82%AB%E3%83%BC%E3%83%89%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ap_bandai%20%E3%83%AF%E3%83%B3%E3%83%94%E3%82%AB%E3%83%BC%E3%83%89%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 5, "excluded_product": 1}}
- [https://twstalker.com/p_bandai](https://twstalker.com/p_bandai): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### 入荷Now プレミアムバンダイ抽選欄

- [https://nyuka-now.com/archives/97393](https://nyuka-now.com/archives/97393): `parsed_empty`、候補0件。

### トレカプラザ55通販店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Atorepla_ec%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Atorepla_ec%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。
- [https://search.yahoo.co.jp/realtime/search?p=id%3Atorepla_ec&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Atorepla_ec&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/torepla_ec](https://twstalker.com/torepla_ec): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### トレカプラザ55通販店 抽選補完 Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Apokecamatomeru%20%E3%83%88%E3%83%AC%E3%82%AB%E3%83%97%E3%83%A9%E3%82%B655%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Apokecamatomeru%20%E3%83%88%E3%83%AC%E3%82%AB%E3%83%97%E3%83%A9%E3%82%B655%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。
- [https://search.yahoo.co.jp/realtime/search?p=id%3Apokecamatomeru&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Apokecamatomeru&ei=UTF-8): `parsed_empty`、候補0件。
- [https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2Fpokecamatomeru%2Fstatus%2F2088582782822055952&omit_script=1&dnt=1](https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2Fpokecamatomeru%2Fstatus%2F2088582782822055952&omit_script=1&dnt=1): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 1, "application_ended": 1}}
- [https://twstalker.com/pokecamatomeru](https://twstalker.com/pokecamatomeru): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### シーガル17店舗共通公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ASeagullJP%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ASeagullJP%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補4件。{"diagnostics": {"account_posts": 5, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ASeagullJP&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ASeagullJP&ei=UTF-8): `parsed`、候補3件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 37}}
- [https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2FSeagullJP%2Fstatus%2F2090969780274798744&omit_script=1&dnt=1](https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2FSeagullJP%2Fstatus%2F2090969780274798744&omit_script=1&dnt=1): `今回未実行・実証なし`、候補0件。
- [https://twstalker.com/SeagullJP](https://twstalker.com/SeagullJP): `今回未実行・実証なし`、候補0件。

### 晴れる屋2公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Ahareruya2pokeca%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ahareruya2pokeca%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 7, "application_ended": 1, "disallowed_application": 2, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Ahareruya2pokeca&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ahareruya2pokeca&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/hareruya2pokeca](https://twstalker.com/hareruya2pokeca): `今回未実行・実証なし`、候補0件。
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fhareruya2pokeca%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fhareruya2pokeca%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `今回未実行・実証なし`、候補0件。

### 古本市場・ふるいち公式 BOX抽選お知らせ

- [https://www.furu1.net/news/news_information.html](https://www.furu1.net/news/news_information.html): `discovery`、候補0件。{"discovered_urls": ["https://www.furu1.net/news/news_information/pdl20260901"]}
- [https://www.furu1.net/news/news_information/pdl20260901](https://www.furu1.net/news/news_information/pdl20260901): `parsed`、候補2件。

### 古本市場・ふるいち公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Afuru1tenpo%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Afuru1tenpo%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 6, "excluded_product": 1, "not_application_announcement": 2}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Afuru1tenpo&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Afuru1tenpo&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 1, "not_application_announcement": 38}}
- [https://twstalker.com/furu1tenpo](https://twstalker.com/furu1tenpo): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### HMV公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3AHMV_Japan%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AHMV_Japan%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 15, "not_application_announcement": 24}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3AHMV_Japan&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AHMV_Japan&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/HMV_Japan](https://twstalker.com/HMV_Japan): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### HMV抽選補完 Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Agamegetnavi%20HMV%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Agamegetnavi%20HMV%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 1, "application_ended": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Agamegetnavi&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Agamegetnavi&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "retailer_not_matched": 40}}
- [https://twstalker.com/gamegetnavi](https://twstalker.com/gamegetnavi): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ファミマオンライン 抽選商品

- [https://famima-online.family.co.jp/search?receiveType=1](https://famima-online.family.co.jp/search?receiveType=1): `discovery_failed`、候補0件。{"error": "ファミマオンラインがメンテナンス・地域制限のエラーページを返しました"}

### ミニストップオンライン 抽選商品

- [https://online.ministop.co.jp/Form/Product/ProductList.aspx?cat=008&dpcnt=40&fpfl=0&img=2&pno=1&sfl=0&shop=0&sort=07&udns=0](https://online.ministop.co.jp/Form/Product/ProductList.aspx?cat=008&dpcnt=40&fpfl=0&img=2&pno=1&sfl=0&shop=0&sort=07&udns=0): `fetch_failed`、候補0件。{"error": "http_status_403"}
- [https://online.ministop.co.jp/Page/pockemon.aspx](https://online.ministop.co.jp/Page/pockemon.aspx): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### DMM通販 ホビー抽選販売

- [https://www.dmm.com/mono/hobby/-/list/=/article=directory/id=5027/](https://www.dmm.com/mono/hobby/-/list/=/article=directory/id=5027/): `fetch_failed`、候補0件。{"error": "challenge"}

### ホビーサーチ BOX抽選販売

- [https://www.1999.co.jp/list/3352/7/1](https://www.1999.co.jp/list/3352/7/1): `fetch_failed`、候補0件。{"error": "http_status_403"}

### エディオンネットショップ 抽選販売

- [https://www.edion.com/](https://www.edion.com/): `discovery`、候補0件。

### イトーヨーカドーネット通販 予約・抽選一覧

- [https://iyec.itoyokado.co.jp/shop/e/eE4reslot/](https://iyec.itoyokado.co.jp/shop/e/eE4reslot/): `discovery`、候補0件。
- [https://iyec.itoyokado.co.jp/shop/pages/apply_pomega_04.aspx](https://iyec.itoyokado.co.jp/shop/pages/apply_pomega_04.aspx): `fetch_failed`、候補0件。{"error": "http_status_404"}

### ホビーリンク・ジャパン 公式抽選販売

- [https://support.hlj.co.jp/hc/ja/sections/203939188-%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B](https://support.hlj.co.jp/hc/ja/sections/203939188-%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B): `fetch_failed`、候補0件。{"error": "http_status_403"}

### ホビーリンク・ジャパン公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Ahobbylink_jp%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ahobbylink_jp%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 2, "application_ended": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Ahobbylink_jp&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ahobbylink_jp&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 39}}
- [https://twstalker.com/hobbylink_jp](https://twstalker.com/hobbylink_jp): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### セブンネットショッピング公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3A7_netshopping%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3A7_netshopping%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 6, "disallowed_application": 3, "not_application_announcement": 1, "old_post": 2}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3A7_netshopping&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3A7_netshopping&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 1, "not_application_announcement": 39}}
- [https://twstalker.com/7_netshopping](https://twstalker.com/7_netshopping): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ノジマオンライン公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3AENETJP%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AENETJP%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 3, "disallowed_application": 1, "not_application_announcement": 2}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3AENETJP&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AENETJP&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 33, "disallowed_application": 1, "not_application_announcement": 32}}
- [https://twstalker.com/ENETJP](https://twstalker.com/ENETJP): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ドラゴンスター通販公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Ads_ecommerce%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ads_ecommerce%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補2件。{"diagnostics": {"account_posts": 40, "application_ended": 12, "disallowed_application": 1, "not_application_announcement": 11}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Ads_ecommerce&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ads_ecommerce&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 36}}
- [https://twstalker.com/ds_ecommerce](https://twstalker.com/ds_ecommerce): `今回未実行・実証なし`、候補0件。

### DMM通販公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ADMM_tsuhan%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ADMM_tsuhan%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 6}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ADMM_tsuhan&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ADMM_tsuhan&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 2, "not_application_announcement": 34}}
- [https://twstalker.com/DMM_tsuhan](https://twstalker.com/DMM_tsuhan): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### DMMマイカ公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ADMM_Myca%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ADMM_Myca%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補4件。{"diagnostics": {"account_posts": 17, "application_ended": 5, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ADMM_Myca&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ADMM_Myca&ei=UTF-8): `parsed`、候補2件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 37}}
- [https://twstalker.com/DMM_Myca](https://twstalker.com/DMM_Myca): `今回未実行・実証なし`、候補0件。

### エディオン公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Aedion_PR%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Aedion_PR%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 22, "disallowed_application": 7, "not_application_announcement": 15}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Aedion_PR&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Aedion_PR&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 4, "not_application_announcement": 36}}
- [https://twstalker.com/edion_PR](https://twstalker.com/edion_PR): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ファミリーマート公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Afamima_now%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Afamima_now%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 10, "not_application_announcement": 30}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Afamima_now&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Afamima_now&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 5, "not_application_announcement": 35}}
- [https://twstalker.com/famima_now](https://twstalker.com/famima_now): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ミニストップオンライン抽選補完 Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Agamegetnavi%20%E3%83%9F%E3%83%8B%E3%82%B9%E3%83%88%E3%83%83%E3%83%97%E3%82%AA%E3%83%B3%E3%83%A9%E3%82%A4%E3%83%B3%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Agamegetnavi%20%E3%83%9F%E3%83%8B%E3%82%B9%E3%83%88%E3%83%83%E3%83%97%E3%82%AA%E3%83%B3%E3%83%A9%E3%82%A4%E3%83%B3%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。
- [https://twstalker.com/gamegetnavi](https://twstalker.com/gamegetnavi): `今回未実行・実証なし`、候補0件。

### Tokyo Otaku Mode 公式抽選販売

- [https://ja.otakumode.com/blogs/news](https://ja.otakumode.com/blogs/news): `discovery`、候補0件。{"discovered_urls": ["https://ja.otakumode.com/blogs/news/pokemontcg-raffle-260831", "https://ja.otakumode.com/blogs/news/pokemontcg-raffle-260817", "https://ja.otakumode.com/blogs/news/pokemontcg-storm-emeralda-raffle", "https://ja.otakumode.com/blogs/news/abyss-eye-3", "https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-9", "https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-8", "https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-7", "https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-6", "https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-5", "https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-4", "https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-3", "https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-2", "https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8", "https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-1"]}
- [https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8](https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8): `parsed`、候補3件。
- [https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-1](https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-1): `parsed`、候補1件。
- [https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-2](https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-2): `parsed`、候補1件。
- [https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-3](https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-3): `parsed`、候補2件。
- [https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-4](https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-4): `parsed`、候補2件。
- [https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-5](https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-5): `parsed_empty`、候補0件。{"alerts": ["retailer_box_product_missing"]}
- [https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-6](https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-6): `parsed`、候補1件。
- [https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-7](https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-7): `parsed`、候補1件。
- [https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-8](https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-8): `parsed`、候補1件。
- [https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-9](https://ja.otakumode.com/blogs/news/%E6%8A%BD%E9%81%B8%E8%B2%A9%E5%A3%B2-%E6%8A%BD%E9%81%B8%E5%BF%9C%E5%8B%9F%E5%8F%97%E4%BB%98%E9%96%8B%E5%A7%8B%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B-9): `parsed_empty`、候補0件。{"alerts": ["retailer_box_product_missing"]}
- [https://ja.otakumode.com/blogs/news/abyss-eye-3](https://ja.otakumode.com/blogs/news/abyss-eye-3): `parsed`、候補1件。
- [https://ja.otakumode.com/blogs/news/pokemontcg-raffle-260817](https://ja.otakumode.com/blogs/news/pokemontcg-raffle-260817): `parsed`、候補1件。
- [https://ja.otakumode.com/blogs/news/pokemontcg-raffle-260831](https://ja.otakumode.com/blogs/news/pokemontcg-raffle-260831): `parsed`、候補1件。
- [https://ja.otakumode.com/blogs/news/pokemontcg-storm-emeralda-raffle](https://ja.otakumode.com/blogs/news/pokemontcg-storm-emeralda-raffle): `parsed`、候補1件。

### イオン（東北地方対象のウェブ応募）

- [https://aeonretail.com/campaign/](https://aeonretail.com/campaign/): `fetch_failed`、候補0件。{"error": "challenge"}
- [https://www.aeonstyleonline.com/](https://www.aeonstyleonline.com/): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### TSUTAYAあけぼの店（石巻）LivePocket抽選

- [https://livepocket.jp/event/search?word=TSUTAYA%E3%80%80%E3%81%82%E3%81%91%E3%81%BC%E3%81%AE&pref=%E5%AE%AE%E5%9F%8E%E7%9C%8C&timespec=1&button=](https://livepocket.jp/event/search?word=TSUTAYA%E3%80%80%E3%81%82%E3%81%91%E3%81%BC%E3%81%AE&pref=%E5%AE%AE%E5%9F%8E%E7%9C%8C&timespec=1&button=): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://t.livepocket.jp/event/search?word=TSUTAYA%E3%80%80%E3%81%82%E3%81%91%E3%81%BC%E3%81%AE&pref=%E5%AE%AE%E5%9F%8E%E7%9C%8C&timespec=1&button=](https://t.livepocket.jp/event/search?word=TSUTAYA%E3%80%80%E3%81%82%E3%81%91%E3%81%BC%E3%81%AE&pref=%E5%AE%AE%E5%9F%8E%E7%9C%8C&timespec=1&button=): `discovery`、候補0件。

### TSUTAYAあけぼの店（石巻）公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3AAKEBONOtoreka%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AAKEBONOtoreka%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3AAKEBONOtoreka&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AAKEBONOtoreka&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 39}}
- [https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2FAKEBONOtoreka%2Fstatus%2F2096070820426899487&omit_script=1&dnt=1](https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2FAKEBONOtoreka%2Fstatus%2F2096070820426899487&omit_script=1&dnt=1): `parsed`、候補1件。{"diagnostics": {"account_posts": 1}}
- [https://twstalker.com/AKEBONOtoreka](https://twstalker.com/AKEBONOtoreka): `今回未実行・実証なし`、候補0件。

### TSUTAYA一関中央店 Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ATSUTAYA19392430%E3%80%80%E6%8A%BD%E9%81%B8&ei=UTF-8&ifr=tl_sc](https://search.yahoo.co.jp/realtime/search?p=id%3ATSUTAYA19392430%E3%80%80%E6%8A%BD%E9%81%B8&ei=UTF-8&ifr=tl_sc): `parsed`、候補1件。{"diagnostics": {"account_posts": 3, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ATSUTAYA19392430&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ATSUTAYA19392430&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 39}}
- [https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2FTSUTAYA19392430%2Fstatus%2F2096124692696621430&omit_script=1&dnt=1](https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2FTSUTAYA19392430%2Fstatus%2F2096124692696621430&omit_script=1&dnt=1): `今回未実行・実証なし`、候補0件。
- [https://twstalker.com/TSUTAYA19392430](https://twstalker.com/TSUTAYA19392430): `今回未実行・実証なし`、候補0件。

### Vidaway佐沼店（TSUTAYA佐沼）Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Avw_1323+%E6%8A%BD%E9%81%B8&ei=UTF-8&ifr=tl_sc](https://search.yahoo.co.jp/realtime/search?p=id%3Avw_1323+%E6%8A%BD%E9%81%B8&ei=UTF-8&ifr=tl_sc): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 8, "excluded_product": 1, "not_application_announcement": 2}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Avw_1323&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Avw_1323&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "excluded_product": 1, "not_application_announcement": 39}}
- [https://twstalker.com/vw_1323](https://twstalker.com/vw_1323): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### MINT仙台店 Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Amintsendai%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Amintsendai%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 5, "application_ended": 4, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Amintsendai&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Amintsendai&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "application_ended": 1, "not_application_announcement": 39}}
- [https://twstalker.com/mintsendai](https://twstalker.com/mintsendai): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### TSUTAYA一関店 Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Atsutayaichi0412%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Atsutayaichi0412%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 2, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Atsutayaichi0412&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Atsutayaichi0412&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 31, "not_application_announcement": 30}}
- [https://twstalker.com/tsutayaichi0412](https://twstalker.com/tsutayaichi0412): `今回未実行・実証なし`、候補0件。
- [https://forms.cloud.microsoft/formapi/api/f3b1cae3-b69a-4f4e-8a60-7ba2714fec4f/users/b459d036-98cf-4b78-86c3-9ab4b55edd66/light/runtimeForms('48qx85q2Tk-KYHuicU_sTzbQWbTPmHhLhsOatLVe3WZUM1NCTUw5SzdMMk1ITFFZU1BPNE43SEpUUi4u')?$expand=questions($expand=choices)](https://forms.cloud.microsoft/formapi/api/f3b1cae3-b69a-4f4e-8a60-7ba2714fec4f/users/b459d036-98cf-4b78-86c3-9ab4b55edd66/light/runtimeForms('48qx85q2Tk-KYHuicU_sTzbQWbTPmHhLhsOatLVe3WZUM1NCTUw5SzdMMk1ITFFZU1BPNE43SEpUUi4u')?$expand=questions($expand=choices)): `fetch_failed`、候補0件。{"error": "http_status_403"}
- [https://search.yahoo.co.jp/realtime/search/tweet/2077921225880317972?detail=1&ifr=tl_twdtl&rkf=1](https://search.yahoo.co.jp/realtime/search/tweet/2077921225880317972?detail=1&ifr=tl_twdtl&rkf=1): `parsed_empty`、候補0件。

### トレカノ奥州水沢店 Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3AWG_Mizusawa_TCG%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AWG_Mizusawa_TCG%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補2件。{"diagnostics": {"account_posts": 4, "not_application_announcement": 1, "tournament_or_result": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3AWG_Mizusawa_TCG&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AWG_Mizusawa_TCG&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 39, "tournament_or_result": 1}}
- [https://twstalker.com/WG_Mizusawa_TCG](https://twstalker.com/WG_Mizusawa_TCG): `今回未実行・実証なし`、候補0件。

### TSUTAYA中里店（石巻）公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ANAKAZATOtoreka%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ANAKAZATOtoreka%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 5, "application_ended": 1, "disallowed_application": 1, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ANAKAZATOtoreka&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ANAKAZATOtoreka&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/NAKAZATOtoreka](https://twstalker.com/NAKAZATOtoreka): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### 萬屋紫波店トレカ公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3AShiwaten_card%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AShiwaten_card%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 4, "disallowed_application": 3, "old_post": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3AShiwaten_card&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AShiwaten_card&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 26, "disallowed_application": 3, "not_application_announcement": 22, "old_post": 1}}
- [https://twstalker.com/Shiwaten_card](https://twstalker.com/Shiwaten_card): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### 萬屋盛岡店トレカ公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Ayorozuya_card%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ayorozuya_card%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 8, "disallowed_application": 4, "not_application_announcement": 1, "old_post": 3}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Ayorozuya_card&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Ayorozuya_card&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 24, "disallowed_application": 4, "not_application_announcement": 17, "old_post": 3}}
- [https://twstalker.com/yorozuya_card](https://twstalker.com/yorozuya_card): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ザ・グレートヨロズヤ盛岡高松店トレカ公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3AGtakamatsu_card%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AGtakamatsu_card%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 3, "disallowed_application": 3}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3AGtakamatsu_card&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AGtakamatsu_card&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 2, "not_application_announcement": 38}}
- [https://twstalker.com/Gtakamatsu_card](https://twstalker.com/Gtakamatsu_card): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### 万代古川店カードコーナー公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Amandaifurukaw3%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Amandaifurukaw3%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 1, "old_post": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Amandaifurukaw3&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Amandaifurukaw3&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/mandaifurukaw3](https://twstalker.com/mandaifurukaw3): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### トレカ道楽 仙台駅前アーケード店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ADourakusendai%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ADourakusendai%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 5, "disallowed_application": 1, "not_application_announcement": 2, "old_post": 2}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ADourakusendai&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ADourakusendai&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://search.yahoo.co.jp/realtime/search?p=%E3%83%88%E3%83%AC%E3%82%AB%E9%81%93%E6%A5%BD%20%E4%BB%99%E5%8F%B0%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=%E3%83%88%E3%83%AC%E3%82%AB%E9%81%93%E6%A5%BD%20%E4%BB%99%E5%8F%B0%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 3, "disallowed_application": 1, "old_post": 2}}
- [https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2FDourakusendai%2Fstatus%2F2084826013847130224&omit_script=1&dnt=1](https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2FDourakusendai%2Fstatus%2F2084826013847130224&omit_script=1&dnt=1): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 1, "application_ended": 1}}
- [https://twstalker.com/Dourakusendai](https://twstalker.com/Dourakusendai): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### magi仙台店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Amagi_sendai%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Amagi_sendai%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 10, "application_ended": 2, "not_application_announcement": 4, "old_post": 3}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Amagi_sendai&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Amagi_sendai&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/magi_sendai](https://twstalker.com/magi_sendai): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### トレカ道楽仙台店 現行抽選補完

- [https://meli-melo.blog.jp/archives/1083580084.html](https://meli-melo.blog.jp/archives/1083580084.html): `parsed`、候補1件。

### フルコンプ仙台駅前店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Afc_sendaieki%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Afc_sendaieki%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 4, "application_ended": 1, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Afc_sendaieki&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Afc_sendaieki&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 39}}
- [https://twstalker.com/fc_sendaieki](https://twstalker.com/fc_sendaieki): `今回未実行・実証なし`、候補0件。

### ポケ堂盛岡店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3APokedouTencho_M%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3APokedouTencho_M%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。
- [https://search.yahoo.co.jp/realtime/search?p=id%3APokedouTencho_M&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3APokedouTencho_M&ei=UTF-8): `parsed_empty`、候補0件。
- [https://twstalker.com/PokedouTencho_M](https://twstalker.com/PokedouTencho_M): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### ポケ堂北上店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3APokedouTencho_K%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3APokedouTencho_K%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。
- [https://search.yahoo.co.jp/realtime/search?p=id%3APokedouTencho_K&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3APokedouTencho_K&ei=UTF-8): `parsed_empty`、候補0件。
- [https://twstalker.com/PokedouTencho_K](https://twstalker.com/PokedouTencho_K): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### TSUTAYA築館店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Atsukidateten%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Atsukidateten%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Atsukidateten&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Atsukidateten&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 18, "not_application_announcement": 17}}
- [https://twstalker.com/tsukidateten](https://twstalker.com/tsukidateten): `今回未実行・実証なし`、候補0件。

### ONE PIECEカードゲーム公式ショップ 仙台・宮城名取

- [https://parks2.bandainamco-am.co.jp/category/EL/](https://parks2.bandainamco-am.co.jp/category/EL/): `discovery`、候補0件。

### TCバトロコ盛岡大通公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_mrok%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_mrok%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 6, "not_application_announcement": 1, "tournament_or_result": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_mrok&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_mrok&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 39}}
- [https://twstalker.com/batoloco_mrok](https://twstalker.com/batoloco_mrok): `今回未実行・実証なし`、候補0件。
- [https://search.yahoo.co.jp/realtime/search/tweet/2076933479003250751?detail=1&ifr=tl_twdtl&rkf=1](https://search.yahoo.co.jp/realtime/search/tweet/2076933479003250751?detail=1&ifr=tl_twdtl&rkf=1): `parsed_empty`、候補0件。
- [https://search.yahoo.co.jp/realtime/search/tweet/2096063514163155133?detail=1&ifr=tl_twdtl&rkf=1](https://search.yahoo.co.jp/realtime/search/tweet/2096063514163155133?detail=1&ifr=tl_twdtl&rkf=1): `parsed`、候補1件。{"diagnostics": {"account_posts": 2, "not_application_announcement": 1}}

### TCバトロコ仙台駅東口公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_SND%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_SND%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 5, "application_ended": 3}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_SND&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_SND&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/batoloco_SND](https://twstalker.com/batoloco_SND): `今回未実行・実証なし`、候補0件。

### トレーディングカードピット仙台駅東口店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Atcgpit_sendai%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Atcgpit_sendai%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 12, "application_ended": 6, "disallowed_application": 1, "not_application_announcement": 4}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Atcgpit_sendai&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Atcgpit_sendai&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/tcgpit_sendai](https://twstalker.com/tcgpit_sendai): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### santy仙台クリスロード店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Asantycrissroad%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Asantycrissroad%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 7, "disallowed_application": 4, "not_application_announcement": 3}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Asantycrissroad&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Asantycrissroad&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 3, "not_application_announcement": 37}}
- [https://twstalker.com/santycrissroad](https://twstalker.com/santycrissroad): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### TSUTAYAヤマト屋書店東仙台店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3AYTHtoreka%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AYTHtoreka%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 7, "application_ended": 4, "disallowed_application": 1, "excluded_product": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3AYTHtoreka&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AYTHtoreka&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 40, "application_ended": 4, "excluded_product": 1, "not_application_announcement": 34}}
- [https://twstalker.com/YTHtoreka](https://twstalker.com/YTHtoreka): `今回未実行・実証なし`、候補0件。

### TSUTAYA BOOKSTORE仙台長命ヶ丘公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ATBSSENDAICHOMEI%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ATBSSENDAICHOMEI%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 6, "not_application_announcement": 5}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ATBSSENDAICHOMEI&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ATBSSENDAICHOMEI&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 29, "not_application_announcement": 28}}
- [https://twstalker.com/TBSSENDAICHOMEI](https://twstalker.com/TBSSENDAICHOMEI): `今回未実行・実証なし`、候補0件。

### 駿河屋イオンモール新利府南館店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ASURUGAYA_RIFU%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ASURUGAYA_RIFU%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 2, "old_post": 2}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ASURUGAYA_RIFU&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ASURUGAYA_RIFU&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/SURUGAYA_RIFU](https://twstalker.com/SURUGAYA_RIFU): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### おもちゃの王様公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3AKingOfToyss%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AKingOfToyss%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。
- [https://search.yahoo.co.jp/realtime/search?p=id%3AKingOfToyss&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3AKingOfToyss&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/KingOfToyss](https://twstalker.com/KingOfToyss): `fetch_failed`、候補0件。{"error": "host_circuit_open"}

### TCバトロコ福島駅前公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_fuku%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_fuku%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 5, "application_ended": 1, "disallowed_application": 1, "not_application_announcement": 2}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_fuku&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_fuku&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 39}}
- [https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2Fbatoloco_fuku%2Fstatus%2F2095742710691053657&omit_script=true&lang=ja](https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2Fbatoloco_fuku%2Fstatus%2F2095742710691053657&omit_script=true&lang=ja): `今回未実行・実証なし`、候補0件。
- [https://twstalker.com/batoloco_fuku](https://twstalker.com/batoloco_fuku): `今回未実行・実証なし`、候補0件。
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fbatoloco_fuku%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fbatoloco_fuku%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `今回未実行・実証なし`、候補0件。

### TCバトロコ小山駅前公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_oyama%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_oyama%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 2, "application_ended": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_oyama&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_oyama&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 39}}
- [https://twstalker.com/batoloco_oyama](https://twstalker.com/batoloco_oyama): `今回未実行・実証なし`、候補0件。
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fbatoloco_oyama%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fbatoloco_oyama%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `今回未実行・実証なし`、候補0件。

### カードショップ竜星のPAO大宮店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3APAOtoreka_omiya%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3APAOtoreka_omiya%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 18, "application_ended": 7, "disallowed_application": 5, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3APAOtoreka_omiya&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3APAOtoreka_omiya&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 1, "not_application_announcement": 39}}
- [https://twstalker.com/PAOtoreka_omiya](https://twstalker.com/PAOtoreka_omiya): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2FPAOtoreka_omiya%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2FPAOtoreka_omiya%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `parsed_empty`、候補0件。

### CARD WINGS秋葉原駅前店ポケモンカード公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ACARDWINGS_POKE%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ACARDWINGS_POKE%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 3, "disallowed_application": 1, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ACARDWINGS_POKE&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ACARDWINGS_POKE&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 29, "disallowed_application": 1, "not_application_announcement": 27}}
- [https://twstalker.com/CARDWINGS_POKE](https://twstalker.com/CARDWINGS_POKE): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2FCARDWINGS_POKE%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2FCARDWINGS_POKE%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `parsed_empty`、候補0件。

### BIG MAGIC秋葉原店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Abigmagicakb%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abigmagicakb%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 3, "disallowed_application": 2, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Abigmagicakb&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abigmagicakb&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/bigmagicakb](https://twstalker.com/bigmagicakb): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fbigmagicakb%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fbigmagicakb%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `parsed_empty`、候補0件。

### 福福トレカ秋葉原店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Afukufuku_toreka%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Afukufuku_toreka%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 11, "not_application_announcement": 8, "old_post": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Afukufuku_toreka&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Afukufuku_toreka&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 39}}
- [https://twstalker.com/fukufuku_toreka](https://twstalker.com/fukufuku_toreka): `今回未実行・実証なし`、候補0件。
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2Ffukufuku_toreka%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2Ffukufuku_toreka%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `今回未実行・実証なし`、候補0件。

### 福福トレカ秋葉原店ワンピース公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Afukufuku_one%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Afukufuku_one%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 7, "disallowed_application": 3, "not_application_announcement": 3}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Afukufuku_one&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Afukufuku_one&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "disallowed_application": 1, "not_application_announcement": 39}}
- [https://twstalker.com/fukufuku_one](https://twstalker.com/fukufuku_one): `今回未実行・実証なし`、候補0件。
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2Ffukufuku_one%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2Ffukufuku_one%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `今回未実行・実証なし`、候補0件。

### TCバトロコ池袋駅前店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ABatoloco_1852%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ABatoloco_1852%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 16, "disallowed_application": 8, "not_application_announcement": 8}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ABatoloco_1852&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ABatoloco_1852&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/Batoloco_1852](https://twstalker.com/Batoloco_1852): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2FBatoloco_1852%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2FBatoloco_1852%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `parsed_empty`、候補0件。

### BIG MAGIC池袋店ポケモンカード公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ABMike_pokemon%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ABMike_pokemon%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補2件。{"diagnostics": {"account_posts": 20, "excluded_product": 1, "not_application_announcement": 5, "tournament_or_result": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ABMike_pokemon&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ABMike_pokemon&ei=UTF-8): `parsed`、候補2件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 32, "tournament_or_result": 1}}
- [https://twstalker.com/BMike_pokemon](https://twstalker.com/BMike_pokemon): `今回未実行・実証なし`、候補0件。
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2FBMike_pokemon%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2FBMike_pokemon%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `今回未実行・実証なし`、候補0件。

### BIG MAGIC池袋店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ABM_ikebukuro%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ABM_ikebukuro%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。
- [https://search.yahoo.co.jp/realtime/search?p=id%3ABM_ikebukuro&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ABM_ikebukuro&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/BM_ikebukuro](https://twstalker.com/BM_ikebukuro): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2FBM_ikebukuro%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2FBM_ikebukuro%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `parsed_empty`、候補0件。

### TCバトロコsatellite渋谷駅前店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_428%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_428%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 8, "not_application_announcement": 7}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_428&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_428&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/batoloco_428](https://twstalker.com/batoloco_428): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fbatoloco_428%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fbatoloco_428%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `parsed_empty`、候補0件。

### POKÉMON CARD LOUNGE公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3APCGL_Shibuya%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3APCGL_Shibuya%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 12, "application_ended": 5, "not_application_announcement": 7}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3APCGL_Shibuya&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3APCGL_Shibuya&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "application_ended": 2, "not_application_announcement": 38}}
- [https://twstalker.com/PCGL_Shibuya](https://twstalker.com/PCGL_Shibuya): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2FPCGL_Shibuya%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2FPCGL_Shibuya%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `parsed_empty`、候補0件。

### TierOne渋谷店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3ATierOneshibuya%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ATierOneshibuya%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed`、候補2件。{"diagnostics": {"account_posts": 5, "application_ended": 1, "not_application_announcement": 2}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3ATierOneshibuya&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3ATierOneshibuya&ei=UTF-8): `parsed`、候補1件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 39}}
- [https://twstalker.com/TierOneshibuya](https://twstalker.com/TierOneshibuya): `今回未実行・実証なし`、候補0件。
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2FTierOneshibuya%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2FTierOneshibuya%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `今回未実行・実証なし`、候補0件。

### TCバトロコ渋谷センター街店公式X Yahooリアルタイム検索

- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_1825%20%E6%8A%BD%E9%81%B8&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_1825%20%E6%8A%BD%E9%81%B8&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 2, "not_application_announcement": 1}}
- [https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_1825&ei=UTF-8](https://search.yahoo.co.jp/realtime/search?p=id%3Abatoloco_1825&ei=UTF-8): `parsed_empty`、候補0件。{"diagnostics": {"account_posts": 40, "not_application_announcement": 40}}
- [https://twstalker.com/batoloco_1825](https://twstalker.com/batoloco_1825): `fetch_failed`、候補0件。{"error": "host_circuit_open"}
- [https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fbatoloco_1825%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp](https://www.bing.com/search?format=rss&q=site%3Ax.com%2Fbatoloco_1825%2Fstatus+%E6%8A%BD%E9%81%B8&setlang=ja-JP&cc=jp): `parsed_empty`、候補0件。
