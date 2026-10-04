// 公式の税込価格と、商品ごとに確認したBOX入数を組み合わせる。
// 「このシリーズはいつも24袋」の推測や、店舗のプレ値を定価として使わない。
export const PRICE_HOSTS={pokemon:['www.pokemon-card.com','www.30th.pokemon-card.com'],onepiece:['www.onepiece-cardgame.com'],gundam:['www.gundam-gcg.com'],dragonball:['www.dbs-cardgame.com'],lorcana:['www.takaratomy.co.jp'],yugioh:['www.yugioh-card.com']};
const DAY=86400000;
const normalize=s=>String(s||'').normalize('NFKC').toLowerCase().replace(/[\s\-‐－_【】「」『』()（）・:：\[\]]/g,'');
export const plain=s=>String(s||'').replace(/<(script|style|nav|header|footer)\b[^>]*>[\s\S]*?<\/\1>/gi,' ').replace(/<[^>]*>/g,' ').replace(/&nbsp;|&#160;/g,' ').replace(/&amp;/g,'&').replace(/&#(\d+);/g,(_,n)=>String.fromCodePoint(Number(n))).normalize('NFKC').replace(/\s+/g,' ').trim();
export function officialUrl(product,url) {
  try{const u=new URL(url);return u.protocol==='https:'&&!u.username&&!u.password&&PRICE_HOSTS[product.game]?.includes(u.hostname)?u.href:null;}catch{return null;}
}
export function productIdentity(product,title) {
  if(/ヴァンガード|ヴァイス|デュエル.?マスターズ|英語版|海外版|中古|開封済|空箱/i.test(title))return false;
  const code=(product.code||product.query||'').match(/^(OP|EB|GD|FB|SB|ST|PRB)-?(\d+)$/i);
  const game={pokemon:/ポケモン|ポケカ/i,onepiece:/ONE\s*PIECE|ワンピース/i,gundam:/ガンダム|GUNDAM/i,dragonball:/ドラゴンボール|DRAGON\s*BALL/i,lorcana:/ロルカナ|LORCANA/i,yugioh:/遊[☆★]?戯[☆★]?王|YU.?GI.?OH/i}[product.game];
  if(code&&new RegExp(`(?<![a-z0-9])${code[1]}[\\s-]*${code[2]}(?![a-z0-9])`,'i').test(title)&&game?.test(title))return true;
  const name=normalize(product.name).replace(/^遊[☆★]?戯[☆★]?王/,'');
  return name.length>=5&&normalize(title).includes(name);
}
function unique(values){const set=[...new Set(values)];return set.length===1?set[0]:null;}
export function boxCount(text) {
  const s=plain(text);
  const values=[...s.matchAll(/(?:1\s*(?:BOX|ボックス|箱)\s*[・:=(]?\s*|\(BOX\)[^。]{0,220}?\()(\d{1,2})\s*パック/gi)].map(m=>Number(m[1])).filter(n=>n>=2&&n<=60);
  return unique(values);
}
export function parseOfficialPrice(product,html,url,now) {
  if(!officialUrl(product,url))return {status:'source_rejected'};
  const title=plain(html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]);
  if(!productIdentity(product,title))return {status:'identity_unconfirmed'};
  let main=html.match(/<main\b[^>]*>([\s\S]*?)<\/main>/i)?.[1]||html;
  // 遊戯王の関連商品一覧にも別商品の価格があるため、主商品の仕様表に限定。
  if(product.game==='yugioh')main=[...main.matchAll(/<dl\b[^>]*>([\s\S]*?)<\/dl>/gi)].map(m=>m[1]).find(s=>/class=["']price["']/.test(s)&&productIdentity(product,plain(s)))||'';
  const specs=[...main.matchAll(/<(?:dt|th|h5)\b[^>]*>\s*(?:メーカー)?(?:希望小売)?価格\s*<\/(?:dt|th|h5)>\s*(?:<div[^>]*>\s*)?<(?:dd|td|p)\b[^>]*>([\s\S]*?)<\/(?:dd|td|p)>/gi)].map(m=>plain(m[1]));
  if(product.game==='yugioh')specs.push(...[...main.matchAll(/<dd\b[^>]*class=["']price["'][^>]*>([\s\S]*?)<\/dd>/gi)].map(m=>plain(m[1])));
  const pack=[],box=[];
  for(const spec of specs) {
    // 明示的な税込表記、またはコナミの「税込額（本体価格 税抜額）」のみ。
    if(!/税込|本体価格/.test(spec))continue;
    for(const part of spec.split(/(?=1\s*(?:BOX|ボックス|箱))/i)) {
      const gross=part.split(/本体価格|税抜/)[0];
      const amount=gross.match(/([\d,]+)\s*円/)?.[1]||gross.match(/[¥￥]\s*([\d,]+)/)?.[1];
      const price=Number(amount?.replaceAll(',',''));if(!Number.isInteger(price)||price<=0)continue;
      if(/1\s*(?:BOX|ボックス|箱)/i.test(part))box.push(price);else if(price<=2000)pack.push(price);
    }
  }
  const packPrice=unique(pack),boxPrice=unique(box),packsPerBox=boxCount(main);
  const evidence={url,checkedAt:now,kind:'official_price',title,packPrice,boxPrice,packsPerBox};
  if(boxPrice&&packPrice&&packsPerBox&&boxPrice!==packPrice*packsPerBox)return {status:'price_conflict',evidence};
  return {status:boxPrice||packPrice?'parsed':'price_unpublished',packPrice,boxPrice,packsPerBox,evidence};
}
export function observedBoxCount(product,state,now) {
  const ruleIds=new Set(state.rules.filter(r=>r.automaticProductId===product.id).map(r=>r.id));
  const observations=state.targets.filter(t=>(t.ruleIds||[]).some(id=>ruleIds.has(id))&&t.lastGood?.detailChecked&&t.lastGoodAt>=now-14*DAY)
    .filter(t=>{try{return ['mediaworld.co.jp','www.masters-square.com'].includes(new URL(t.url).hostname);}catch{return false;}})
    .filter(t=>productIdentity(product,t.lastGood.title)&&!/カートン|\d+\s*BOX\s*(?:セット|組)|FUTURISTIC|デッキ/i.test(t.lastGood.title))
    .map(t=>({count:boxCount(t.lastGood.title),url:t.url,title:t.lastGood.title,checkedAt:t.lastGoodAt})).filter(x=>x.count);
  const count=unique(observations.map(x=>x.count));
  return count?{count,evidence:observations.map(x=>({...x,kind:'observed_box_quantity'}))}:null;
}
async function fetchOfficial(product,url,fetcher) {
  for(let redirects=0;redirects<3;redirects++) {
    if(!officialUrl(product,url))throw new Error('source_rejected');
    const response=await fetcher(url,{redirect:'manual',signal:AbortSignal.timeout(12000),headers:{'User-Agent':'PersonalTCGMonitor/1.0 (+https://github.com/nekoromme/tcg-box-monitor-public)'}});
    if(response.status>=300&&response.status<400){url=new URL(response.headers.get('location'),url).href;await response.body?.cancel();continue;}
    if(!response.ok){await response.body?.cancel();throw new Error(`http_${response.status}`);}
    const reader=response.body.getReader(),chunks=[];let size=0;
    try{while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>1500000)throw new Error('body_too_large');chunks.push(value);}}finally{await reader.cancel();}
    const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
    return {html:new TextDecoder().decode(bytes),url};
  }
  throw new Error('redirect_limit');
}
export async function collectInventoryPrices(state,previous={}, {fetcher=fetch,now=Date.now()}={}) {
  const records={...(previous.records||{})},log=[...(previous.log||[])];
  const products=state.automatic.products;
  // 最大80弾、確認済みは7日・未確定は6時間あける。BOX入数の新しい観測は即利用。
  let requests=0;const deadline=Date.now()+90000;
  for(const product of [...products].sort((a,b)=>(a.priceStatus==='ready')-(b.priceStatus==='ready')).slice(0,80)) {
    const old=records[product.id],quantity=observedBoxCount(product,state,now);
    if(old?.nextCheckAt>now&&!(old.status==='quantity_unconfirmed'&&quantity))continue;
    if(requests>=16||Date.now()>deadline)break;
    requests++;
    let result;
    try {
      const url=product.id==='onepiece-eb-04'?'https://www.onepiece-cardgame.com/products/boosters/eb04.php':product.officialUrl;
      const page=await fetchOfficial(product,url,fetcher),parsed=parseOfficialPrice(product,page.html,page.url,now);
      const count=parsed.packsPerBox||quantity?.count||null;
      const boxPrice=parsed.boxPrice||(parsed.packPrice&&count?parsed.packPrice*count:null);
      result={productId:product.id,game:product.game,name:product.name,officialUrl:page.url,checkedAt:now,
        status:parsed.status==='parsed'?(boxPrice?'confirmed':'quantity_unconfirmed'):parsed.status,
        packPrice:parsed.packPrice||null,packsPerBox:count,boxPrice:parsed.status==='parsed'?boxPrice:null,
        basis:parsed.boxPrice?'official_box':'official_pack_times_verified_count',
        sources:[parsed.evidence,...(!parsed.packsPerBox&&quantity?quantity.evidence:[])].filter(Boolean)};
    } catch(error){result={productId:product.id,game:product.game,name:product.name,checkedAt:now,status:'fetch_failed',error:/^(http_\d+|source_rejected|body_too_large|redirect_limit)$/.test(error.message)?error.message:'connection_failed'};}
    // 一時失敗・掲載終了で確認済みの定価を消さない。失敗時刻と前回の根拠を分けて残す。
    const confirmed=result.status==='confirmed';
    records[product.id]=!confirmed&&old?.status==='confirmed'?{...old,lastAttemptAt:now,lastAttemptStatus:result.status,nextCheckAt:now+6*3600000}:{...result,nextCheckAt:now+(confirmed?7*DAY:6*3600000)};
    log.push({at:now,productId:product.id,status:result.status,boxPrice:result.boxPrice||null,...(result.error?{error:result.error}:{})});
  }
  return {version:1,checkedAt:now,records,log:log.slice(-240)};
}
