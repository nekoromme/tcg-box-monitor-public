// 「昔一度送れた」と「今も正常」を区別する。外部から監視側の停止も検出する。
export const MINIMUM_VERSION='0.10.4';
export function versionAtLeast(value,minimum=MINIMUM_VERSION) {
  const a=String(value||'').split('.').map(Number),b=minimum.split('.').map(Number);
  if(a.length!==3||a.some(n=>!Number.isInteger(n)))return false;
  for(let i=0;i<3;i++){if(a[i]>b[i])return true;if(a[i]<b[i])return false;}
  return true;
}
export function assessInventory(state,now=Date.now()) {
  const issues=[],add=(code,message)=>issues.push({code,message});
  if(!state.notificationConfigured)add('notification_unconfigured','Discordの通知先が未設定');
  if(!state.enabled)return issues; // 利用者の停止設定を勝手に異常・再開扱いにしない。
  const completed=state.lastCompletedAt||state.lastTick||0;
  if(!completed||now-completed>15*60000)add('monitor_stalled','15分以上、巡回の完了を確認できない');
  if(state.error)add('monitor_error','巡回処理にエラーが残っている');
  const health=state.deliveryHealth||{},events=state.events||[];
  const success=Math.max(health.lastSuccessAt||0,...events.filter(e=>e.delivery==='sent').map(e=>e.sentAt||0));
  // 期限切れで取り消された送信失敗も拾う。成功2件が残っていても見逃さない。
  const recentFailures=events.filter(e=>e.error&&e.delivery!=='sent'&&Math.max(e.lastFailureAt||0,e.cancelledAt||0,e.at||0)>Math.max(success,now-3600000));
  if((health.consecutiveFailures||0)>=2||recentFailures.length>=2)add('delivery_failing','直近のDiscord通知が繰り返し失敗している');
  if(events.some(e=>e.delivery==='failed'&&(e.lastFailureAt||e.at)>now-3600000))add('delivery_exhausted','再試行の上限に達した未送信通知がある');
  if(events.some(e=>e.delivery==='pending'&&now-e.at>15*60000))add('delivery_backlog','15分以上待っている未送信通知がある');
  if(state.automatic?.enabled&&(!state.automatic.lastSync||now-state.automatic.lastSync>6*3600000))add('catalog_stale','6時間以上、新弾情報を更新できていない');
  return issues;
}
export function incidentDecision(previous,issues,now=Date.now()) {
  const fingerprint=issues.map(i=>i.code).sort().join(',');
  if(previous?.lastAttemptAt&&now-previous.lastAttemptAt<15*60000)return null;
  if(fingerprint) {
    if(previous?.fingerprint!==fingerprint||!previous.deliveredAt||now-previous.deliveredAt>=6*3600000)return {kind:'alert',fingerprint};
  } else if(previous?.fingerprint&&previous.deliveredAt)return {kind:'recovery',fingerprint:''};
  return null;
}
