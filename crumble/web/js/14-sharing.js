/* ---------- hosting panel (host only) ---------- */
async function renderShare(force){if(S.role!='admin')return;const box=$('#sharebox');
 if(!force&&box.contains(document.activeElement)&&document.activeElement.tagName=='INPUT')return;
 const r=await api('/api/share');if(r.err)return;const ago=t=>{const s=Date.now()/1000-t;return s<90?'online now':s<3600?Math.round(s/60)+' min ago':s<86400?Math.round(s/3600)+' h ago':Math.round(s/86400)+' d ago'};
 box.innerHTML=`<details open><summary>🌐 Share with others</summary>`+(!r.listen?
  `<p class=small>Right now Crumble only listens on this PC. To let friends use your AI, close it and start it with <b>python Crumble.py --share</b> (or double-click <b>Share.bat</b> on Windows, <b>share.sh</b> on Mac/Linux). They open your link, enter the password, and chat. Your model stays on your PC.</p>`:
  `<div class=row><b>${r.on?'🟢 Guests can join':'⚪ Sharing is paused'}</b><button class="${r.on?'x':'go'}" data-sh=toggle>${r.on?'Stop sharing':'Start sharing'}</button></div>
  <label>Link for guests (same Wi-Fi / network)</label>${r.urls.map(u=>`<div class=fact><input readonly value="${at(u)}"><button data-sh=copy data-v="${at(u)}">Copy</button></div>`).join('')||'<p class=small>No network address found.</p>'}
  <label>Password (empty = anyone with the link can join)</label><div class=fact><input id=shpw value="${at(r.password)}"><button data-sh=setpw>Save</button><button data-sh=regen>Random</button></div>
  <label>Most guests at once</label><input type=number id=shmax min=1 max=100 value=${r.max} data-sh=max>
  <label>Guests (${r.guests.length}) · ${r.queue?r.queue+' waiting for the AI':'AI is free'}</label>
  ${r.guests.map(g=>`<div class=fact><input readonly value="${at(g.name)} · ${ago(g.seen)}${g.busy?' · generating':''}"><button class=x data-sh=kick data-v=${g.uid}>Kick</button></div>`).join('')||'<p class=small>Nobody has joined yet.</p>'}
  ${r.guests.length?'<div class=row><button class=x data-sh=kickall>Kick everyone</button></div>':''}
  <details><summary>Playing over the internet</summary><p class=small>Same Wi-Fi works as is. For friends elsewhere, the safest way is a tunnel such as <b>cloudflared</b> (<code>cloudflared tunnel --url http://localhost:8000</code>) or <b>ngrok</b>: you get an https link to send them and no router setup. Port-forwarding also works but is plain http, so use a strong password. Everyone shares one model, so replies queue up; guests can chat and keep their own private chats, but cannot load models, edit characters or see character secrets.</p></details>`)+`</details>`}
$('#sharebox').onclick=async e=>{const b=e.target.closest('button'),k=b?.dataset.sh;if(!k)return;let body=null;
 if(k=='copy'){navigator.clipboard?.writeText(b.dataset.v);b.textContent='Copied';return}
 if(k=='toggle')body={on:!(b.textContent=='Stop sharing')};else if(k=='setpw')body={password:$('#shpw').value};else if(k=='regen')body={regen:1};
 else if(k=='kick')body={kick:b.dataset.v};else if(k=='kickall'){if(!confirm('Kick all guests?'))return;body={kick:'all'}}
 const r=await api('/api/share','POST',body);if(r.err)alert(r.err);renderShare(true)};
$('#sharebox').onchange=async e=>{if(e.target.dataset.sh=='max'){await api('/api/share','POST',{max:+e.target.value});renderShare(true)}};
setInterval(()=>{if(S&&S.role=='admin'&&!$('#samp').hidden)renderShare()},4000);
