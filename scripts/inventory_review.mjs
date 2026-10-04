const DAY=86400000;
// 週1回、保存した実観測から除外候補を作る。安値が一瞬出ただけでは除外しない。
// 相場サイトの最高出品額を根拠に、停止中の商品を自動で復帰させない。
export function reviewInventoryMarket(state,policy,previous={},now=Date.now()) {
  if(previous.nextReviewAt>now)return previous;
  const products=state.automatic.products.map(p=>{
    const rules=state.rules.filter(r=>r.automaticProductId===p.id),ids=new Set(rules.map(r=>r.id));
    const paused=policy.pausedProducts.some(x=>x.id===p.id)&&policy.productSettings?.[p.id]?.enabled!==true,evidence=[];
    for(const target of state.targets.filter(t=>(t.ruleIds||[]).some(id=>ids.has(id)))) {
      // 取得失敗や売切れをまたいで24時間連続と判定しない。現在の連続観測だけ使う。
      const observation=target.history?.at(-1);
      if(observation?.kind!=='observation'||observation.stock!=='in_stock'||observation.comparable===false||!p.boxPrice||observation.price>Math.floor(p.boxPrice*1.05)||!observation.price)continue;
      if((observation.lastAt||observation.at)<now-DAY||observation.lastAt-observation.at<DAY||observation.samples<3)continue;
      evidence.push({url:target.url,price:observation.price,from:observation.at,through:observation.lastAt,samples:observation.samples});
    }
    return {productId:p.id,name:p.name,status:paused?'paused_preserved':evidence.length?'pause_candidate':'insufficient_evidence',
      reason:paused?'既存の停止設定を維持':evidence.length?'定価105%以下の在庫を同一店で24時間以上・3回以上観測':'継続在庫の根拠不足。現在の設定を維持',evidence};
  });
  return {version:1,reviewedAt:now,nextReviewAt:now+7*DAY,scope:'監視店の在庫履歴。市場全体の成約価格ではありません。候補の提示のみで停止・再開はしません。',products};
}
export function inventoryCadenceSummary(state,now=Date.now()) {
  const active=state.targets.filter(t=>t.monitorActive),lags=state.events.filter(e=>e.delivery==='sent'&&e.kind!=='catalog'&&e.sentAt>=now-7*DAY&&e.sentAt>=e.at).map(e=>e.sentAt-e.at).sort((a,b)=>a-b);
  return {checkedAt:now,notificationDelay:{samples:lags.length,medianMs:lags.length?lags[Math.floor(lags.length/2)]:null,maxMs:lags.length?lags.at(-1):null},
    products:state.automatic.products.map(p=>{
      const ids=new Set(state.rules.filter(r=>r.automaticProductId===p.id).map(r=>r.id));
      const targets=active.filter(t=>(t.ruleIds||[]).some(id=>ids.has(id))),intervals=targets.map(t=>t.intervalSeconds).filter(Number.isFinite);
      return {productId:p.id,pages:targets.length,minSeconds:intervals.length?Math.min(...intervals):null,maxSeconds:intervals.length?Math.max(...intervals):null,
        nextAt:targets.length?Math.min(...targets.map(t=>t.nextAt)):null,errors:targets.filter(t=>t.error).length};
    }),
    limitations:'送信遅延は在庫を検知してから通知受理まで。店舗の実際の販売開始からの時間は不明。観測間に完売した販売は判定できません。'};
}
