// Fragment-only form: no prices, drafts or listing links are sent to this server.
export default String.raw`<!doctype html>
<html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>Propozycja ceny • iPhone Sniper</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#14171c;color:#f5f7fa;font:17px/1.5 system-ui,sans-serif;padding:28px 18px}main{max-width:580px;margin:25px auto;background:#20252d;border:1px solid #353e4a;border-left:5px solid #2ecc71;border-radius:20px;padding:28px}h1{font-size:28px;margin:6px 0 12px}p{color:#b8c2ce}.tag{color:#59df98;font-size:13px;font-weight:700;letter-spacing:1px}label{display:block;font-weight:650;margin:22px 0 8px}input,textarea{width:100%;background:#14191f;border:1px solid #516073;border-radius:10px;padding:13px;color:white;font:inherit}input:focus,textarea:focus{outline:2px solid #2ecc71}textarea{min-height:135px;resize:vertical}button,a.action{display:block;width:100%;border:0;border-radius:10px;padding:14px;text-align:center;font:700 17px system-ui;cursor:pointer;margin-top:14px;text-decoration:none}button{background:#2ecc71;color:#072414}a.action{background:#354151;color:#fff}button:disabled{opacity:.5;cursor:default}.small{font-size:14px}.error{color:#ff9a9a}#status{min-height:25px;margin-bottom:0}footer{text-align:center;color:#7f8c9e;font-size:13px}a[hidden]{display:none}
</style>
<main><div class="tag">IPHONE SNIPER</div><h1>💬 Zaproponuj cenę</h1><p>Zmień kwotę, skopiuj wiadomość i wklej ją w rozmowie ze sprzedawcą na OLX.</p>
<label for="price">Twoja propozycja (zł)</label><input id="price" inputmode="decimal" autocomplete="off" placeholder="Wpisz kwotę"><p id="hint" class="small"></p>
<label for="message">Wiadomość do sprzedawcy</label><textarea id="message" maxlength="2000"></textarea>
<button id="copy" disabled>Kopiuj wiadomość</button><a id="open" class="action" hidden target="_blank" rel="noopener noreferrer">Otwórz ogłoszenie OLX ↗</a><p id="status" role="status" aria-live="polite"></p><p class="small">Wysyłasz wiadomość samodzielnie na OLX. Propozycja nie uwzględnia napraw, prowizji ani transportu.</p></main><footer>Kwota i treść pozostają w Twojej przeglądarce.</footer>
<script>
const price=document.querySelector('#price'),message=document.querySelector('#message'),copy=document.querySelector('#copy'),open=document.querySelector('#open'),status=document.querySelector('#status'),hint=document.querySelector('#hint');
const params=new URLSearchParams(location.hash.slice(1));
function amount(value){const s=value.trim().replace(',','.');if(!/^\d{1,6}(\.\d{1,2})?$/.test(s))return null;const n=Number(s);return n>0&&n<=100000?n:null;}
let validUrl=false;
try{const url=new URL(params.get('url'));if(url.protocol==='https:'&&['olx.pl','www.olx.pl'].includes(url.hostname)&&!url.username&&!url.password&&!url.port&&url.pathname.startsWith('/d/oferta/')){url.search='';url.hash='';open.href=url.href;open.hidden=false;validUrl=true;}}catch{}
const initial=amount(params.get('price')||'');
if(initial!==null){price.value=initial.toLocaleString('pl-PL',{useGrouping:false,maximumFractionDigits:2});hint.textContent='Domyślnie: najniższa cena tego wariantu w Twojej tabeli minus 200 zł.';}else{hint.textContent='Brak pewnej ceny modelu i pamięci w tabeli. Wpisz własną propozycję.';}
function update(){const n=amount(price.value);price.setAttribute('aria-invalid',String(n===null));message.value=n===null?'':'Cześć, czy sprzedaż za '+n.toLocaleString('pl-PL',{useGrouping:false,maximumFractionDigits:2})+' zł wchodzi w grę?';copy.disabled=!validUrl||n===null;status.textContent=validUrl?(n===null?'Wpisz kwotę od 0,01 do 100 000 zł.':''):'Nieprawidłowy link. Otwórz formularz przyciskiem z alertu.';status.className=(!validUrl||n===null)?'error small':'small';}
price.addEventListener('input',update);message.addEventListener('input',()=>{copy.disabled=!validUrl||amount(price.value)===null||!message.value.trim();});
copy.addEventListener('click',async()=>{if(copy.disabled)return;try{await navigator.clipboard.writeText(message.value);status.textContent='Skopiowano. Otwórz OLX i wklej wiadomość.';}catch{message.focus();message.select();status.textContent='Przytrzymaj zaznaczoną wiadomość i wybierz Kopiuj.';}});update();
</script></html>`;
