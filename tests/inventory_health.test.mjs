import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,rm,readdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {assessInventory,incidentDecision} from '../scripts/inventory_health.mjs';
import {runInventorySync} from '../scripts/sync_inventory_monitor.mjs';
// 数字のWebhook識別子を持たない、実際には送信できないテスト専用URL。
const NOW=1791069600000,SHA='a'.repeat(40),WEBHOOK='https://discord.com/api/webhooks/test-only/not-a-real-credential';
function state() {return {enabled:true,discovery:{version:1,stores:{},log:[]},notificationConfigured:true,lastTick:NOW,lastCompletedAt:NOW,load:{activePages:3,intervalSeconds:60,discoverySeconds:3600},automatic:{pricePolicy:{version:1,defaultPercent:105},enabled:true,lastSync:NOW,products:['gundam-gd01','gundam-gd05','pokemon-m6a'].map(id=>({id,name:id})),log:[]},rules:[{}],targets:[{}],events:[{delivery:'sent',sentAt:NOW-600000}],runs:[]};}
test('過去の送信成功が残っていても、新しい失敗・取消・停止を検出する',()=>{
  const s=state();s.events.push({delivery:'cancelled',error:'送信失敗',at:NOW-60000},{delivery:'pending',error:'送信失敗',at:NOW-30000});
  assert(assessInventory(s,NOW).some(x=>x.code==='delivery_failing'));
  s.events=[];assert.deepEqual(assessInventory(s,NOW),[]); // 新着ゼロは異常ではない。
  s.lastCompletedAt=NOW-3600000;assert(assessInventory(s,NOW).some(x=>x.code==='monitor_stalled'));
  s.enabled=false;assert.deepEqual(assessInventory(s,NOW),[]);
});
test('同一障害は連投せず、6時間後の再報と復旧を区別する',()=>{
  const issue=[{code:'delivery_failing'}],previous={fingerprint:'delivery_failing',deliveredAt:NOW-60000,lastAttemptAt:NOW-60000};
  assert.equal(incidentDecision(previous,issue,NOW),null);
  assert.equal(incidentDecision(previous,issue,NOW+7*3600000).kind,'alert');
  assert.equal(incidentDecision(previous,[],NOW+20*60000).kind,'recovery');
  assert.equal(incidentDecision({},[],NOW),null);
});
test('復旧時に旧通知を取り消しても、取消時刻を新たな送信失敗にしない',()=>{
  const s=state();
  s.events.push(...[1,2].map(n=>({id:String(n),delivery:'cancelled',error:'Discord送信失敗',at:NOW-6*3600000,cancelledAt:NOW,cancelReason:'stale'})));
  assert.deepEqual(assessInventory(s,NOW),[]);
  for(const event of s.events.filter(e=>e.error))event.lastFailureAt=NOW-1000;
  assert(assessInventory(s,NOW).some(x=>x.code==='delivery_failing')); // 本当に新しく失敗したものは検出
});
test('復旧は障害通知直後でも一度だけ送れ、復旧の送信失敗は連投しない',()=>{
  const previous={kind:'alert',fingerprint:'storage_quota',delivery:'sent',deliveredAt:NOW-1000,lastAttemptAt:NOW-1000};
  assert.equal(incidentDecision(previous,[],NOW).kind,'recovery');
  assert.equal(incidentDecision({...previous,fingerprint:''},[],NOW),null);
  assert.equal(incidentDecision({...previous,kind:'recovery',delivery:'failed'},[],NOW),null);
});
test('監視への接続失敗でも異常ログと外部通知を残し、古い正常表示にしない',async t=>{
  const root=await mkdtemp(join(tmpdir(),'inventory-outage-'));t.after(()=>rm(root,{recursive:true,force:true}));
  await writeFile(join(root,'inventory_status.md'),'以前の在庫記録');
  let posts=0,reads=0;
  const fetcher=async input=>{const url=String(input);if(url.includes('api.github.com'))return Response.json({object:{sha:SHA}});if(url.endsWith('/api/health'))return Response.json({version:'0.12.0',commit:SHA});if(url.endsWith('/api/monitor')){reads++;return Response.json({failure:{code:'storage_quota'}},{status:503});}if(url.startsWith('https://discord.com')){posts++;return Response.json({id:'message'});}throw new Error('unexpected request');};
  const options={root,webhook:WEBHOOK,fetcher,now:()=>NOW,pause:async()=>{},log:()=>{}};
  const health=await runInventorySync(options);assert.equal(health.status,'degraded');assert.equal(health.issues[0].code,'storage_quota');assert.equal(reads,3);assert.equal(posts,1);
  await runInventorySync(options);assert.equal(posts,1);
  assert.match(await readFile(join(root,'inventory_status.md'),'utf8'),/異常あり/);
  for(const file of await readdir(root)){const text=await readFile(join(root,file),'utf8');assert(!text.includes(WEBHOOK));assert(!text.includes('not-a-real-credential'));}
});
test('復旧は新しい巡回完了を待ち、商品・送信済み履歴を維持する',async t=>{
  const root=await mkdtemp(join(tmpdir(),'inventory-recovery-'));t.after(()=>rm(root,{recursive:true,force:true}));
  await writeFile(join(root,'monitor_state.json'),JSON.stringify({seen_releases:{}}));
  await writeFile(join(root,'inventory_incident.json'),JSON.stringify({fingerprint:'storage_quota',deliveredAt:NOW-3600000,lastAttemptAt:NOW-3600000}));
  let reads=0,posts=0;const s=state();
  const fetcher=async(input,options={})=>{const url=String(input);if(url.includes('api.github.com'))return Response.json({object:{sha:SHA}});if(url.endsWith('/api/health'))return Response.json({version:'0.12.0',commit:SHA});if(url.endsWith('/api/monitor')){if(options.method==='GET')reads++;return Response.json({...s,lastCompletedAt:reads>1?NOW+1:NOW});}if(url.startsWith('https://discord.com')){posts++;return Response.json({id:'message'});}throw new Error('unexpected request');};
  const health=await runInventorySync({root,webhook:WEBHOOK,fetcher,now:()=>NOW+100,pause:async()=>{},log:()=>{}});
  assert.equal(health.status,'ok');assert.equal(posts,1);assert(reads>=2);
  const report=JSON.parse(await readFile(join(root,'inventory_status.json'),'utf8'));assert.equal(report.events.length,1);assert.equal(report.events[0].delivery,'sent');assert.equal(report.automatic.pricePolicy.defaultPercent,105);assert.match(await readFile(join(root,'inventory_status.md'),'utf8'),/定価の105%以下/);
  assert.equal(JSON.parse(await readFile(join(root,'inventory_incident.json'),'utf8')).fingerprint,'');
});

for(const endpoint of ['github','health'])for(const failure of ['transport','http','json']) {
  test(`本番情報の一時失敗から回復し、実際の巡回完了を確認する ${endpoint}/${failure}`,async t=>{
    const root=await mkdtemp(join(tmpdir(),'inventory-metadata-'));t.after(()=>rm(root,{recursive:true,force:true}));
    await writeFile(join(root,'monitor_state.json'),JSON.stringify({seen_releases:{}}));
    let attempts=0,reads=0,posts=0;const signals=[];
    const fetcher=async(input,options={})=>{
      const url=String(input),isRef=url.includes('api.github.com'),isHealth=url.endsWith('/api/health');
      if((endpoint==='github'&&isRef)||(endpoint==='health'&&isHealth)) {
        signals.push(options.signal);
        if(++attempts===1) {
          if(failure==='transport')throw new TypeError('fetch failed');
          return new Response('temporarily unavailable',{status:failure==='http'?502:200});
        }
      }
      if(isRef)return Response.json({object:{sha:SHA}});
      if(isHealth)return Response.json({version:'0.13.0',commit:SHA});
      if(url.endsWith('/api/monitor')){if(options.method==='GET')reads++;return Response.json({...state(),lastCompletedAt:reads>1?NOW+1:NOW});}
      if(url.startsWith('https://discord.com')){posts++;return Response.json({id:'message'});}
      throw new Error('unexpected request');
    };
    const health=await runInventorySync({root,webhook:WEBHOOK,fetcher,now:()=>NOW+100,pause:async()=>{},log:()=>{}});
    assert.equal(health.status,'ok');assert.equal(attempts,2);assert(reads>=2);assert.equal(posts,0);
    assert.notEqual(signals[0],signals[1]); // 再試行は、失効したタイムアウトを使い回さない。
  });
}

for(const [status,expectedAttempts] of [[503,3],[403,1],[429,1]]) {
  test(`本番情報が読めない場合は異常を保持し、設定を変えない HTTP ${status}`,async t=>{
    const root=await mkdtemp(join(tmpdir(),'inventory-metadata-failure-'));t.after(()=>rm(root,{recursive:true,force:true}));
    let attempts=0,commands=0;
    const fetcher=async(input,options={})=>{
      const url=String(input);
      if(url.includes('api.github.com')){attempts++;return new Response('',{status});}
      if(url.endsWith('/api/monitor'))commands++;
      if(url.startsWith('https://discord.com'))return Response.json({id:'message'});
      throw new Error('must not change configuration');
    };
    const health=await runInventorySync({root,webhook:WEBHOOK,fetcher,now:()=>NOW,pause:async()=>{},log:()=>{}});
    assert.equal(health.status,'degraded');assert.equal(attempts,expectedAttempts);assert.equal(commands,0);
    assert.equal(health.issues[0].code,'deployment_check_failed');assert.equal(health.issues[0].httpStatus,status);
  });
}

test('通信が正常でも本当に古い稼働版は正常扱いにせず、設定を変えない',async t=>{
  const root=await mkdtemp(join(tmpdir(),'inventory-old-deployment-'));t.after(()=>rm(root,{recursive:true,force:true}));
  let healthReads=0,commands=0;
  const fetcher=async input=>{
    const url=String(input);
    if(url.includes('api.github.com'))return Response.json({object:{sha:SHA}});
    if(url.endsWith('/api/health')){healthReads++;return Response.json({version:'0.11.0',commit:'b'.repeat(40)});}
    if(url.endsWith('/api/monitor'))commands++;
    if(url.startsWith('https://discord.com'))return Response.json({id:'message'});
    throw new Error('must not change configuration');
  };
  const health=await runInventorySync({root,webhook:WEBHOOK,fetcher,now:()=>NOW,pause:async()=>{},log:()=>{}});
  assert.equal(health.status,'degraded');assert.equal(health.issues[0].code,'deployment_mismatch');
  assert.equal(healthReads,12);assert.equal(commands,0);
});
