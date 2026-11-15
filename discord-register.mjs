// Registers the application-wide command list; requires DISCORD_BOT_TOKEN.
const text=(name,description)=>({type:3,name,description,required:true});
const integer=(name,description,required=false)=>({type:4,name,description,required,min_value:0,max_value:100000});
const commands=[
 {name:'ustawienia',description:'Pokaż filtry monitora'},
 {name:'modele',description:'Zmień modele iPhone',options:[text('lista','Np. 11 12 13 14 15')]},
 {name:'lokalizacja',description:'Zmień miasto i promień',options:[text('miasto','Nazwa miasta, np. Bielsko-Biała'),{...integer('promien','Promień w kilometrach',true),choices:[0,2,5,10,15,30,50,75,100,150,200].map(n=>({name:String(n),value:n}))}]},
 {name:'cena',description:'Zmień ceny; brak maksimum usuwa górny limit',options:[integer('minimum','Cena minimalna'),integer('maksimum','Cena maksymalna')]},
 {name:'pauza',description:'Wstrzymaj alerty'}, {name:'start',description:'Wznów alerty'}
].map(c=>({...c,type:1,default_member_permissions:null}));
const token=process.env.DISCORD_BOT_TOKEN;
if(!token)throw Error('Brak sekretu DISCORD_BOT_TOKEN.');
const headers={Authorization:`Bot ${token}`,'Content-Type':'application/json'};
const info=await fetch('https://discord.com/api/v10/oauth2/applications/@me',{headers});
if(!info.ok)throw Error(`Nie można zweryfikować tokenu bota: HTTP ${info.status}`);
const identity=await info.json();
const owner=identity.team?.owner_user_id||identity.owner?.id;
if(!identity.id||!owner)throw Error('Nie można ustalić ID aplikacji lub jej właściciela.');
const r=await fetch(`https://discord.com/api/v10/applications/${identity.id}/commands`,{method:'PUT',headers,body:JSON.stringify(commands)});
if(!r.ok)throw Error(`Rejestracja nieudana: HTTP ${r.status}`);
const registered=await r.json();
console.log(`Zarejestrowano ${registered.length} komend globalnych: ${registered.map(c=>c.name).join(', ')}`);
console.log(`OWNER_ID=${owner}`);
