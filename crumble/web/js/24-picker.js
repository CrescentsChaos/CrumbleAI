/* ---------- searchable people picker (js/24-picker.js) ----------
   Used for the members of a place, the members of a group chat and the "chat here with..." box on a place card.
   It never lists everyone: the chosen people are small chips (the first few, "+N" for the rest) and the rest are found by typing,
   six matches at a time. mpMount(host, key, {sel, pool, placeholder, max, hint, onChange, pick}); with `pick` it is a one-shot chooser. */
const MP={},MP_SHOW=6,MP_CHIPS=8;
const mpPool=k=>(MP[k].pool()||[]).filter(x=>x&&x.id);
const mpFind=(k,id)=>mpPool(k).find(x=>x.id==id);
const mpAv=x=>x.group?`<div class="av sm" style="background:${grad(x.name)}">👥</div>`:avatar(x,'sm');
function mpMount(host,k,o){const h=typeof host=='string'?$(host):host;if(!h)return;
 MP[k]={max:99,placeholder:'Search by name or tag…',...o,sel:[...(o.sel||[])],q:'',all:false,hot:0,h};h.dataset.mpk=k;
 h.innerHTML=`<div class=mp><div class=mp-sel></div><label class=mp-find>${ico('search')}<input class=mp-in autocomplete=off spellcheck=false placeholder="${at(MP[k].placeholder)}" aria-label="${at(MP[k].placeholder)}"></label><div class=mp-res hidden></div><div class="small mp-hint"></div></div>`;
 if(!h._mp){h._mp=1;
  h.addEventListener('input',e=>{if(!e.target.classList.contains('mp-in'))return;const m=MP[h.dataset.mpk];m.q=e.target.value;m.hot=0;mpRes(h.dataset.mpk)});
  h.addEventListener('focusin',e=>{if(e.target.classList.contains('mp-in'))mpRes(h.dataset.mpk)});
  h.addEventListener('keydown',e=>{if(!e.target.classList.contains('mp-in'))return;const kk=h.dataset.mpk,m=MP[kk],n=h.querySelectorAll('.mp-it').length;
   if(e.key=='ArrowDown'||e.key=='ArrowUp'){e.preventDefault();if(n){m.hot=(m.hot+(e.key=='ArrowDown'?1:n-1))%n;mpRes(kk,true)}}
   else if(e.key=='Enter'){e.preventDefault();const it=h.querySelectorAll('.mp-it')[m.hot];if(it)mpAdd(kk,it.dataset.mpadd)}
   else if(e.key=='Escape')h.querySelector('.mp-res').hidden=true;
   else if(e.key=='Backspace'&&!e.target.value&&m.pick==null&&m.sel.length)mpRemove(kk,m.sel[m.sel.length-1])});
  h.addEventListener('click',e=>{const kk=h.dataset.mpk;let b=e.target.closest('[data-mpadd]');if(b)return mpAdd(kk,b.dataset.mpadd);
   b=e.target.closest('[data-mprm]');if(b)return mpRemove(kk,b.dataset.mprm);if(e.target.closest('[data-mpall]')){MP[kk].all=!MP[kk].all;mpChips(kk)}})}
 mpChips(k)}
function mpChips(k){const m=MP[k];if(!m||!m.h.isConnected&&!document.contains(m.h))return;const box=m.h.querySelector('.mp-sel'),pool=mpPool(k);if(!box)return;
 if(m.pick){box.hidden=true;m.h.querySelector('.mp-hint').textContent=m.hint||'';return}
 const ids=m.sel.filter(id=>mpFind(k,id)),show=m.all?ids:ids.slice(0,MP_CHIPS);m.sel=ids;
 box.innerHTML=(ids.length?show.map(id=>{const x=mpFind(k,id);return`<span class=mp-chip>${mpAv(x)}<b>${esc(x.name||'(unnamed)')}</b><button type=button data-mprm="${at(id)}" title="Remove" aria-label="Remove ${at(x.name)}">${ico('close')}</button></span>`}).join('')+
  (ids.length>MP_CHIPS?`<button type=button class=mp-more data-mpall=1>${m.all?'Show fewer':`+${ids.length-MP_CHIPS} more`}</button>`:''):`<span class=small>${esc(m.empty||'No one yet')}</span>`);
 m.h.querySelector('.mp-hint').textContent=(m.hint?m.hint+' ':'')+(ids.length?`${ids.length} ${ids.length==1?'person':'people'} chosen.`:'')+(pool.length?'':' Make some characters first.')}
function mpRes(k,keep){const m=MP[k],res=m.h.querySelector('.mp-res'),q=(m.q||'').trim().toLowerCase(),words=q.split(/\s+/).filter(Boolean);
 let list=mpPool(k).filter(x=>m.pick||!m.sel.includes(x.id));
 if(words.length)list=list.filter(x=>{const t=[x.name,x.tags,x.sub].join(' ').toLowerCase();return words.every(w=>t.includes(w))});
 const rank=x=>{const n=(x.name||'').toLowerCase();return n==q?0:n.startsWith(q)?1:n.split(/\s+/).some(w=>w.startsWith(words[0]||''))?2:3};
 list.sort((a,b)=>(m.prefer?(m.prefer.includes(b.id)-m.prefer.includes(a.id)):0)||(words.length?rank(a)-rank(b):0)||(a.name||'').localeCompare(b.name||''));
 const shown=list.slice(0,MP_SHOW);m.hot=Math.min(m.hot,Math.max(0,shown.length-1));
 res.innerHTML=shown.length?shown.map((x,i)=>`<button type=button class="mp-it${i==m.hot?' hot':''}" data-mpadd="${at(x.id)}">${mpAv(x)}<span><b>${esc(x.name||'(unnamed)')}</b><small>${esc(x.sub||x.tags||'')}</small></span><i>${m.pick?'':ico('plus')}</i></button>`).join('')+
  (list.length>shown.length?`<div class=mp-foot>${list.length-shown.length} more. Keep typing to narrow it down.</div>`:''):`<div class=mp-foot>${q?'No match for “'+esc(m.q.trim())+'”.':(mpPool(k).length?'Everyone is already here.':'Nothing to choose yet.')}</div>`;
 res.hidden=false;if(keep)res.querySelector('.hot')?.scrollIntoView({block:'nearest'})}
function mpAdd(k,id){const m=MP[k];if(!m||!mpFind(k,id))return;
 if(m.pick){m.h.querySelector('.mp-res').hidden=true;m.h.querySelector('.mp-in').value='';m.q='';return m.pick(id)}
 if(m.sel.includes(id))return;if(m.sel.length>=m.max){m.h.querySelector('.mp-hint').textContent=`That is the limit (${m.max}).`;return}
 m.sel.push(id);m.q='';const i=m.h.querySelector('.mp-in');i.value='';mpChips(k);mpRes(k);i.focus();m.onChange&&m.onChange([...m.sel])}
function mpRemove(k,id){const m=MP[k];if(!m)return;m.sel=m.sel.filter(x=>x!=id);mpChips(k);if(!m.h.querySelector('.mp-res').hidden)mpRes(k);m.onChange&&m.onChange([...m.sel])}
const mpSelected=k=>MP[k]?[...MP[k].sel]:[];
document.addEventListener('mousedown',e=>{document.querySelectorAll('.mp-res').forEach(r=>{if(!r.hidden&&!r.closest('.mp').contains(e.target))r.hidden=true})});
/* every character as a pool entry (the Narrator is not a person you can place) */
const mpChars=()=>(S.chars||[]).map(c=>({...c,sub:(c.tags||'').split(',').slice(0,3).join(' · ')}));
