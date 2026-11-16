// Credentials stay in encrypted runtime environment variables, never in this source.
export async function relay(request,env){
 const url=new URL(request.url),national=url.pathname==='/relay/polska',reply=url.pathname==='/reply-ingest';
 if(!national&&!reply)return null;
 const key=national?env.SETTINGS_KEY:env.REPLY_CLIENT_TOKEN;
 if(!key||request.headers.get('Authorization')!==`Bearer ${key}`)return Response.json({error:'Unauthorized'},{status:401});
 if(request.method!=='POST')return Response.json({error:'Method not allowed'},{status:405});
 const text=await request.text();if(text.length>12000)return Response.json({error:'Too large'},{status:413});
 let data;try{data=JSON.parse(text);}catch{return Response.json({error:'Invalid JSON'},{status:400});}
 let payload;
 if(national){
  if(!Array.isArray(data.embeds)||data.embeds.length!==1||!data.embeds[0].url?.startsWith('https://www.olx.pl/'))return Response.json({error:'Invalid alert'},{status:400});
  payload={content:'',embeds:data.embeds,components:data.components||[],allowed_mentions:{parse:[]}};
 }else{
  let ad;try{ad=new URL(data.url);}catch{}
  if(!ad||ad.protocol!=='https:'||!['www.olx.pl','olx.pl'].includes(ad.hostname)||!ad.pathname.startsWith('/d/oferta/')||typeof data.message!=='string'||data.message.length>2000||typeof data.eventId!=='string'||!/^[-a-zA-Z0-9:]{8,160}$/.test(data.eventId))return Response.json({error:'Invalid reply'},{status:400});
  const eventKey='reply:'+data.eventId;
  if(await env.SETTINGS.get(eventKey))return Response.json({ok:true,duplicate:true});
  payload={content:'',embeds:[{title:data.accepted===true?'✅ Sprzedawca prawdopodobnie akceptuje propozycję':'💬 Nowa odpowiedź sprzedawcy',url:ad.href,description:data.message,color:data.accepted===true?0x2ecc71:0x5865f2,footer:{text:'Sprawdź rozmowę na OLX. To nie jest potwierdzenie zawarcia transakcji.'}}],allowed_mentions:{parse:[]}};
 }
 const target=national?env.DISCORD_NATIONAL_WEBHOOK_URL:env.DISCORD_REPLY_WEBHOOK_URL;
 if(!target)return Response.json({error:'Destination not configured'},{status:503});
 const response=await fetch(target+'?with_components=true',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 if(!response.ok)return Response.json({error:'Discord delivery failed'},{status:502});
 if(reply)await env.SETTINGS.put('reply:'+data.eventId,String(Date.now()));
 return Response.json({ok:true},{headers:{'Cache-Control':'no-store'}});
}
