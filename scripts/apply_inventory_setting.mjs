// 設定画面からGitHubの認証画面を経由して届く、所有者本人の変更だけを受け付ける。
// 公開ページに通知鍵・Webhook・GitHubトークンを渡さない。
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {validateInventoryPolicy} from './inventory_policy.mjs';
export function applySettingRequest(policy,event,products,now=Date.now()) {
  if(event.issue?.user?.login!==event.repository?.owner?.login||event.issue?.title!=='[在庫設定] 通知条件の変更'||event.issue?.pull_request)throw new Error('設定変更はリポジトリ所有者本人のみ可能です');
  const body=event.issue.body||'';if(body.length>3000)throw new Error('設定内容が長すぎます');
  const block=body.match(/```json\s*([\s\S]*?)\s*```/);if(!block)throw new Error('設定内容を読み取れません');
  const input=JSON.parse(block[1]);
  if(input.version!==1||!products.some(p=>p.id===input.productId))throw new Error('監視対象の商品を確認できません');
  if(typeof input.enabled!=='boolean'||!Number.isInteger(input.percent)||input.percent<50||input.percent>1000||input.maxPrice!==null&&(!Number.isInteger(input.maxPrice)||input.maxPrice<1||input.maxPrice>99999999))throw new Error('通知条件が不正です');
  const next=structuredClone(policy);next.productSettings ||= {};
  next.productSettings[input.productId]={enabled:input.enabled,percent:input.percent,maxPrice:input.maxPrice,updatedAt:new Date(now).toISOString(),issueNumber:event.issue.number};
  return validateInventoryPolicy(next);
}
if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const event=JSON.parse(await readFile(process.env.GITHUB_EVENT_PATH,'utf8'));
  const path='config/inventory-notification-policy.json',policy=JSON.parse(await readFile(path,'utf8'));
  const state=JSON.parse(await readFile('.monitor-state/inventory_status.json','utf8'));
  const next=applySettingRequest(policy,event,state.automatic.products);
  await writeFile(path,JSON.stringify(next,null,2)+'\n');
  console.log('所有者の通知設定を検証しました。');
}
