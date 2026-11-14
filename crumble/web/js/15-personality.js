/* ---------- personality engine: request options, profile preview, memory section, score badge ---------- */
function persCfg(){return{on:!!U.pers,depth:U.persDepth,guard:!!U.persGuard,dyn:!!U.persDyn,canon:!!U.persCanon}}
function persBadge(p){const s=p.score,c=s>=80?'ok':s>=65?'':'low';
 return`<span class="pscore ${c}" title="${at((p.flags||[]).join('; ')||'sounds like them')}">voice ${s}${p.retries?' ↻':''}</span>`}
async function persProfile(char,cid){if(S.role=='guest')return null;
 try{const r=await api('/api/personality','POST',cid?{cid}:{char});return r&&!r.err?r:null}catch(e){return null}}
function persBars(p){return p.traits.map(t=>{const why=t.src=='set'?'set by you':t.ev.length?'read from: '+t.ev.join(', '):t.src=='derived'?'follows from the other traits':'nothing in the sheet';
 return`<div class=pt title="${at(why)}"><span>${esc(t.label)}</span><div class=pbar><i style="width:${t.v}%"></i></div><b>${t.v}</b><small>${t.src}</small></div>`}).join('')}
function persTags(p){const t=[];(p.triggers||[]).forEach(x=>t.push(`<span title="sets them off">⚡ ${esc(x)}</span>`));(p.comforts||[]).forEach(x=>t.push(`<span title="comforts them">♡ ${esc(x)}</span>`));
 return t.length?`<div class=ptags>${t.join('')}</div>`:''}
function persView(p){return p?`<div class=psum>${esc(p.summary)||'No strong traits found yet. Describe them in Personality, Flaws or Quirks, or set numbers in Traits.'}</div>${persBars(p)}${persTags(p)}`:'<p class=small>Profile unavailable.</p>'}

/* character editor: live preview of what the engine reads from the sheet */
function persForm(){return`<details><summary>Personality profile (what the engine reads from this sheet)</summary><p class=small>Updates as you type. Set numbers in Traits to override anything it guesses.</p><div id=pprev><p class=small>Reading…</p></div></details>`}
let pTimer=0;
async function persPreview(){const el=$('#pprev');if(!el)return;if(S.role=='guest'){el.innerHTML='';return}
 const p=await persProfile(collect());if($('#pprev')===el)el.innerHTML=persView(p)}
$('#form').addEventListener('input',e=>{if(e.target.dataset.k&&$('#pprev')){clearTimeout(pTimer);pTimer=setTimeout(persPreview,700)}});

/* memory tab: profile, grudge, what they have said about themselves, consistency over time */
function persIds(){return G?gmem().filter(c=>c.id!='__narrator__').map(c=>[c.id,c.name]):(cur?.id?[[cur.id,cur.name||'Character']]:[])}
function persSt(id){const s=G?mst(id):chat.state;return s.pers=s.pers||{}}
function persSpark(d){if(!d.length)return'<p class=small>No replies scored yet.</p>';
 const w=300,h=46,x=i=>d.length<2?w/2:6+i*(w-12)/(d.length-1),y=s=>h-4-(h-8)*s/100;
 return`<svg class=pspark viewBox="0 0 ${w} ${h}" preserveAspectRatio=none><line x1=0 x2=${w} y1=${y(65)} y2=${y(65)}></line><polyline points="${d.map((p,i)=>x(i)+','+y(p.score)).join(' ')}"></polyline></svg>`}
function persMem(){const f=$('#memf');if(!f||!chat?.state)return;
 const ids=persIds();if(!ids.length)return;
 let h=`<details open id=persmem><summary>Personality${U.pers?'':' (engine is off in Settings)'}</summary>`;
 for(const[id,name]of ids){const p=persSt(id),canon=p.canon||[],drift=p.drift||[],last=drift.at(-1);
  h+=`<div data-pc=${id}>${G?`<label><b>${esc(name)}</b></label>`:''}<div class=pprof data-pid=${id}>${S.role=='guest'?'':'<p class=small>Reading…</p>'}</div>
  ${p.grudge>=.15?`<label>Still bothered by how you treated them: <b>${Math.round(p.grudge*100)}%</b></label><div class=meter style="width:100%"><i style="width:${p.grudge*100}%"></i></div>`:''}
  <label>Established about ${esc(name)} (they said it earlier; the engine keeps them consistent with it)</label>
  ${canon.map((x,i)=>`<div class=pcanon><input data-pm=canon data-c=${id} data-i=${i} value="${at(x)}"><button class=x data-pm=delcanon data-c=${id} data-i=${i}>✕</button></div>`).join('')||'<p class=small>Nothing yet. Durable things they say about themselves are collected here.</p>'}
  <div class=row><input data-pnew=${id} placeholder="Add a fact about them…"><button data-pm=addcanon data-c=${id}>Add</button></div>
  <label>Consistency of recent replies${last?`: <b>${last.score}/100</b>${last.flags?.length?' · '+esc(last.flags[0]):''}`:''}</label>${persSpark(drift)}
  <div class=row><button class=x data-pm=settle data-c=${id}>Settle mood and forget the grudge</button></div></div>`}
 f.insertAdjacentHTML('beforeend',h+'</details>');
 if(S.role!='guest')ids.forEach(async([id])=>{const el=f.querySelector(`.pprof[data-pid="${id}"]`);if(!el)return;
  const src=G?gmem().find(c=>c.id==id):cur;el.innerHTML=persView(await persProfile(null,src?.id))})}
$('#memf').addEventListener('input',e=>{const t=e.target;if(t.dataset.pm!='canon'||!chat?.state)return;persSt(t.dataset.c).canon[+t.dataset.i]=t.value;saveSoon()});
$('#memf').addEventListener('click',e=>{const b=e.target.closest('button'),k=b?.dataset.pm;if(!k||!chat?.state)return;const p=persSt(b.dataset.c);
 if(k=='delcanon')(p.canon=p.canon||[]).splice(+b.dataset.i,1);
 else if(k=='addcanon'){const i=$('#memf').querySelector(`[data-pnew="${b.dataset.c}"]`),v=i?.value.trim();if(!v)return;(p.canon=p.canon||[]).push(v)}
 else if(k=='settle'){Object.assign(p,{va:null,grudge:0,frac:0,mood:null});const s=G?mst(b.dataset.c):chat.state;Object.assign(s,{mood:'neutral',emoji:'😐',energy:'medium'})}
 else return;saveSoon();head();renderMem()});
