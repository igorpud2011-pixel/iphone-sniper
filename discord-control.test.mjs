import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{change,modelPanel,verify} from './discord-control.mjs';
const state={models:[11,12],city:'Bielsko-Biała',radius:30,min:0,max:null,enabled:true};
test('model and price validation; state is immutable',()=>{
 assert.deepEqual(change(state,'modele',{lista:'15 11 15'}).models,[11,15]);
 assert.throws(()=>change(state,'modele',{lista:'16'}));
 assert.throws(()=>change(state,'cena',{minimum:600,maksimum:500}));
 assert.equal(change(state,'pauza').enabled,false);
 assert.equal(state.enabled,true);
});
test('settings panel offers one toggle for every supported iPhone',()=>{
 const panel=modelPanel(state);
 assert.match(panel.content,/\*\*Wybrane:\*\* iPhone 11 · iPhone 12/);
 assert.deepEqual(panel.components[0].components.map(button=>button.custom_id),[
  'settings_model_11','settings_model_12','settings_model_13','settings_model_14','settings_model_15'
 ]);
 assert.equal(panel.components[0].components[0].label,'✓ iPhone 11');
 assert.equal(panel.components[0].components[2].label,'iPhone 13');
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
