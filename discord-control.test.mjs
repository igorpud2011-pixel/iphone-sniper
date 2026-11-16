import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{change,modelPanel,verify,MODEL_IDS,expandModels} from './discord-control.mjs';
const state={models:[11,12],city:'Bielsko-Biała',radius:30,min:0,max:null,enabled:true};
test('catalog and exact models support old families',()=>{
 assert.ok(change(state,'modele',{lista:'15 11 15'}).models.includes('11 pro max'));
 assert.ok(change(state,'modele',{lista:'16'}).models.includes('16'));
 assert.ok(change(state,'modele',{lista:'xs max, 16e'}).models.includes('xs max'));
 assert.throws(()=>change(state,'modele',{lista:'nonsense'}));
 assert.throws(()=>change(state,'cena',{minimum:600,maksimum:500}));
 assert.equal(change(state,'pauza').enabled,false);
 assert.equal(state.enabled,true);
});
test('all models appear once in multi-select lists within Discord limits',()=>{
 const panel=modelPanel(state);
 const menus=panel.components.filter(row=>row.components[0].type===3).map(row=>row.components[0]);
 assert.equal(menus.length,3);
 assert.deepEqual(menus.flatMap(m=>m.options.map(o=>o.value)),MODEL_IDS);
 assert.equal(new Set(MODEL_IDS).size,MODEL_IDS.length);
 for(const m of menus){assert.ok(m.options.length<=25);assert.ok(m.max_values<=25);}
 assert.ok(menus.flatMap(m=>m.options).find(o=>o.value==='11 pro').default);
});
test('private settings endpoint denies anonymous requests',async()=>{
 const r=await worker.fetch(new Request('https://example.com/settings'),{SETTINGS_KEY:'test'},{});
 assert.equal(r.status,401);
});
test('Discord signature verifies body and timestamp',async()=>{
 const key=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
 const pub=Buffer.from(await crypto.subtle.exportKey('raw',key.publicKey)).toString('hex');
 const timestamp=String(Math.floor(Date.now()/1000)),body=JSON.stringify({type:1});
 const signature=Buffer.from(await crypto.subtle.sign('Ed25519',key.privateKey,new TextEncoder().encode(timestamp+body))).toString('hex');
 const req=new Request('https://example.com/interactions',{headers:{'X-Signature-Timestamp':timestamp,'X-Signature-Ed25519':signature}});
 assert.equal(await verify(req,body,pub),true);
 assert.equal(await verify(req,body+'x',pub),false);
 assert.equal(await verify(new Request(req,{headers:{'X-Signature-Timestamp':'1','X-Signature-Ed25519':signature}}),body,pub),false);
});
test('signed multi-select saves only its group and rejects other users',async()=>{
 const keys=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
 const pub=Buffer.from(await crypto.subtle.exportKey('raw',keys.publicKey)).toString('hex');
 let saved={...state,models:['16','11']}; const waits=[];
 const env={OWNER_ID:'123',DISCORD_PUBLIC_KEY:pub,SETTINGS:{get:async()=>saved,put:async(k,v)=>{saved=JSON.parse(v);}}};
 const oldFetch=globalThis.fetch;globalThis.fetch=async()=>new Response('{}');
 async function send(user){
  const body=JSON.stringify({type:3,data:{custom_id:'settings_select_0',values:['16e']},member:{user:{id:user}},application_id:'1',token:'test'});
  const ts=String(Math.floor(Date.now()/1000));const sig=Buffer.from(await crypto.subtle.sign('Ed25519',keys.privateKey,new TextEncoder().encode(ts+body))).toString('hex');
  return (await worker.fetch(new Request('https://example.com/interactions',{method:'POST',headers:{'X-Signature-Timestamp':ts,'X-Signature-Ed25519':sig},body}),env,{waitUntil:p=>waits.push(p)})).json();
 }
 try{
  assert.equal((await send('wrong')).type,4);assert.deepEqual(saved.models,['16','11']);
  assert.equal((await send('123')).type,6);await Promise.all(waits);
  assert.deepEqual(saved.models,['11','16e']);
 }finally{globalThis.fetch=oldFetch;}
});
test('owner grants and revokes access; member cannot change access list',async()=>{
 const keys=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
 const pub=Buffer.from(await crypto.subtle.exportKey('raw',keys.publicKey)).toString('hex');
 const owner='111111111111111111', member='222222222222222222';
 const db=new Map([['settings',state],['access',[]]]);const waits=[];
 const env={OWNER_ID:owner,DISCORD_PUBLIC_KEY:pub,SETTINGS:{get:async k=>db.get(k),put:async(k,v)=>db.set(k,JSON.parse(v))}};
 const oldFetch=globalThis.fetch;globalThis.fetch=async()=>new Response('{}');
 async function call(user,type,data){
  const body=JSON.stringify({type,data,member:{user:{id:user}},application_id:'1',token:'test'}), ts=String(Math.floor(Date.now()/1000));
  const sig=Buffer.from(await crypto.subtle.sign('Ed25519',keys.privateKey,new TextEncoder().encode(ts+body))).toString('hex');
  const result=await worker.fetch(new Request('https://example.com/interactions',{method:'POST',headers:{'X-Signature-Timestamp':ts,'X-Signature-Ed25519':sig},body}),env,{waitUntil:p=>waits.push(p)});
  await Promise.all(waits);return result.json();
 }
 try{
  assert.equal((await call(member,2,{name:'ustawienia'})).type,4);
  await call(owner,3,{custom_id:'settings_access_save',values:[member]});
  assert.deepEqual(db.get('access'),[member]);
  assert.equal((await call(member,2,{name:'ustawienia'})).type,5);
  assert.equal((await call(member,3,{custom_id:'settings_access_save',values:[]})).type,4);
  assert.deepEqual(db.get('access'),[member]);
  await call(owner,3,{custom_id:'settings_access_save',values:[]});
  assert.equal((await call(member,2,{name:'ustawienia'})).type,4);
 }finally{globalThis.fetch=oldFetch;}
});
test('status reports are authenticated and preserve last success after failures',async()=>{
 const db=new Map();const env={SETTINGS_KEY:'test',SETTINGS:{get:async k=>db.get(k),put:async(k,v)=>db.set(k,JSON.parse(v))}};
 const t=Math.floor(Date.now()/1000);
 const h={status:'ok',searches_total:6,searches_ok:6,fetched:200,matched:0,alerts:0,errors:[],finished_at:t-2,duration_seconds:10};
 const post=(report,key='test')=>worker.fetch(new Request('https://example.com/health',{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},body:JSON.stringify(report)}),env,{});
 assert.equal((await post(h,'wrong')).status,401);
 assert.equal((await post(h)).status,200);
 await post({...h,status:'error',finished_at:t,errors:['Timeout'],searches_ok:0});
 assert.equal(db.get('health').last_success_at,t-2);
 assert.equal((await post({...h,fetched:-1})).status,400);
 const {statusPanel}=await import('./discord-control.mjs');
 assert.match(statusPanel(db.get('health'),{enabled:true},t).embeds[0].description,/Błąd/);
 assert.match(statusPanel(db.get('health'),{enabled:true},t+600).embeds[0].description,/Brak świeżego/);
});
test('offer form is local only and preserves private settings authorization',async()=>{
 const response=await worker.fetch(new Request('https://example.com/offer'),{},{});
 assert.equal(response.status,200);
 assert.match(response.headers.get('Content-Security-Policy'),/connect-src 'none'/);
 assert.equal(response.headers.get('Referrer-Policy'),'no-referrer');
 const html=await response.text();
 assert.match(html,/location.hash/);
 assert.match(html,/navigator.clipboard.writeText/);
 assert.match(html,/minus 200 zł/);
 assert.doesNotMatch(html,/localStorage|fetch\(/);
 assert.equal((await worker.fetch(new Request('https://example.com/settings'),{},{})).status,401);
});
