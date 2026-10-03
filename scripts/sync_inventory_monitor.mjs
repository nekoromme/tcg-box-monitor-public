// 常時巡回はWorkerが担当。ここでは新弾同期・稼働確認・異常通知・ログ保存を行う。
// Webhookと認証鍵は実行中だけ使い、公開される状態ファイルには含めない。
import {createHmac} from 'node:crypto';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {assessInventory,incidentDecision,versionAtLeast} from './inventory_health.mjs';
const BASE='https://tcg-cross-search.purplepearl-v.workers.dev';
const STATUS_URL='https://github.com/nekoromme/tcg-box-monitor-public/blob/monitor-state/inventory_status.md';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const time=n=>n?new Date(n).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}):'未確認';
const safe=s=>String(s||'').replace(/[\r\n|<>]/g,' ');
async function readJson(path,fallback=null){try{return JSON.parse(await readFile(path,'utf8'));}catch{return fallback;}}

export async function runInventorySync({root=process.env.INVENTORY_LOG_DIR||'.monitor-state',webhook=process.env.DISCORD_WEBHOOK_URL,fetcher=fetch,now=Date.now,pause=delay,log=console.log,summary=process.env.GITHUB_STEP_SUMMARY}={}) {
  await mkdir(root,{recursive:true});
  const key=webhook?createHmac('sha256',webhook).update('tcg-cross-search:automatic-inventory:v1').digest('hex'):'';
  if(key)log(`::add-mask::${key}`);
  let state,deployment={},issues=[],stage='configuration';
  // 同期操作は重複しても同じ対象へ収束するため、通信の一時失敗を3回まで再試行する。
  async function api(body) {
    let last;
    for(let n=0;n<3;n++) {
      try {
        const response=await fetcher(BASE+'/api/monitor',{method:body?'POST':'GET',redirect:'error',signal:AbortSignal.timeout(90000),headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
        let data;try{data=await response.json();}catch{}
        if(response.ok&&data)return data;
        const backend=data?.failure?.code;
        const limitTerms=(Array.isArray(data?.failure?.limitTerms)?data.failure.limitTerms:[]).filter(x=>['daily','rows','written','writes','reads','duration','requests','CPU','storage','database','quota','limit'].includes(x));
        last=Object.assign(new Error(`監視への接続失敗 HTTP ${response.status}`),{status:response.status,backend:['storage_quota','storage_data','runtime_limit','monitor_unavailable'].includes(backend)?backend:null,limitTerms});
        if(response.status<500&&response.status!==429)break;
      }catch{last=new Error('監視への通信に失敗');}
      if(n<2)await pause(5000*(n+1));
    }
    throw last;
  }
  try {
    if(!webhook)throw new Error('通知先が未設定');
    stage='deployment';
    const ref=await fetcher('https://api.github.com/repos/nekoromme/tcg-cross-search/git/ref/heads/main',{redirect:'error',headers:{Accept:'application/vnd.github+json','User-Agent':'TCGInventoryHealth/1.0'},signal:AbortSignal.timeout(15000)});
    if(!ref.ok)throw new Error('運用コードの変更番号を確認できない');
    const expectedCommit=(await ref.json()).object?.sha;
    if(!/^[a-f0-9]{40}$/.test(expectedCommit||''))throw new Error('変更番号の形式が不正');
    // 公開中の数分だけ待つ。旧版のままなら設定を触らず、外部から異常を知らせる。
    for(let n=0;n<12;n++) {
      const response=await fetcher(BASE+'/api/health',{redirect:'error',signal:AbortSignal.timeout(15000)});
      const health=await response.json();deployment={version:health.version,commit:health.commit,expectedCommit,deployedAt:health.deployedAt};
      if(versionAtLeast(health.version)&&health.commit===expectedCommit)break;
      if(n<11)await pause(15000);
    }
    if(!versionAtLeast(deployment.version)||deployment.commit!==expectedCommit)throw Object.assign(new Error('本番の稼働版が最新の修正版と一致しない'),{code:'deployment_mismatch'});
    stage='read-state';state=await api();
    const beforeCompleted=state.lastCompletedAt||state.lastTick||0;
    const initial=!state.automatic||state.rules.length===0;
    const source=await readJson(join(root,'monitor_state.json'));
    if(!source)throw new Error('公式発売情報の保存ファイルを確認できない');
    const releases=Object.fromEntries(Object.entries(source.seen_releases||{}).filter(([,r])=>r.source_tier==='official').sort((a,b)=>String(b[1].release_date||b[1].release_month||'').localeCompare(String(a[1].release_date||a[1].release_month||''))).slice(0,80));
    await writeFile(join(root,'inventory_releases.json'),JSON.stringify({seen_releases:releases,recordedAt:source.last_run_summary?.recorded_at})+'\n');
    stage='synchronize';
    if(!state.notificationConfigured)state=await api({action:'settings',webhook});
    state=await api({action:'automatic',releases}); // 停止した目覚ましも、既存の有効設定に沿って再設定する。
    const seedLog=[];
    if(initial||state.targets.length===0)for(const p of state.automatic.products.filter(p=>p.pinned))for(const store of ['mediaworld','suns','cardwiz']) {
      try {
        const query=new URLSearchParams({store,q:p.query,sealed:'1',refresh:'1'});
        const response=await fetcher(`${BASE}/api/search?${query}`,{signal:AbortSignal.timeout(35000)}),result=await response.json();
        seedLog.push({at:now(),query:p.query,store,status:result.status||response.status,found:result.results?.length||0});
        if(result.results?.length)state=await api({action:'automatic-seeds',seeds:result.results.map(r=>({...r,storeId:store}))});
      }catch{seedLog.push({at:now(),query:p.query,store,error:'初回検索を取得できず。定期検索で再試行'});}
    }
    // 起動の予約だけで回復としない。各実行で新しい巡回の完了を実際に待つ。
    stage='verify-tick';
    if(state.enabled)for(let n=0;n<12;n++) {
      state=await api();
      if((state.lastCompletedAt||0)>beforeCompleted)break;
      if(n<11)await pause(15000);
    }
    state=await api();issues=assessInventory(state,now());
    if(state.enabled&&(state.lastCompletedAt||0)<=beforeCompleted)issues.push({code:'tick_not_advanced',message:'再開後の巡回完了を確認できない'});
    const pinned=['gundam-gd01','gundam-gd05','pokemon-m6a'];
    if(!pinned.every(id=>state.automatic.products.some(p=>p.id===id)))issues.push({code:'required_products_missing',message:'指定3商品の監視条件が欠けている'});
    const deliveries=Object.fromEntries(['sent','pending','failed','cancelled','screen'].map(status=>[status,state.events.filter(e=>e.delivery===status).length]));
    const report={generatedAt:now(),deployment,enabled:state.enabled,notificationConfigured:state.notificationConfigured,lastTick:state.lastTick,lastCompletedAt:state.lastCompletedAt,load:state.load,error:state.error,lastFailure:state.lastFailure,storage:state.storage,deliveryHealth:state.deliveryHealth,deliveries,automatic:{enabled:state.automatic.enabled,lastSync:state.automatic.lastSync,nextSync:state.automatic.nextSync,error:state.automatic.error,lastFailure:state.automatic.lastFailure,products:state.automatic.products,log:state.automatic.log},rules:state.rules,targets:state.targets,events:state.events,runs:state.runs||[],seedLog};
    await writeFile(join(root,'inventory_status.json'),JSON.stringify(report,null,2)+'\n');
    await mkdir(join(root,'inventory-logs'),{recursive:true});
    const day=new Date(now()).toLocaleDateString('sv-SE',{timeZone:'Asia/Tokyo'}),logPath=join(root,'inventory-logs',`${day}.jsonl`);
    let old=[];try{old=(await readFile(logPath,'utf8')).trim().split('\n').filter(Boolean).map(x=>JSON.parse(x));}catch{}
    const seen=new Set(old.map(x=>x.at)),rows=[...old,...report.runs.filter(x=>!seen.has(x.at))].sort((a,b)=>a.at-b.at);
    await writeFile(logPath,rows.map(x=>JSON.stringify(x)).join('\n')+'\n');
    const lines=['# カード在庫監視の稼働状況','',`ログ保存：${time(report.generatedAt)}（日本時間）`,`最終巡回完了：${time(report.lastCompletedAt)}／Discord通知：${report.notificationConfigured?'設定済み':'未設定'}`,`監視：${state.automatic.products.length}弾・${state.load.activePages}有効商品ページ／保存期間中の送信成功：${deliveries.sent}件`,`直近の通知成功：${time(state.deliveryHealth?.lastSuccessAt)}／連続失敗：${state.deliveryHealth?.consecutiveFailures||0}件`, `稼働版：${deployment.version}／${deployment.commit}`,'','価格上限なし。通常の日本語版BOXを対象に、在庫・予約を価格付きで通知。取得失敗は売り切れにしません。',`商品確認は約${Math.ceil(state.load.intervalSeconds/60)}分以上（指定商品は優先）。掲載検索は商品・店舗ごと約${Math.ceil(state.load.discoverySeconds/3600)}時間以上。通信制限で延びます。`,'','|作品|商品|発売日|固定|','|---|---|---|---|',...state.automatic.products.map(p=>`|${p.game}|${safe(p.name)}|${p.releaseDate}|${p.pinned?'固定':''}|`),'','商品別の価格・在庫・通知結果は [inventory_status.json](inventory_status.json)、稼働判定は [inventory_health.json](inventory_health.json)、巡回履歴は [inventory-logs](inventory-logs) を参照。',`新弾更新：${time(state.automatic.lastSync)}／${safe(state.automatic.error||'正常')}`];
    await writeFile(join(root,'inventory_status.md'),lines.join('\n')+'\n');
  }catch(error) {
    // 接続前に失敗しても、古いログを最新正常に見せない。秘密を含む例外本文は出さない。
    const code=error?.backend||error?.code||(stage==='deployment'?'deployment_check_failed':'monitor_connection_failed');
    const known=new Set(['storage_quota','storage_data','runtime_limit','monitor_unavailable','deployment_mismatch','deployment_check_failed','monitor_connection_failed']);
    issues=[{code:known.has(code)?code:'monitor_connection_failed',message:stage==='deployment'?'本番の修正版・変更番号を確認できない':`監視との接続・確認に失敗${error?.status?`（HTTP ${error.status}）`:''}`,stage,...(error?.status?{httpStatus:error.status}:{}),...(error?.limitTerms?.length?{limitTerms:error.limitTerms}:{})}];
  }
  const health={checkedAt:now(),status:issues.length?'degraded':state?.enabled===false?'paused':'ok',issues,deployment,lastCompletedAt:state?.lastCompletedAt||null};
  await writeFile(join(root,'inventory_health.json'),JSON.stringify(health,null,2)+'\n');
  let markdown='';try{markdown=await readFile(join(root,'inventory_status.md'),'utf8');}catch{}
  markdown=markdown.replace(/^<!-- inventory-health -->[\s\S]*?<!-- \/inventory-health -->\n*/,'');
  const banner=`<!-- inventory-health -->\n> 稼働確認：${issues.length?'異常あり':health.status==='paused'?'設定により停止中':'正常'}（${time(health.checkedAt)} 日本時間）${issues.length?'\n> '+issues.map(i=>i.message).join('／')+'。以下の在庫記録は最終取得時点のもの。':''}\n<!-- /inventory-health -->\n\n`;
  await writeFile(join(root,'inventory_status.md'),banner+markdown);
  if(summary)await writeFile(summary,banner+markdown);
  // 監視側が落ちても送れるよう、同じ通知先へGitHubから異常・復旧を知らせる。
  const incidentPath=join(root,'inventory_incident.json'),previous=await readJson(incidentPath,{}),decision=health.status==='paused'?null:incidentDecision(previous,issues,now());
  if(decision&&webhook) {
    const content=decision.kind==='recovery'?`【カード在庫監視】復旧を確認\n新しい巡回の完了と通知状態を確認しました。\n${STATUS_URL}`:`【カード在庫監視】異常を検知\n${issues.map(i=>i.message).join('／')}\n確認：${time(health.checkedAt)}\n${STATUS_URL}`;
    const incident={...previous,...decision,lastAttemptAt:now(),delivery:'failed',...(decision.kind==='alert'?{deliveredAt:0}:{})};
    try {
      const url=new URL(webhook);url.searchParams.set('wait','true');
      const response=await fetcher(url,{method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{'Content-Type':'application/json','User-Agent':'DiscordBot (https://github.com/nekoromme/tcg-box-monitor-public, 1.0)'},body:JSON.stringify({content,allowed_mentions:{parse:[]}})});
      if(!response.ok)throw new Error('delivery failed');
      await response.body?.cancel();incident.delivery='sent';incident.deliveredAt=now();
    }catch{log(JSON.stringify({event:'inventory_incident_delivery_failed'}));}
    // 復旧通知が失敗した場合は、次回も復旧通知を再試行できるよう元の障害を残す。
    if(decision.kind==='recovery'&&incident.delivery!=='sent')incident.fingerprint=previous.fingerprint;
    await writeFile(incidentPath,JSON.stringify(incident,null,2)+'\n');
  }
  log(JSON.stringify({event:'inventory_health',...health,deliveryHealth:state?.deliveryHealth,storage:state?.storage}));
  return health;
}
if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const result=await runInventorySync();if(result.status==='degraded')process.exitCode=1;
}
