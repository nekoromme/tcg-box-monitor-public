import {readFile} from 'node:fs/promises';

export const POLICY_URL='https://github.com/nekoromme/tcg-box-monitor-public/blob/main/config/inventory-notification-policy.json';
const safe=value=>String(value??'').replace(/[\r\n|<>]/g,' ');

// この設定はDiscord自動監視用。ブラウザの別の合言葉の監視には触れない。
// 相場の自動推測ではなく、確認日と根拠のある商品ID単位の停止リストを使う。
export async function loadInventoryPolicy() {
  const policy=JSON.parse(await readFile(new URL('../config/inventory-notification-policy.json',import.meta.url),'utf8'));
  return validateInventoryPolicy(policy);
}

export function validateInventoryPolicy(policy) {
  const ids=new Set();
  if(policy?.version!==1||!Number.isFinite(Date.parse(policy.reviewedAt))||!Array.isArray(policy.pausedProducts))throw policyError('notification_policy_invalid');
  for(const product of policy.pausedProducts) {
    if(typeof product.id!=='string'||!product.id||ids.has(product.id)||!product.name||!product.reason||!product.evidence?.length)throw policyError('notification_policy_invalid');
    for(const source of product.evidence)if(!/^https:\/\//.test(source.url)||!source.kind||!Number.isInteger(source.price)||source.price<=0)throw policyError('notification_policy_invalid');
    ids.add(product.id);
  }
  return policy;
}

function policyError(code) {return Object.assign(new Error(code),{code});}

// 削除すると新弾同期で作り直されるため、既存の「一時停止」を使う。
// 通知待ちの取消・過去の送信ID・個別価格上限・商品履歴は監視本体で維持する。
// リストにない商品を再開する操作は行わず、利用者の手動停止を尊重する。
export async function enforceInventoryPolicy(state,policy,api,log=()=>{}) {
  validateInventoryPolicy(policy);
  const excluded=new Set(policy.pausedProducts.map(p=>p.id));
  const changes=state.rules.filter(r=>excluded.has(r.automaticProductId)&&r.enabled!==false).map(r=>({id:r.id,productId:r.automaticProductId}));
  for(const change of changes) {
    state=await api({action:'toggle',id:change.id,enabled:false});
    if(!state.rules.some(r=>r.id===change.id&&r.enabled===false))throw policyError('notification_policy_not_applied');
    log(JSON.stringify({event:'inventory_product_paused',productId:change.productId,reviewedAt:policy.reviewedAt}));
  }
  return state;
}

export function inventoryPolicyIssues(state,policy) {
  const excluded=new Set(policy.pausedProducts.map(p=>p.id));
  return state.rules.some(r=>excluded.has(r.automaticProductId)&&r.enabled!==false)
    ?[{code:'notification_policy_not_applied',message:'停止対象のBOXが自動監視で有効になっている'}]:[];
}

export function inventoryPolicySummary(state,policy,now=Date.now()) {
  const excluded=new Map(policy.pausedProducts.map(p=>[p.id,p]));
  return {version:policy.version,reviewedAt:policy.reviewedAt,verifiedAt:now,sourceUrl:POLICY_URL,pausedProducts:policy.pausedProducts,
    products:state.automatic.products.map(p=>{
      const rule=state.rules.find(r=>r.automaticProductId===p.id);
      const active=!!(state.enabled&&state.automatic.enabled&&rule?.enabled&&!rule.autoRetired);
      const stopped=excluded.get(p.id);
      return {...p,monitoringEnabled:active,notificationStatus:stopped&&!active?'相場確認により停止':!active?'設定により停止':p.priceStatus!=='ready'?'定価確認まで通知保留':'価格条件内なら通知',notificationReason:stopped?.reason||''};
    })};
}

export function inventoryPolicyReport(summary) {
  return ['', '## 自動通知の対象設定', '',
    `相場確認日：${summary.reviewedAt}。停止リストは [inventory-notification-policy.json](${POLICY_URL})。`,
    'この一覧がDiscord自動通知側の設定です。ブラウザに保存された合言葉の手動監視とは別です。',
    '停止した弾は個別の巡回・在庫通知を止め、登録・価格上限・過去の履歴を残します。新弾同期では再開しません。相場の常時再判定や自動再開は行いません。',
    '', '|停止対象|理由|確認した価格（送料・手数料別）|', '|---|---|---|',
    ...summary.pausedProducts.map(p=>`|${safe(p.name)}|${safe(p.reason)}|${p.evidence.map(e=>`[${safe(e.kind)} ${e.price.toLocaleString('ja-JP')}円](${e.url})`).join('／')}|`), ''];
}
