import {relay} from './national-relay.mjs';
import offerPage from './offer-page.mjs';
export const MODEL_IDS=["duo", "18 pro max", "18 pro", "17 pro max", "17 pro", "17", "17e", "air", "16 pro max", "16 pro", "16 plus", "16", "16e", "15 pro max", "15 pro", "15 plus", "15", "14 pro max", "14 pro", "14 plus", "14", "13 pro max", "13 pro", "13 mini", "13", "12 pro max", "12 pro", "12 mini", "12", "11 pro max", "11 pro", "11", "xs max", "xs", "xr", "x", "se 2022", "se 2020", "se 2016", "se", "8 plus", "8", "7 plus", "7", "6s plus", "6s", "6 plus", "6", "5s", "5c", "5", "4s", "4", "3gs", "3g", "2g"];
export const expandModels = models => [...new Set(models.flatMap(n=>typeof n==='number'?MODEL_IDS.filter(m=>m.split(' ')[0]===String(n)):[String(n).toLowerCase()]))].filter(m=>MODEL_IDS.includes(m));
const normalizeSettings = s => ({...s,models:expandModels(s.models)});
// Cloudflare Worker: Discord interactions + private settings endpoint.
const defaults = () => ({models:expandModels([11,12,13,14,15]),city:'Bielsko-Biała',radius:30,min:0,max:null,enabled:true});
const json = (data,status=200) => Response.json(data,{status,headers:{'Cache-Control':'no-store'}});
const reply = content => json({type:4,data:{content,flags:64,allowed_mentions:{parse:[]}}});
export const modelPanel = raw => {
 const current=normalizeSettings(raw);
 const chunks=Array.from({length:Math.ceil(MODEL_IDS.length/25)},(_,i)=>MODEL_IDS.slice(i*25,i*25+25));
 return {content:'',embeds:[{title:current.nationwide?'🇵🇱 Ustawienia • Cała Polska':'⚙️ Centrum alertów iPhone',color:0x5865f2,description:'Rozwiń listy i zaznacz modele. W każdej liście możesz wybrać kilka pozycji. Zmiany zapisują się automatycznie.',fields:[
 {name:'📱 Wybrane modele',value:current.models.map(m=>'iPhone '+m.toUpperCase().replace('PRO','Pro').replace('MAX','Max').replace('PLUS','Plus').replace('MINI','mini')).join(', ').slice(0,1024)||'Brak'},
 {name:'📍 Obszar',value:current.nationwide?'Cała Polska':`${current.city} · ${current.radius} km`,inline:true},
 {name:'💰 Cena',value:`${current.min}–${current.max??'bez limitu'} zł`,inline:true},
 {name:'Status',value:current.enabled?'🟢 Monitoring włączony':'⏸️ Monitoring wstrzymany',inline:true}],footer:{text:'Pierwszy skan nowego wyszukiwania ustala historię. Opóźnienie RSS może się różnić.'}}],
 components:[...chunks.map((items,i)=>({type:1,components:[{type:3,custom_id:`settings_select_${i}`,placeholder:`Wybierz modele · lista ${i+1}/${chunks.length}`,min_values:0,max_values:items.length,options:items.map(m=>({label:'iPhone '+m.replace(/\b(pro|max|plus|air|duo|se|xs|xr|x)\b/g,x=>x==='pro'?'Pro':x==='max'?'Max':x==='plus'?'Plus':x==='air'?'Air':x==='duo'?'Duo':x.toUpperCase()),value:m,default:current.models.includes(m)}))}]})),
 {type:1,components:[{type:2,custom_id:'settings_access',label:'👥 Dostęp',style:2},{type:2,custom_id:'settings_location',label:'📍 Lokalizacja',style:2},{type:2,custom_id:'settings_price',label:'💰 Cena',style:2},{type:2,custom_id:'settings_models_all',label:'Wszystkie',style:2},{type:2,custom_id:'settings_monitor',label:current.enabled?'⏸ Pauza':'▶ Wznów',style:current.enabled?2:3}]}],allowed_mentions:{parse:[]}};
};
export function statusPanel(health,settings,now=Math.floor(Date.now()/1000)){
 const stale=!health||now-health.finished_at>300;
 const state=!settings.enabled?'⏸️ Monitoring wstrzymany':stale?'⚠️ Brak świeżego raportu':({ok:'🟢 Skan zakończony poprawnie',partial:'🟠 Częściowy błąd',error:'🔴 Błąd skanowania',paused:'⏸️ Ostatni skan był wstrzymany'}[health.status]||'⚠️ Nieznany stan');
 const date=t=>t?`<t:${t}:F> (<t:${t}:R>)`:'Brak danych';
 return {content:'',embeds:[{title:'📡 Status monitora OLX',description:state,color:stale||health?.status==='error'?0xe74c3c:0x5865f2,fields:[
 {name:'Ostatni raport',value:date(health?.finished_at)},
 {name:'Ostatni pełny udany skan',value:date(health?.last_success_at)},
 {name:'Wyszukiwania',value:health?`${health.searches_ok}/${health.searches_total} poprawnych`:'Brak danych',inline:true},
 {name:'Odczytane pozycje',value:String(health?.fetched??'—'),inline:true},
 {name:'Nowe pasujące / wysłane',value:health?`${health.matched} / ${health.alerts}`:'—',inline:true},
 {name:'Czas skanu',value:health?`${health.duration_seconds} s`:'—',inline:true},
 {name:'Błędy',value:health?.errors?.length?health.errors.join('\n').slice(0,1024):'Brak zgłoszonych błędów'+(health?'':' (brak raportu)')}],footer:{text:'Pozycje mogą powtarzać się między wyszukiwaniami. Status potwierdza odczyt RSS, nie kompletność OLX.'}}],allowed_mentions:{parse:[]}};
}
const hex = x => {
  if (!/^(?:[a-f\d]{2})+$/i.test(x || '')) throw Error('hex');
  return Uint8Array.from(x.match(/../g),v=>parseInt(v,16));
};
export async function verify(request,body,key){
 try {
  const timestamp=request.headers.get('X-Signature-Timestamp');
  if (!/^\d+$/.test(timestamp||'') || Math.abs(Date.now()/1000-Number(timestamp))>300) return false;
  const publicKey=await crypto.subtle.importKey('raw',hex(key),{name:'Ed25519'},false,['verify']);
  return await crypto.subtle.verify('Ed25519',publicKey,hex(request.headers.get('X-Signature-Ed25519')),new TextEncoder().encode(timestamp+body));
 } catch {return false;}
}
export function change(current,name,options={}){
 const s=structuredClone(current);
 if(name==='modele'){
  const values=String(options.lista||'').toLowerCase().replace(/iphone/g,'').trim();
  const tokens=values.includes(',')?values.split(',').map(v=>v.trim()):values.split(/[ ;]+/);
  const models=expandModels(tokens.map(v=>/^\d+$/.test(v)?Number(v):v));
  if(!models.length)throw Error('Wybierz modele w /ustawienia lub podaj np. 11, 13 pro, 16e.');
  s.models=models;
 }else if(name==='lokalizacja'){
  const city=String(options.miasto||'').trim();
  if(!/^[\p{L}\s-]{2,80}$/u.test(city)) throw Error('Niepoprawna nazwa miasta.');
  const radius=Number(options.promien);
  if(![0,2,5,10,15,30,50,75,100,150,200].includes(radius)) throw Error('Wybierz obsługiwany promień OLX.');
  s.city=city;s.radius=radius;
 }else if(name==='cena'){
  const min=Number(options.minimum??0),max=options.maksimum==null?null:Number(options.maksimum);
  if(!Number.isInteger(min)||min<0||min>100000||(max!==null&&(!Number.isInteger(max)||max<min||max>100000))) throw Error('Sprawdź zakres cen: minimum nie może przekraczać maksimum.');
  s.min=min;s.max=max;
 }else if(name==='pauza')s.enabled=false;
 else if(name==='start')s.enabled=true;
 else throw Error('Nieznana komenda.');
 return s;
}
export default {async fetch(request,env,ctx){
 if(new URL(request.url).pathname==='/offer'&&request.method==='GET')return new Response(offerPage,{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"}});

 const url=new URL(request.url);
 const relayed=await relay(request,env);if(relayed)return relayed;
 const apiNational=url.searchParams.get('profile')==='polska';
 async function profile(national){
  if(!national)return normalizeSettings(await env.SETTINGS.get('settings','json')||defaults());
  let value=await env.SETTINGS.get('settings_pl','json');
  if(!value){value={...await profile(false),city:'Cała Polska',radius:0,nationwide:true};await env.SETTINGS.put('settings_pl',JSON.stringify(value));}
  return normalizeSettings(value);
 }
 const reportKey=apiNational?'health_pl':'health';

 if(url.pathname==='/health'&&request.method==='POST'){
  if(!env.SETTINGS_KEY||request.headers.get('Authorization')!==`Bearer ${env.SETTINGS_KEY}`)return json({error:'Unauthorized'},401);
  let h;try{h=await request.json();}catch{return json({error:'Invalid JSON'},400);}
  const counts=['searches_total','searches_ok','fetched','matched','alerts'];
  if(!['ok','partial','error','paused'].includes(h.status)||counts.some(k=>!Number.isInteger(h[k])||h[k]<0||h[k]>1000000)||!Number.isInteger(h.finished_at)||Math.abs(Date.now()/1000-h.finished_at)>300||!Number.isFinite(h.duration_seconds)||h.duration_seconds<0||h.duration_seconds>21600||!Array.isArray(h.errors)||h.errors.length>100||h.errors.some(e=>typeof e!=='string'||e.length>300))return json({error:'Invalid report'},400);
  const previous=await env.SETTINGS.get(reportKey,'json');
  if(previous?.finished_at>h.finished_at)return json({ok:true});
  const clean=Object.fromEntries(['status','finished_at','duration_seconds','errors',...counts].map(k=>[k,h[k]]));
  clean.last_success_at=h.status==='ok'?h.finished_at:previous?.last_success_at??null;
  await env.SETTINGS.put(reportKey,JSON.stringify(clean));return json({ok:true});
 }
 if(url.pathname==='/settings'&&request.method==='GET'){
  if(!env.SETTINGS_KEY || request.headers.get('Authorization')!==`Bearer ${env.SETTINGS_KEY}`)return json({error:'Unauthorized'},401);
  return json({...await profile(apiNational),profile_available:!apiNational||Boolean(env.DISCORD_NATIONAL_WEBHOOK_URL)});
 }
 if(url.pathname!=='/interactions'||request.method!=='POST')return json({error:'Not found'},404);
 const body=await request.text();
 if(!await verify(request,body,env.DISCORD_PUBLIC_KEY))return json({error:'Invalid signature'},401);
 let interaction;try{interaction=JSON.parse(body);}catch{return json({error:'Invalid JSON'},400);}
 if(interaction.type===1)return json({type:1});
 if(![2,3,5].includes(interaction.type))return json({error:'Unsupported interaction'},400);
 const national=Boolean(env.NATIONAL_CHANNEL_ID&&interaction.channel_id===env.NATIONAL_CHANNEL_ID);
 const settingsKey=national?'settings_pl':'settings';
 const user=interaction.member?.user?.id||interaction.user?.id;
 const owner=Boolean(env.OWNER_ID&&user===env.OWNER_ID);
 const action=interaction.data?.custom_id||'';
 if(action==='settings_access'||action==='settings_access_save'){
  if(!owner)return reply('Tylko właściciel może nadawać i odbierać dostęp.');
  ctx.waitUntil((async()=>{
   let members=await env.SETTINGS.get('access','json')||[];
   if(!Array.isArray(members))members=[];
   if(action==='settings_access_save'){
    const values=interaction.data.values||[];
    if(values.length>25||values.some(id=>!/^\d{15,22}$/.test(id)))throw Error('Niepoprawna lista osób');
    members=[...new Set(values)].filter(id=>id!==env.OWNER_ID);
    await env.SETTINGS.put('access',JSON.stringify(members));
   }
   const panel={content:'## 👥 Dostęp do ustawień\nWybierz osoby, które mogą zmieniać wspólne filtry i pauzować alerty. Odznaczenie osoby odbiera dostęp. Tylko Ty możesz zarządzać tą listą.\n\n'+(members.length?'Dostęp: '+members.map(id=>`<@${id}>`).join(', '):'Dostęp ma obecnie tylko właściciel.'),embeds:[],components:[{type:1,components:[{type:5,custom_id:'settings_access_save',placeholder:'Wybierz osoby z dostępem',min_values:0,max_values:25,default_values:members.map(id=>({id,type:'user'}))}]}],allowed_mentions:{parse:[]}};
   const result=await fetch(`https://discord.com/api/v10/webhooks/${interaction.application_id}/${interaction.token}/messages/@original`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(panel)});
   if(!result.ok)console.error('Panel dostępu: HTTP',result.status);
  })().catch(()=>console.error('Nie udało się zapisać listy dostępu.')));
  return json(action==='settings_access'?{type:5,data:{flags:64}}:{type:6});
 }
 const members=owner?[]:await env.SETTINGS.get('access','json');
 if(!owner&&(!Array.isArray(members)||!members.includes(user)))return reply('Brak dostępu. Właściciel może dodać Cię w /ustawienia → Dostęp.');
 if(interaction.type===3){
  const id=interaction.data?.custom_id;
  if(id==='settings_location'&&national)return reply('Ten profil obejmuje całą Polskę. Modele i ceny zmienisz pozostałymi przyciskami.');
  if(id==='settings_location'||id==='settings_price'){
   const location=id==='settings_location';
   const fields=location?[['miasto','Miasto (np. Bielsko-Biała)'],['promien','Promień: 0, 2, 5, 10, 15, 30, 50, 75, 100, 150, 200']]:[['minimum','Cena minimalna w zł (np. 0)'],['maksimum','Cena maksymalna w zł (puste = bez limitu)']];
   return json({type:9,data:{custom_id:location?'settings_location_submit':'settings_price_submit',title:location?'Lokalizacja wyszukiwania':'Zakres cen',components:fields.map(([custom_id,label])=>({type:1,components:[{type:4,custom_id,label:label.slice(0,45),style:1,required:custom_id!=='maksimum',max_length:80}]}))}});
  }
  ctx.waitUntil((async()=>{
  const action=interaction.data?.custom_id||'';
  const current=await profile(national);
  let next;
  const match=/^settings_model_(1[1-5])$/.exec(action);
  const select=/^settings_select_(\d+)$/.exec(action);
  if(select){
   const group=MODEL_IDS.slice(Number(select[1])*25,Number(select[1])*25+25);
   const values=interaction.data.values||[];
   if(!group.length||values.some(m=>!group.includes(m)))return;
   const models=[...current.models.filter(m=>!group.includes(m)),...values];
   if(!models.length)return;
   next={...current,models};
  }else if(match){
   const model=Number(match[1]);
   const models=current.models.includes(model)?current.models.filter(n=>n!==model):[...current.models,model].sort((a,b)=>a-b);
   if(!models.length)return;
   next={...current,models};
  }else if(action==='settings_models_all')next={...current,models:[...MODEL_IDS]};
  else if(action==='settings_monitor')next={...current,enabled:!current.enabled};
  else return;
  await env.SETTINGS.put(settingsKey,JSON.stringify(next));
  await fetch(`https://discord.com/api/v10/webhooks/${interaction.application_id}/${interaction.token}/messages/@original`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(modelPanel(next))});
  })().catch(()=>console.error('Nie udało się zapisać ustawień.')));
  return json({type:6});
 }
 const name=interaction.type===5?(interaction.data.custom_id==='settings_location_submit'?'lokalizacja':interaction.data.custom_id==='settings_price_submit'?'cena':'nieznana'):interaction.data?.name;
 if(national&&name==='lokalizacja')return reply('Ten profil obejmuje całą Polskę. Lokalizację zmienisz na kanale lokalnym.');
 const options=Object.fromEntries((interaction.data?.options||[]).map(o=>[o.name,o.value]));
 if(interaction.type===5){
  for(const row of interaction.data.components||[])for(const field of row.components||[]){
   if(field.custom_id==='miasto')options.miasto=field.value;
   else if(field.value.trim())options[field.custom_id]=Number(field.value);
  }
 }
 // Acknowledge within Discord's three-second window; storage happens afterwards.
 ctx.waitUntil((async()=>{
  let message;
  try{
   const current=await profile(national);
   if(name==='status'){
    const health=await env.SETTINGS.get(national?'health_pl':'health','json');
    const result=await fetch(`https://discord.com/api/v10/webhooks/${interaction.application_id}/${interaction.token}/messages/@original`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(statusPanel(health,current))});
    if(!result.ok)console.error('Status Discord: HTTP',result.status);
    return;
   }
   if(name==='ustawienia'){
    const endpoint=`https://discord.com/api/v10/webhooks/${interaction.application_id}/${interaction.token}/messages/@original`;
    const result=await fetch(endpoint,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(modelPanel(current))});
    if(!result.ok)console.error('Discord response failed',result.status);
    return;
   }
   else{
    const next=change(current,name,options);
    await env.SETTINGS.put(settingsKey,JSON.stringify(next));
    const result=await fetch(`https://discord.com/api/v10/webhooks/${interaction.application_id}/${interaction.token}/messages/@original`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(modelPanel(next))});
    if(!result.ok)console.error('Discord response failed',result.status);
    return;
   }
  }catch(e){message=e.message||'Nie udało się zapisać ustawień.';}
  const endpoint=`https://discord.com/api/v10/webhooks/${interaction.application_id}/${interaction.token}/messages/@original`;
  const result=await fetch(endpoint,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:message,allowed_mentions:{parse:[]}})});
  if(!result.ok)console.error('Discord response failed',result.status);
 })());
 return json({type:5,data:{flags:64}});
}};
