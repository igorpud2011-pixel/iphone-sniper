// Run once locally with DISCORD_BOT_TOKEN, DISCORD_APP_ID and DISCORD_GUILD_ID.
const text=(name,description)=>({type:3,name,description,required:true});
const integer=(name,description,required=false)=>({type:4,name,description,required,min_value:0,max_value:100000});
const commands=[
 {name:'ustawienia',description:'Pokaż filtry monitora'},
 {name:'modele',description:'Zmień modele iPhone',options:[text('lista','Np. 11 12 13 14 15')]},
 {name:'lokalizacja',description:'Zmień miasto i promień',options:[text('miasto','Nazwa miasta, np. Bielsko-Biała'),{...integer('promien','Promień w kilometrach',true),choices:[0,2,5,10,15,30,50,75,100,150,200].map(n=>({name:String(n),value:n}))}]},
 {name:'cena',description:'Zmień ceny; brak maksimum usuwa górny limit',options:[integer('minimum','Cena minimalna'),integer('maksimum','Cena maksymalna')]},
 {name:'pauza',description:'Wstrzymaj alerty'}, {name:'start',description:'Wznów alerty'}
].map(c=>({...c,type:1,default_member_permissions:'0'}));
const {DISCORD_BOT_TOKEN:token,DISCORD_APP_ID:app,DISCORD_GUILD_ID:guild}=process.env;
if(!token||!/^\d+$/.test(app||'')||!/^\d+$/.test(guild||''))throw Error('Brak tokenu lub ID aplikacji/serwera w zmiennych środowiskowych.');
const r=await fetch(`https://discord.com/api/v10/applications/${app}/guilds/${guild}/commands`,{method:'PUT',headers:{Authorization:`Bot ${token}`,'Content-Type':'application/json'},body:JSON.stringify(commands)});
if(!r.ok)throw Error(`Rejestracja nieudana: HTTP ${r.status}`);
console.log('Zarejestrowano komendy. Dostęp wymaga uprawnień administratora; endpoint dodatkowo sprawdza OWNER_ID.');
