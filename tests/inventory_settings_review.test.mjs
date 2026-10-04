import test from 'node:test';
import assert from 'node:assert/strict';
import {applySettingRequest} from '../scripts/apply_inventory_setting.mjs';
import {reviewInventoryMarket,inventoryCadenceSummary} from '../scripts/inventory_review.mjs';
import {enforceInventoryPolicy} from '../scripts/inventory_policy.mjs';
const NOW=Date.parse('2026-10-04T13:00:00+09:00');
const policy={version:1,reviewedAt:new Date(NOW).toISOString(),pausedProducts:[]};
test('所有者の認証済み変更だけ保存し、再同期でも上限・停止・履歴を維持する',async()=>{
  const event={repository:{owner:{login:'owner'}},issue:{user:{login:'owner'},number:7,title:'[在庫設定] 通知条件の変更',body:'```json\n'+JSON.stringify({version:1,productId:'p',enabled:false,percent:105,maxPrice:5000})+'\n```'}};
  const next=applySettingRequest(policy,event,[{id:'p'}],NOW);
  assert.throws(()=>applySettingRequest(policy,{...event,issue:{...event.issue,user:{login:'stranger'}}},[{id:'p'}]));
  let state={rules:[{id:'r',automaticProductId:'p',enabled:true,config:{priceLimit:'105',maxPrice:null}}],events:[{id:'old',delivery:'sent'}]};let calls=0;
  const api=async c=>{calls++;if(c.action==='toggle')state.rules[0].enabled=c.enabled;else Object.assign(state.rules[0].config,{priceLimit:c.priceLimit,maxPrice:c.maxPrice});return structuredClone(state);};
  state=await enforceInventoryPolicy(state,next,api);state=await enforceInventoryPolicy(state,next,api);
  assert.equal(calls,2);assert.equal(state.rules[0].config.maxPrice,5000);assert.equal(state.events[0].id,'old');
});
test('一瞬の安値や取得失敗を除外候補とせず、週1回だけ継続在庫を確認する',()=>{
  const product={id:'p',name:'BOX',boxPrice:6000},state={automatic:{products:[product]},rules:[{id:'r',automaticProductId:'p'}],targets:[{ruleIds:['r'],url:'https://example.com/product',history:[{kind:'observation',stock:'in_stock',price:6000,at:NOW-86400000,lastAt:NOW,samples:4}]}],events:[]};
  const review=reviewInventoryMarket(state,policy,{},NOW);assert.equal(review.products[0].status,'pause_candidate');
  state.targets[0].history.push({kind:'error',at:NOW});assert.equal(reviewInventoryMarket(state,policy,{},NOW).products[0].status,'insufficient_evidence');
  assert.equal(reviewInventoryMarket(state,policy,review,NOW+100),review);
  assert.equal(inventoryCadenceSummary(state,NOW).notificationDelay.samples,0);
});
