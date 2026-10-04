import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {archiveDiscovery,discoveryReport} from '../scripts/inventory_discovery.mjs';
import {assessInventory} from '../scripts/inventory_health.mjs';

test('観測日のファイルへ冪等に追記し、同時刻の複数店・種別を保持する',async t=>{
  const root=await mkdtemp(join(tmpdir(),'discovery-archive-'));t.after(()=>rm(root,{recursive:true,force:true}));
  const at=Date.parse('2026-10-04T14:59:00Z');
  const log=[{at,kind:'listing',storeId:'a'},{at,kind:'listing',storeId:'b'},{at,kind:'page_found',storeId:'a',targetId:'one'},
    {at:at+120000,kind:'sold_out',storeId:'a',targetId:'one',durationUpperMs:null}];
  await archiveDiscovery(root,{log});await archiveDiscovery(root,{log});
  const a=(await readFile(join(root,'discovery-logs/2026-10-04.jsonl'),'utf8')).trim().split('\n');assert.equal(a.length,3);
  const b=JSON.parse(await readFile(join(root,'discovery-logs/2026-10-05.jsonl'),'utf8'));assert.equal(b.durationUpperMs,null);
  // 壊れた既存ログを空扱いして上書きしない。
  await writeFile(join(root,'discovery-logs/2026-10-04.jsonl'),'broken');await assert.rejects(()=>archiveDiscovery(root,{log}));
});
test('理由と未確認をレポートし、価格判定と同様に未適用も検出する',()=>{
  const text=discoveryReport({stores:{a:{storeId:'a',mode:'waiting',reason:'通常',error:'未確認',intervalMs:3600000}}}).join('\n');
  assert.match(text,/未確認/);assert.match(text,/初回発見は掲載開始時刻とは限りません/);assert.match(text,/60分/);
  assert(assessInventory({enabled:true,automatic:{enabled:true}},Date.now()).some(x=>x.code==='discovery_policy_missing'));
});
