/* ---------- hierarchical memory: short-term, episodic, semantic, emotional ---------- */
const memCfg=()=>({on:!!U.mem,depth:U.memDepth,learn:!!U.memLearn});
const MLAY=[['episodic','📖','Episodic','what happened between you'],['semantic','📌','Semantic','lasting facts about you, them and your bond'],['emotional','💭','Emotional','how it felt']];
const MIMP=[[.3,'Minor'],[.5,'Normal'],[.75,'Important'],[.9,'Core']];
const blankMem=()=>({v:1,seq:0,turn:0,scene:'',recent:[],items:[],legacy:false});
const memS=cid=>cid?mst(cid):chat.state;
const memSt=cid=>{const s=memS(cid);return s.mem&&Array.isArray(s.mem.items)?s.mem:(s.mem=blankMem())};
const cname=cid=>cid?(memberById(cid)?.name||'Character'):(cur?.name||'Character');
const mres=(t,cid)=>String(t||'').split('{{user}}').join(uname()).split('{{char}}').join(cname(cid));
function mph(t,cid){let s=String(t||'').trim();
 for(const[n,p]of[[uname(),'{{user}}'],[cname(cid),'{{char}}']])for(const x of new Set([n,n.split(' ')[0]]))if(x.length>1)
  s=s.replace(new RegExp('(^|[^\\w{])'+x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?![\\w}])','g'),'$1'+p);
 return s}
const memFacts=m=>m.items.filter(i=>i.t=='semantic'&&(i.subj||'user')=='user').sort((a,b)=>(a.ts||0)-(b.ts||0)).slice(-40).map(i=>i.text);
const memSync=cid=>{memS(cid).facts=memFacts(memSt(cid))};
function undoMem(u,cid){const s=memS(cid),m=s.mem;if(!m||!Array.isArray(m.items))return;
 m.items=m.items.filter(i=>!(u.add||[]).includes(i.id));m.scene=u.scene||'';m.recent=u.recent||[];s.facts=memFacts(m)}
const memUsed=cid=>(([...hist].reverse().find(m=>m.role=='assistant'&&m.recalled&&(!cid||m.cid==cid)))||{}).recalled||[];
function memRow(i,cid,used){
 const near=MIMP.reduce((a,b)=>Math.abs(b[0]-(i.imp??.5))<Math.abs(a[0]-(i.imp??.5))?b:a)[0];
 const emo=i.t=='emotional'&&i.emo?`<span class=memo title="${at(i.emo)}">${S.emo?.[i.emo]||'💭'}</span>`:'';
 return`<div class="mrow${used?' used':''}" data-id="${i.id}" data-c="${cid}">${used?'<span title="used in the last reply">🔎</span>':''}${emo}`+
  `<input data-mm=text value="${at(mres(i.text,cid))}"><select data-mm=imp title="Importance">${MIMP.map(([v,l])=>`<option value=${v} ${v==near?'selected':''}>${l}</option>`).join('')}</select>`+
  `<button class=x data-mm=pin title="${i.pin?'Pinned: always kept in mind':'Pin: always keep in mind'}">${i.pin?'📌':'📍'}</button><button class=x data-mm=del title="Forget this">✕</button></div>`}
function memHtml(st,name,cid){
 const m=memSt(cid),used=new Set(memUsed(cid)),recent=(m.recent||[]).slice(-4);
 let h=`<details open class=mlay><summary>🧠 Memory${G?' · '+esc(name):''}</summary>
 <p class=small>Each reply only gets the few memories that matter for what you just said. 🔎 marks what the last reply used.</p>
 <label>⏱ Short-term: the scene right now</label><textarea data-mm=scene data-c="${cid}" rows=2 placeholder="Filled in automatically after each reply">${esc(mres(m.scene,cid))}</textarea>
 ${recent.length?`<div class=mchips>${recent.map(r=>`<span title="${at(mres(r.text,cid))}">${esc(mres(r.text,cid))}</span>`).join('')}</div>`:''}`;
 for(const[t,ic,ti,hint]of MLAY){
  const items=m.items.filter(i=>i.t==t).sort((a,b)=>(b.ts||0)-(a.ts||0)||(b.turn||0)-(a.turn||0));
  h+=`<label>${ic} ${ti} (${items.length}) <small>${hint}</small></label>`+(items.slice(0,30).map(i=>memRow(i,cid,used.has(i.id))).join('')||'<p class=small>Nothing yet.</p>')+
   (items.length>30?`<p class=small>+ ${items.length-30} older ones not shown</p>`:'')+
   `<div class=row><input data-mmnew=${t} data-c="${cid}" placeholder="Add a ${t} memory…"><button data-mm=add data-t=${t} data-c="${cid}">Add</button></div>`}
 return h+`<label>🔎 Try a message: what would be recalled?</label><div class=row><input data-mmq data-c="${cid}" placeholder="e.g. Do you still have the necklace?"><button data-mm=test data-c="${cid}">Test</button></div>
 <div class=mtest data-mtest="${cid}"></div>
 <div class=row><button data-mm=build data-c="${cid}">Build memories from this chat</button><button class=x data-mm=wipe data-c="${cid}">Forget all</button><span class=small data-mstat="${cid}"></span></div></details>`}
const memRowOf=t=>{const r=t.closest('.mrow');if(!r||!chat?.state)return null;const cid=r.dataset.c||'',m=memSt(cid);return{r,cid,m,i:m.items.find(x=>x.id==r.dataset.id)}};
$('#memf').addEventListener('input',e=>{const t=e.target,k=t.dataset.mm;if(!k||!chat?.state)return;
 if(k=='scene'){memSt(t.dataset.c||'').scene=mph(t.value,t.dataset.c||'');saveSoon();return}
 const o=k=='text'&&memRowOf(t);if(o?.i&&t.value.trim()){o.i.text=mph(t.value,o.cid);o.i.src='edited';memSync(o.cid);saveSoon()}});
$('#memf').addEventListener('change',e=>{const t=e.target;if(t.dataset.mm!='imp')return;const o=memRowOf(t);if(o?.i){o.i.imp=+t.value;saveSoon()}});
$('#memf').addEventListener('click',async e=>{const b=e.target.closest('button'),k=b?.dataset.mm;if(!k||!chat?.state)return;
 const o=memRowOf(b),cid=o?o.cid:(b.dataset.c||''),m=memSt(cid),stat=()=>$('#memf').querySelector(`[data-mstat="${cid}"]`);
 if(k=='del'&&o?.i){m.items=m.items.filter(x=>x!==o.i);m.items.forEach(x=>{if(x.link==o.i.id)delete x.link})}
 else if(k=='pin'&&o?.i)o.i.pin=!o.i.pin;
 else if(k=='add'){const t=b.dataset.t,v=$('#memf').querySelector(`[data-mmnew="${t}"][data-c="${cid}"]`)?.value.trim();if(!v)return;
  m.items.push({id:t[0]+'u'+rid().slice(0,5),t,text:mph(v,cid),imp:.6,ts:Date.now(),turn:hist.length,n:0,last:0,pin:false,src:'user',...(t=='semantic'?{subj:'user'}:{})})}
 else if(k=='test'){const q=$('#memf').querySelector(`[data-mmq][data-c="${cid}"]`)?.value.trim(),box=$('#memf').querySelector(`[data-mtest="${cid}"]`);if(!q||!box)return;
  box.textContent='Searching…';const s=memS(cid),r=await api('/api/recall','POST',{name:cname(cid),user:uname(),state:{mem:s.mem,facts:s.facts,mood:s.mood},query:q,turn:hist.length,depth:U.memDepth});
  box.innerHTML=r.err?esc(r.err):r.short.map(x=>`<div class=small>⏱ ${esc(x)}</div>`).join('')+(r.trace.map(t=>`<div class=mt><b>${esc(t.t)}</b> ${esc(t.text)}<small>${esc(t.why)} · relevance ${Math.round(t.rel*100)} · recency ${Math.round(t.rec*100)} · importance ${Math.round(t.imp*100)}</small></div>`).join('')||'<p class=small>Nothing would be added to the prompt for that message.</p>');return}
 else if(k=='build'){if(!S.loaded){stat().textContent='Load a model first.';return}
  b.disabled=true;stat().textContent='Reading the chat… (one model call per important moment)';let added=0,calls=0,err='';
  for(const c of(G?gmem().filter(c=>c.id!='__narrator__'):[cur])){const s=memS(G?c.id:''),r=await api('/api/memorize','POST',{char:apiChar(c),user:uname(),history:apiHist(hist),state:s,mem:memCfg()});
   if(r.err){err=r.err;break}Object.assign(s,r.state);added+=r.added;calls+=r.calls}
  saveSoon();renderMem();const el=$('#memf').querySelector(`[data-mstat="${cid}"]`);if(el)el.textContent=err||`Done: ${added} new ${added==1?'memory':'memories'} (${calls} model calls).`;return}
 else if(k=='wipe'){if(!confirm('Forget every memory in this chat?'))return;memS(cid).mem=blankMem();memS(cid).facts=[]}
 else return;
 memSync(cid);saveSoon();renderMem()});
