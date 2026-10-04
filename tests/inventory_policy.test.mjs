import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {loadInventoryPolicy,validateInventoryPolicy,enforceInventoryPolicy,inventoryPolicyIssues,inventoryPolicySummary,inventoryPolicyReport} from '../scripts/inventory_policy.mjs';
import {runInventorySync} from '../scripts/sync_inventory_monitor.mjs';

const NOW=Date.parse('2026-10-04T12:08:00+09:00'),SHA='a'.repeat(40);
const WEBHOOK='https://discord.com/api/webhooks/test-only/not-a-real-credential';

test('公開設定は7弾だけを停止し、指定3商品・プレ値の弾・未来弾を含めない',async()=>{
  const policy=await loadInventoryPolicy();
  assert.deepEqual(policy.pausedProducts.map(p=>p.id).sort(),['gundam-gd02','gundam-gd03','gundam-gd04','gundam-eb01','lorcana-azurite-sea','yugioh-/japan/products/ut01/','yugioh-/japan/products/26lp/'].sort());
  const invalid=structuredClone(policy);invalid.pausedProducts.push(invalid.pausedProducts[0]);
  assert.throws(()=>validateInventoryPolicy(invalid),{code:'notification_policy_invalid'});
  assert.throws(()=>validateInventoryPolicy({version:1,pausedProducts:[]}),{code:'notification_policy_invalid'});
});

test('停止は商品IDで一致し、再同期・再実行でも履歴と手動停止を維持する',async()=>{
  const policy=await loadInventoryPolicy();
  let state={enabled:true,automatic:{enabled:true,products:[]},rules:[
    {id:'exclude',automaticProductId:'gundam-gd02',enabled:true},
    {id:'manual',config:{query:'GD02'},enabled:true},
    {id:'paused',automaticProductId:'gundam-gd01',enabled:false},
    {id:'keep',automaticProductId:'gundam-gd05',enabled:true},
    {id:'future',automaticProductId:'gundam-gd06',enabled:true}
  ],events:[{id:'old-sent',delivery:'sent',receiptId:'kept'}],targets:[{history:[{price:5280}]}]};
  let writes=0;
  const api=async command=>{writes++;assert.equal(command.action,'toggle');assert.equal(command.enabled,false);state.rules.find(r=>r.id===command.id).enabled=false;return structuredClone(state);};
  state=await enforceInventoryPolicy(state,policy,api);
  const before=JSON.stringify(state);
  state=await enforceInventoryPolicy(state,policy,api);assert.equal(writes,1);assert.equal(JSON.stringify(state),before);
  assert.equal(state.rules[1].enabled,true);assert.equal(state.rules[2].enabled,false);assert.equal(state.rules[3].enabled,true);assert.equal(state.rules[4].enabled,true);
  assert.equal(state.events[0].receiptId,'kept');assert.equal(state.targets[0].history[0].price,5280);
  assert.deepEqual(inventoryPolicyIssues(state,policy),[]);
  // 商品を作り直した場合も、変わったルールIDに追従して停止する。
  state.rules[0]={id:'new-rule-id',automaticProductId:'gundam-gd02',enabled:true};
  assert.equal(inventoryPolicyIssues(state,policy)[0].code,'notification_policy_not_applied');
  state=await enforceInventoryPolicy(state,policy,api);assert.equal(writes,2);assert.equal(state.rules[0].enabled,false);
});

test('HTTP成功でも停止設定が反映されていなければ失敗する',async()=>{
  const policy=await loadInventoryPolicy(),state={rules:[{id:'a',automaticProductId:'gundam-gd02',enabled:true}]};
  await assert.rejects(enforceInventoryPolicy(state,policy,async()=>state),{code:'notification_policy_not_applied'});
});

test('実行経路で停止を先に適用し、送信履歴・上限を維持して、読取結果から表示する',async t=>{
  const root=await mkdtemp(join(tmpdir(),'inventory-policy-'));t.after(()=>rm(root,{recursive:true,force:true}));
  await writeFile(join(root,'monitor_state.json'),JSON.stringify({seen_releases:{}}));
  const products=['gundam-gd01','gundam-gd05','pokemon-m6a','gundam-gd02'];
  const pricePolicy={version:1,defaultPercent:105,overrides:{'pokemon-m6a':{percent:200,maxPrice:null}}};
  const state={enabled:true,notificationConfigured:true,lastTick:NOW,lastCompletedAt:NOW,
    discovery:{version:1,stores:{},log:[]},load:{activePages:3,intervalSeconds:60,discoverySeconds:3600},
    automatic:{enabled:true,pricePolicy,lastSync:NOW,products:products.map(id=>({id,name:id,priceStatus:'ready',notificationMaxPrice:id==='pokemon-m6a'?14400:6098,pricePercent:id==='pokemon-m6a'?200:105})),log:[]},
    rules:products.map(id=>({id,automaticProductId:id,enabled:true})),targets:[{id:'history',history:[{price:5280}]}],
    events:[{id:'old-sent',delivery:'sent',receiptId:'receipt-kept',sentAt:NOW-60000},{id:'pending-gd02',ruleId:'gundam-gd02',delivery:'pending',at:NOW}],runs:[]};
  const commands=[];let reads=0;
  const fetcher=async(input,options={})=>{
    const url=String(input);
    if(url.includes('api.github.com'))return Response.json({object:{sha:SHA}});
    if(url.endsWith('/api/health'))return Response.json({version:'0.12.1',commit:SHA});
    if(url.endsWith('/api/monitor')) {
      if(options.method==='POST') {
        const command=JSON.parse(options.body);commands.push(command.action);
        if(command.action==='toggle'){state.rules.find(r=>r.id===command.id).enabled=command.enabled;for(const event of state.events)if(event.ruleId===command.id&&event.delivery==='pending')event.delivery='cancelled';}
        if(command.action==='automatic')assert.equal(state.rules.at(-1).enabled,false);
      } else if(++reads>1)state.lastCompletedAt=NOW+1;
      return Response.json(state);
    }
    throw new Error('unexpected external request'); // 検証のためのDiscord通知を増やさない。
  };
  const options={root,webhook:WEBHOOK,fetcher,now:()=>NOW+100,pause:async()=>{},log:()=>{}};
  assert.equal((await runInventorySync(options)).status,'ok');
  assert.deepEqual(commands,['toggle','automatic']);
  const report=JSON.parse(await readFile(join(root,'inventory_status.json'),'utf8'));
  assert.deepEqual(report.automatic.pricePolicy,pricePolicy);assert.equal(report.events[0].receiptId,'receipt-kept');assert.equal(report.events[1].delivery,'cancelled');assert.equal(report.targets[0].history[0].price,5280);
  assert.equal(report.automatic.products.at(-1).notificationStatus,'相場確認により停止');
  const markdown=await readFile(join(root,'inventory_status.md'),'utf8');assert.match(markdown,/登録：4弾／監視有効：3弾/);assert.match(markdown,/通知設定/);assert.match(markdown,/相場確認により停止/);assert(!markdown.includes(WEBHOOK));
  const summary=inventoryPolicySummary({...state,enabled:false},await loadInventoryPolicy(),NOW);
  assert(summary.products.every(p=>!p.monitoringEnabled));assert.match(inventoryPolicyReport(summary).join('\n'),/ブラウザ/);
  commands.length=0;reads=0;state.lastCompletedAt=NOW;
  assert.equal((await runInventorySync(options)).status,'ok');assert.deepEqual(commands,['automatic']);
});
