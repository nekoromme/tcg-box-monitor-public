import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseOfficialPrice,collectInventoryPrices,observedBoxCount,boxCount,productIdentity} from '../scripts/inventory_prices.mjs';
const fixtures=JSON.parse(readFileSync(new URL('./fixtures/inventory-prices-2026-10-04.json',import.meta.url)));
const NOW=Date.parse('2026-10-04T13:30:00+09:00');
test('2026年10月4日の公式仕様欄から税込単価と商品ごとの入数を読み取る',()=>{
  const expected={'onepiece-eb-04':[220,null],'onepiece-op-18':[240,null],'onepiece-eb-05':[240,null],'gundam-gd06':[250,null],'dragonball-fb08':[220,null],'yugioh-/japan/products/yac1/':[396,15],'yugioh-/japan/products/26lp/':[396,10],'yugioh-/japan/products/ut01/':[396,15],'yugioh-/japan/products/betb/':[198,30],'yugioh-/japan/products/rv02/':[264,15],'yugioh-/japan/products/imph/':[198,30]};
  for(const f of fixtures) {
    const result=parseOfficialPrice(f.product,f.html,f.product.officialUrl,NOW),e=expected[f.product.id];
    if(e){assert.equal(result.packPrice,e[0],f.product.id);assert.equal(result.packsPerBox,e[1],f.product.id);}
    else if(f.product.game==='lorcana')assert.equal(result.boxPrice,5280,f.product.id);
    else assert.equal(result.status,'price_unpublished',f.product.id);
  }
});
test('入数はその商品の新品BOXだけに結びつけ、別ゲーム・カートン・矛盾を除外する',()=>{
  const product={id:'onepiece-eb-04',game:'onepiece',query:'EB-04',name:'EGGHEAD CRISIS'},title='ワンピース EGGHEAD CRISIS EB-04 (1BOX・24パック入)';
  assert.equal(boxCount(title),24);assert.equal(boxCount('1パック6枚入り'),null);
  assert.equal(productIdentity(product,'ヴァンガード EB04 BOX (12パック)'),false);
  const target={ruleIds:['rule'],lastGood:{title,detailChecked:true},lastGoodAt:NOW,url:'https://www.masters-square.com/product/92917'};
  const s={rules:[{id:'rule',automaticProductId:product.id}],targets:[target]};
  assert.equal(observedBoxCount(product,s,NOW).count,24);
  s.targets.push({...target,lastGood:{title:title.replace('24パック','12パック'),detailChecked:true}});
  assert.equal(observedBoxCount(product,s,NOW),null);
});
test('未発表から価格公開へ自動移行し、通信失敗でも確認済み価格と履歴を保持する',async()=>{
  const f=fixtures.find(f=>f.product.id==='yugioh-/japan/products/yac1/');
  const state={automatic:{products:[f.product]},rules:[],targets:[]};let requests=0;
  const fetcher=async()=>{requests++;return new Response(f.html);};
  const first=await collectInventoryPrices(state,{}, {fetcher,now:NOW});
  assert.equal(first.records[f.product.id].boxPrice,5940);assert.equal(first.records[f.product.id].status,'confirmed');
  const cached=await collectInventoryPrices(state,first,{fetcher,now:NOW+3600000});assert.equal(requests,1);assert.deepEqual(cached.records,first.records);
  const failed=await collectInventoryPrices(state,first,{fetcher:async()=>new Response('',{status:503}),now:NOW+8*86400000});
  assert.equal(failed.records[f.product.id].boxPrice,5940);assert.equal(failed.records[f.product.id].checkedAt,NOW);assert.equal(failed.records[f.product.id].lastAttemptStatus,'fetch_failed');
  const pending=await collectInventoryPrices(state,{}, {fetcher:async()=>new Response(f.html.replace('396円','未定')),now:NOW});
  assert.equal(pending.records[f.product.id].boxPrice,null);
  const published=await collectInventoryPrices(state,pending,{fetcher,now:NOW+6*3600000});assert.equal(published.records[f.product.id].boxPrice,5940);
});
test('他商品タイトル・別ホスト・税込不明を採用しない',()=>{
  const f=fixtures.find(f=>f.product.id==='onepiece-op-18');
  assert.equal(parseOfficialPrice(f.product,f.html,'https://example.com/',NOW).status,'source_rejected');
  assert.equal(parseOfficialPrice(f.product,f.html.replace(/神の支配/g,'別商品').replace(/OP-18/g,'OP-19'),f.product.officialUrl,NOW).status,'identity_unconfirmed');
  assert.equal(parseOfficialPrice(f.product,f.html.replace(/税込/g,'税別'),f.product.officialUrl,NOW).status,'price_unpublished');
});
