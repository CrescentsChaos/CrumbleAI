/* ---------- history keeper + conversation dynamics: what the page adds ---------- */
const dynCfg=()=>({on:U.dyn!==0,level:U.dyn??2,greet:U.greetH??6});
/* the older history the keeper holds for this chat (read-only: it is built from the chat, so editing the chat rebuilds it) */
function keepHtml(st,n){const k=st&&st.keep;if(!k||!(k.events?.length||k.chapters?.length||k.long||Object.keys(k.bonds||{}).length))
 return`<details><summary>Older history the keeper holds</summary><p class=small>Long chats are folded down automatically. Promises, secrets, gifts, injuries, key moments and the people ${esc(n)} hears about are kept here word for word and never folded away. It fills in as the chat grows.</p>${keepFresh()}</details>`;
 const nm=e=>esc(String(e.t||'').replace(/\{\{user\}\}/g,uname()).replace(/\{\{char\}\}/g,n));
 const ev=(k.events||[]).slice(-30).map(e=>`<div class=tl><b>${esc(e.k)}</b> · ${nm(e)}</div>`).join('');
 const bo=Object.values(k.bonds||{}).sort((a,b)=>b.n-a.n).slice(0,10).map(b=>`<div class=tl><b>${esc(b.name)}</b> · ${esc(b.owner=='char'?n:uname())}'s ${esc(b.rel)}${b.was?` (once ${esc(b.was)})`:''} · mentioned ${b.n}×</div>`).join('');
 const ch=[...(k.long?[{t:k.long,a:0,b:0,long:1}]:[]),...(k.chapters||[])].map(c=>`<div class=tl><b>${c.long?'A long time ago':'Earlier'}</b> · ${esc(c.t)}</div>`).join('');
 return`<details><summary>Older history the keeper holds (${(k.events||[]).length} key moments)</summary><p class=small>Folded-down older chapters, the moments that really happened and the people involved. This is carried into the prompt (the relevant part, for each message).</p>${keepFresh()}${bo?`<label>People and relationships</label>${bo}`:''}${ev?`<label>Key moments</label>${ev}`:''}${ch?`<label>Older chapters</label>${ch}`:''}</details>`}
const keepFresh=()=>`<label><input type=checkbox data-m=fresh ${chat?.cfg?.fresh?'checked':''}> Fresh start: this chat ignores earlier chats with this character</label>`;
/* the character speaks first when you come back after a long absence (Settings > Greet me when I come back) */
function greetCheck(){if(!U.greetH||G||!chat||!cur?.id||!S.loaded||ctl||rounding||document.hidden||($('#chat')&&$('#chat').hidden))return;
 const ic=hist.filter(m=>!m.ooc),l=ic.at(-1);if(!l||ic.length<2||!l.ts)return;
 if(Date.now()-l.ts<U.greetH*36e5||chat.cfg.greeted===l.ts)return;if(isDead?.(cur.id))return;
 chat.cfg.greeted=l.ts;saveChat();gen('nudge',undefined,{reason:'return'})}
