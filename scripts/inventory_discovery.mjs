import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
const safe=s=>String(s??'').replace(/[\r\n|<>]/g,' ');
const time=n=>n?new Date(n).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}):'未確認';
// 起動時刻でなく各観測の日付へ保存。停止後の再開・同一時刻の別店舗も失わない。
export async function archiveDiscovery(root,discovery) {
  if(!discovery?.log?.length)return;
  const dir=join(root,'discovery-logs');await mkdir(dir,{recursive:true});
  const days=new Map();
  for(const row of discovery.log)if(Number.isFinite(row.at)) {
    const day=new Date(row.at).toLocaleDateString('sv-SE',{timeZone:'Asia/Tokyo'});
    if(!days.has(day))days.set(day,[]);days.get(day).push(row);
  }
  const key=x=>JSON.stringify([x.at,x.kind,x.storeId,x.targetId,x.ruleId]);
  for(const [day,rows] of days) {
    const path=join(dir,`${day}.jsonl`);let old=[];
    try{old=(await readFile(path,'utf8')).split('\n').filter(Boolean).map(x=>JSON.parse(x));}catch(error){if(error.code!=='ENOENT')throw error;}
    const merged=new Map(old.map(x=>[key(x),x]));for(const row of rows)merged.set(key(row),row);
    await writeFile(path,[...merged.values()].sort((a,b)=>a.at-b.at).map(x=>JSON.stringify(x)).join('\n')+'\n');
  }
}
export function discoveryReport(discovery) {
  if(!discovery)return ['掲載探索の新方式はまだ稼働確認できていません。'];
  const modes={normal:'通常',quiet:'変化少',focused:'重点',waiting:'待機',paused:'停止中'};
  return ['','## 販売ページの発見・観測','',
    '一覧は通常30分、24時間以上追加なしの店は60分、新しい対象ページを発見した店は2時間だけ10分が目安。15分以内の販売終了を過去7日間に2回以上確認した店も24時間重点監視。最大3店、商品詳細の重点枠は最大5ページ・2分以上。通信上限・店舗の応答によって延びます。',
    '初回発見は掲載開始時刻とは限りません。購入可能時間は観測による下限・上限を記録し、初回から売り切れ・取得失敗を短時間完売には数えません。',
    '', '|店舗|状態|間隔目安|理由|最終成功|次回予定|前回発見|','|---|---|---:|---|---|---|---:|',
    ...Object.values(discovery.stores||{}).map(s=>`|${safe(s.storeName||s.storeId)}|${modes[s.mode]||'初回待ち'}|${s.intervalMs?Math.ceil(s.intervalMs/60000)+'分':'未確認'}|${safe(s.error||s.reason)}|${time(s.lastAt)}|${time(s.nextAt)}|${s.lastResult?.registered||0}|`),
    '', '個々の観測と頻度を変えた理由は [discovery-logs](discovery-logs) に日付別で保存。検索範囲・続きの有無・未確認も記録します。'];
}
