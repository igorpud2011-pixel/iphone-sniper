// Cloudflare Worker: Discord interactions + private settings endpoint.
const defaults = () => ({models:[11,12,13,14,15],city:'Bielsko-Biała',radius:30,min:0,max:null,enabled:true});
const json = (data,status=200) => Response.json(data,{status,headers:{'Cache-Control':'no-store'}});
const reply = content => json({type:4,data:{content,flags:64,allowed_mentions:{parse:[]}}});
const modelPanel = current => ({
 content:`## ⚙️ Ustawienia alertów\n**Modele iPhone** — zaznacz modele, które mają być monitorowane. Zmiana zapisuje się od razu.\n${current.models.map(n=>`☑️ iPhone ${n}`).join('  ·  ') || '☑️ Brak wybranych modeli'}\n\n**Lokalizacja**\n${current.city} · promień ${current.radius} km\n\n**Zakres ceny**\n${current.min}–${current.max??'bez limitu'} zł\n\n**Monitoring**\n${current.enabled?'🟢 Włączony':'⏸️ Wstrzymany'}\n\nZmiany wyszukiwania wczytuje kolejny przebieg monitora.`,
 components:[{type:1,components:[{type:3,custom_id:'settings_models',placeholder:'Wybierz monitorowane modele',min_values:1,max_values:5,options:[11,12,13,14,15].map(n=>({label:`iPhone ${n}`,value:String(n),default:current.models.includes(n)}))}]}],
 allowed_mentions:{parse:[]}
});
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
  const models=[...new Set(String(options.lista||'').split(/[ ,;]+/).filter(Boolean).map(Number))];
  if(!models.length || models.some(n=>!Number.isInteger(n)||n<11||n>15)) throw Error('Podaj modele od 11 do 15, np. 11 13 15.');
  s.models=models.sort((a,b)=>a-b);
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
 const url=new URL(request.url);
 if(url.pathname==='/settings'&&request.method==='GET'){
  if(!env.SETTINGS_KEY || request.headers.get('Authorization')!==`Bearer ${env.SETTINGS_KEY}`)return json({error:'Unauthorized'},401);
  return json(await env.SETTINGS.get('settings','json')||defaults());
 }
 if(url.pathname!=='/interactions'||request.method!=='POST')return json({error:'Not found'},404);
 const body=await request.text();
 if(!await verify(request,body,env.DISCORD_PUBLIC_KEY))return json({error:'Invalid signature'},401);
 let interaction;try{interaction=JSON.parse(body);}catch{return json({error:'Invalid JSON'},400);}
 if(interaction.type===1)return json({type:1});
 if(interaction.type!==2&&interaction.type!==3)return json({error:'Unsupported interaction'},400);
 const user=interaction.member?.user?.id||interaction.user?.id;
 if(!env.OWNER_ID||user!==env.OWNER_ID)return reply('Tylko właściciel może sterować tym botem.');
 if(interaction.type===3){
  if(interaction.data?.custom_id!=='settings_models')return json({type:6});
  const selected=interaction.data?.values||[];
  if(selected.some(v=>!/^1[1-5]$/.test(v)))return json({type:6});
  const current=await env.SETTINGS.get('settings','json')||defaults();
  const next={...current,models:selected.map(Number).sort((a,b)=>a-b)};
  await env.SETTINGS.put('settings',JSON.stringify(next));
  return json({type:7,data:modelPanel(next)});
 }
 const name=interaction.data?.name;
 const options=Object.fromEntries((interaction.data?.options||[]).map(o=>[o.name,o.value]));
 // Acknowledge within Discord's three-second window; storage happens afterwards.
 ctx.waitUntil((async()=>{
  let message;
  try{
   const current=await env.SETTINGS.get('settings','json')||defaults();
   if(name==='ustawienia'){
    const endpoint=`https://discord.com/api/v10/webhooks/${interaction.application_id}/${interaction.token}/messages/@original`;
    const result=await fetch(endpoint,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(modelPanel(current))});
    if(!result.ok)console.error('Discord response failed',result.status);
    return;
   }
   else{
    const next=change(current,name,options);
    await env.SETTINGS.put('settings',JSON.stringify(next));
    message='Zapisano ustawienia. Monitor zastosuje je przy następnym uruchomieniu. Po zmianie wyszukiwania pierwsze skanowanie ustala historię bez wysyłania starych ofert.';
   }
  }catch(e){message=e.message||'Nie udało się zapisać ustawień.';}
  const endpoint=`https://discord.com/api/v10/webhooks/${interaction.application_id}/${interaction.token}/messages/@original`;
  const result=await fetch(endpoint,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:message,allowed_mentions:{parse:[]}})});
  if(!result.ok)console.error('Discord response failed',result.status);
 })());
 return json({type:5,data:{flags:64}});
}};
