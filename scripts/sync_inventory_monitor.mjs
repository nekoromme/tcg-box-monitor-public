// 既存のDiscord秘密情報を公開ファイルへ出さず、在庫監視Workerへ接続する。
// 商品の巡回はWorkerが続ける。この処理は初期設定・新弾同期・ログ保存だけ。
import {createHmac} from 'node:crypto';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
const base='https://tcg-cross-search.purplepearl-v.workers.dev';
const webhook=process.env.DISCORD_WEBHOOK_URL;
if(!webhook)throw new Error('DISCORD_WEBHOOK_URLが未設定です');
const key=createHmac('sha256',webhook).update('tcg-cross-search:automatic-inventory:v1').digest('hex');
// 派生した鍵もGitHubのログでマスク。URL・レポート・成果物には含めない。
console.log(`::add-mask::${key}`);
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function api(body) {
  const response=await fetch(base+'/api/monitor',{method:body?'POST':'GET',redirect:'error',signal:AbortSignal.timeout(90000),headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
  if(!response.ok)throw new Error(`在庫監視への接続失敗 HTTP ${response.status}`);
  return response.json();
}
// 自動デプロイ完了前の起動では登録しない。古い版へ何度も操作しない。
let deployed=false;
for(let n=0;n<12;n++) {
  const r=await fetch(base+'/api/health',{signal:AbortSignal.timeout(15000)});
  const health=await r.json();
  if(health.version && !['0.9.0','0.9.1','0.10.0'].includes(health.version)){deployed=true;break;}
  if(n<11)await delay(15000);
}
if(!deployed)throw new Error('在庫監視v0.10.1のデプロイ完了を確認できません');
let state=await api();
const previousCatalogFailure=state.automatic?.lastFailure;
const initial=!state.automatic || state.rules.length===0;
const root=process.env.INVENTORY_LOG_DIR||'.monitor-state';
const source=JSON.parse(await readFile(join(root,'monitor_state.json'),'utf8'));
// 公式商品の直近80記録だけ。抽選・通知・画像履歴の6MB全体をWorkerへ送らない。
const releases=Object.fromEntries(Object.entries(source.seen_releases||{}).filter(([,r])=>r.source_tier==='official').sort((a,b)=>String(b[1].release_date||b[1].release_month||'').localeCompare(String(a[1].release_date||a[1].release_month||''))).slice(0,80));
await writeFile(join(root,'inventory_releases.json'),JSON.stringify({seen_releases:releases,recordedAt:source.last_run_summary?.recorded_at})+'\n');
state=await api({action:'settings',webhook});
state=await api({action:'automatic',releases});
// 失敗時も下で状態を保存する。例外でログ保存より先に終了しない。

// 最低限の3商品は初回に数店舗から商品URLを渡し、全店検索の順番待ちを短くする。
// 在庫値は信頼せず、Workerが商品詳細を再確認してから通知する。
const seedLog=[];
if(initial || state.targets.length===0) {
  for(const p of state.automatic.products.filter(p=>p.pinned)) {
    for(const store of ['mediaworld','suns','cardwiz']) {
      try {
        const query=new URLSearchParams({store,q:p.query,sealed:'1',refresh:'1'});
        const response=await fetch(`${base}/api/search?${query}`,{signal:AbortSignal.timeout(35000)});
        const result=await response.json();
        seedLog.push({at:Date.now(),query:p.query,store,status:result.status||response.status,found:result.results?.length||0,error:result.error||''});
        if(result.results?.length)state=await api({action:'automatic-seeds',seeds:result.results.map(r=>({...r,storeId:store}))});
      }catch{seedLog.push({at:Date.now(),query:p.query,store,error:'初回の掲載検索を取得できず。定期検索で再試行'});}
    }
  }
}
// 初回だけ、画面を閉じた状態での定期起動・実通知結果を待つ。
if(initial || !state.events.some(e=>e.delivery==='sent'))for(let n=0;n<12;n++) {
  state=await api();
  if(state.lastTick && state.targets.some(t=>t.lastGoodAt) && state.events.some(e=>e.delivery==='sent'))break;
  await delay(15000);
}
state=await api();
await mkdir(join(root,'inventory-logs'),{recursive:true});
const deliveries=Object.fromEntries(['sent','pending','failed','cancelled','screen'].map(status=>[status,state.events.filter(e=>e.delivery===status).length]));
const report={generatedAt:Date.now(),enabled:state.enabled,notificationConfigured:state.notificationConfigured,lastTick:state.lastTick,load:state.load,error:state.error,deliveries,automatic:{enabled:state.automatic.enabled,lastSync:state.automatic.lastSync,nextSync:state.automatic.nextSync,error:state.automatic.error,lastFailure:state.automatic.lastFailure||previousCatalogFailure,products:state.automatic.products,log:state.automatic.log},rules:state.rules,targets:state.targets,events:state.events,runs:state.runs||[],seedLog};
await writeFile(join(root,'inventory_status.json'),JSON.stringify(report,null,2)+'\n');
const day=new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Tokyo'}),logPath=join(root,'inventory-logs',`${day}.jsonl`);
let old=[];try{old=(await readFile(logPath,'utf8')).trim().split('\n').filter(Boolean).map(x=>JSON.parse(x));}catch{}
const seen=new Set(old.map(x=>x.at));
const rows=[...old,...report.runs.filter(x=>!seen.has(x.at))].sort((a,b)=>a.at-b.at);
await writeFile(logPath,rows.map(x=>JSON.stringify(x)).join('\n')+'\n');
const time=n=>n?new Date(n).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}):'未確認';
const safe=s=>String(s||'').replace(/[\r\n|<>]/g,' ');
const lines=['# カード在庫監視の稼働状況','',`ログ保存：${time(report.generatedAt)}（日本時間）`,`最終巡回：${time(report.lastTick)}／Discord通知：${report.notificationConfigured?'設定済み':'未設定'}`,`監視：${state.automatic.products.length}弾・${state.targets.length}商品ページ／直近通知の送信済み：${state.events.filter(e=>e.delivery==='sent').length}件`,'','価格上限なし。通常の日本語版BOXを対象に、在庫・予約を価格付きで通知。取得失敗は売り切れにしません。',`商品確認は約${Math.ceil(state.load.intervalSeconds/60)}分以上（指定商品は優先）。掲載検索は各商品・店舗につき約${Math.ceil(state.load.discoverySeconds/3600)}時間以上。負荷や通信制限で延びます。`,'','|作品|商品|発売日|固定|','|---|---|---|---|',...state.automatic.products.map(p=>`|${p.game}|${safe(p.name)}|${p.releaseDate}|${p.pinned?'固定':''}|`),'','詳細な商品別の価格・在庫・取得失敗・通知結果は [inventory_status.json](inventory_status.json)、巡回ログは [inventory-logs](inventory-logs) を参照。',`新弾更新：${time(state.automatic.lastSync)}／${safe(state.automatic.error||'正常')}`];
await writeFile(join(root,'inventory_status.md'),lines.join('\n')+'\n');
if(process.env.GITHUB_STEP_SUMMARY)await writeFile(process.env.GITHUB_STEP_SUMMARY,lines.join('\n')+'\n');
console.log(JSON.stringify({event:'inventory_sync',products:state.automatic.products.length,targets:state.targets.length,lastTick:state.lastTick,checked:state.targets.filter(t=>t.lastGoodAt).length,sent:state.events.filter(e=>e.delivery==='sent').length,notificationConfigured:state.notificationConfigured}));
console.log(JSON.stringify({event:'inventory_delivery_health',deliveries,errors:state.events.filter(e=>['failed','pending'].includes(e.delivery)&&e.error).map(e=>({id:e.id,kind:e.kind||'stock',error:e.error,attempts:e.attempts})),catalogFailure:report.automatic.lastFailure}));
if(!state.notificationConfigured || !state.automatic.products.some(p=>p.id==='gundam-gd01') || !state.automatic.products.some(p=>p.id==='gundam-gd05') || !state.automatic.products.some(p=>p.id==='pokemon-m6a'))throw new Error('必須監視対象または通知設定を確認できません');
if(state.automatic.error)throw new Error(state.automatic.error);
if(!deliveries.sent && state.events.some(e=>['failed','pending'].includes(e.delivery)&&e.error))throw new Error('Discord通知をまだ一件も送信できていません。保存した通知結果を確認してください');
if(state.enabled && state.lastTick && Date.now()-state.lastTick>15*60000)throw new Error('15分以上巡回が止まっています');
