/* ---------- mood colours, relationship paths and instant feedback ----------
   Mood: the header, the avatar ring and every message pick up the character's mood colour. The moment you send a message
   the page shows a provisional reaction (no model call: the server reads tone against the character's temperament), and
   replaces it with the tracker's answer a few seconds later.
   Relationships: every character has a path (friendship, partners, master and disciple, rivalry, family or romance) and a
   progress bar that climbs six stages. It moves with how they feel about you; every stage reached is a milestone. */
const MG={warm:['#f5b84b',.7],love:['#f06a8d',.9],calm:['#4fc3b0',.4],curious:['#5aa9f0',.2],drive:['#f58a4b',.5],sad:['#7b8fe0',-.6],fear:['#a583e6',-.5],anger:['#e5534b',-.8],sour:['#92c25c',-.5],flat:['#a09890',0]},MW={};
[['warm','happy joyful excited amused playful smug ecstatic'],['love','affectionate fond grateful passionate flushed'],['calm','relaxed content calm hopeful'],['curious','curious thoughtful surprised skeptical confused serious'],
 ['drive','proud confident determined'],['sad','sad lonely hurt guilty tired sleepy bored'],['fear','nervous anxious worried scared shy flustered embarrassed overwhelmed'],
 ['anger','angry furious annoyed irritated frustrated jealous'],['sour','disgusted']].forEach(([g,w])=>w.split(' ').forEach(x=>MW[x]=g));
const mcol=m=>(MG[MW[m]]||MG.flat)[0],mval=m=>(MG[MW[m]]||MG.flat)[1],ENI={low:.3,medium:.55,high:.9},ENL={low:'Low energy',medium:'Steady',high:'High energy'};
const RC=[10,25,45,65,85,101],RDEF={label:'Getting to know each other',icon:'🌱',color:'#b9a99b',blurb:'',stages:['Strangers','Acquaintances','Familiar','Comfortable','Close','Bonded']};
const rpath=t=>(S.rels&&S.rels[t])||RDEF,stOf=id=>G?mst(id):chat.state,chOf=id=>G?memberById(id):cur;
const isAdult=c=>{const a=String(c?.age||'').toLowerCase(),m=/\d+/.exec(a);return m?+m[0]>=18:!/\b(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen)\b(?!\s+(?:hundred|thousand))|\b(?:minor|child|kid|teen\w*|underage)\b/.test(a)};
let LIVE={},PREV={},PK='',BP={open:false,f:null,view:'one',sel:-1};const PW={},PM={};

/* ---------- relationship data (saved with the chat in chat.rp.rel) ---------- */
const relRec=(id,mk)=>{const rp=chat.rp||(chat.rp={}),m=rp.rel||(rp.rel={});return m[id]||(mk?(m[id]={type:'auto',v:0,ms:[],hist:[],peak:0}):null)};
function relType(id){let t=chat?.rp?.rel?.[id]?.type||'auto';if(!(S.rels&&S.rels[t]))t='auto';if((t=='auto'||t=='romance')&&!isAdult(chOf(id)))t='friend';return t}
const relV=id=>relType(id)=='romance'?(chat.rp?.rom?.[id]?.v||0):(chat.rp?.rel?.[id]?.v||0);
function setRelV(id,v){v=Math.max(0,Math.min(100,Math.round(v*100)/100));if(relType(id)=='romance'){const r=(chat.rp.rom=chat.rp.rom||{});(r[id]=r[id]||{v:0,ms:[]}).v=v}else relRec(id,true).v=v;const r=relRec(id,true);r.peak=Math.max(r.peak||0,v)}
const sIdx=v=>{const i=RC.findIndex(c=>v<c);return i<0?5:i};
function sInfo(id){const t=relType(id),v=relV(id),i=sIdx(v),P=rpath(t),lo=i?RC[i-1]:0,hi=Math.min(RC[i],100);return{t,v,i,P,label:P.stages[i],next:P.stages[i+1]||'',frac:Math.max(0,Math.min(1,(v-lo)/(hi-lo)))}}
/* one exchange: d is the affection change the tracker applied. Kind exchanges build the bond, hurtful ones damage it faster than it grew,
   and a bond never falls below 60% of its peak from words alone. Returns what changed so it can be shown and undone. */
function bondStep(id,d){const t=relType(id),old=relV(id),oi=sIdx(old),r=relRec(id,true),a=stOf(id).affection??50;
 let dv=d>0?1.1*d+(a>=60?.5:.2):d<0?Math.max(-8,1.4*d):(a>=60?.3:.12);if(t=='romance')dv*=.7;
 let nv=Math.max(0,Math.min(100,old+dv));if(dv<0)nv=Math.max(nv,Math.min(old,(r.peak||0)*.6));
 setRelV(id,nv);const nw=relV(id),ni=sIdx(nw),up=ni>oi,P=rpath(t);
 if(up)r.hist=(r.hist||[]).concat({s:P.stages[ni],i:ni,t:Date.now(),ty:t}).slice(-14);
 return{dv:Math.round((nw-old)*100)/100,h:up?1:0,up:up?{id,label:P.stages[ni],P}:null}}
function bondUndo(m){if(!m||!chat)return;
 if(m.bd){const b=m.bd;if(relRec(b.c)){setRelV(b.c,relV(b.c)-b.dv);if(b.h){const h=relRec(b.c).hist||[],k=h.map(x=>x.i>=0).lastIndexOf(true);if(k>=0)h.splice(k,1)}}delete m.bd}
 if(m.rxd){const id=m.cid||cur?.id;if(id&&id!='__narrator__')addAff(id,-m.rxd);delete m.rxd}delete m.mo}
function bondAfterTrack(m,id,r){delete LIVE[id];const d=+r.delta||0,st=stOf(id),b=bondStep(id,d),rec=relRec(id,true);
 m.bd={c:id,dv:b.dv,h:b.h};m.mo={m:st.mood,e:st.emoji,d,f:1};
 if(relType(id)=='auto'&&relV(id)>=45&&!rec.fork&&!rec.forkDone){rec.fork=1;forkToast(id)}
 if(b.up)stageToast(b.up)}
function setRelType(id,t){const from=relType(id);if(from==t||!(S.rels&&S.rels[t])||(t=='romance'&&!isAdult(chOf(id))))return;
 const r=relRec(id,true),rom=(chat.rp.rom=chat.rp.rom||{});
 if(from=='romance')r.v=Math.max(r.v||0,Math.round((rom[id]?.v||0)*.8));   // what grew as romance is not lost when the path changes
 r.type=t;if(t=='romance'){const x=rom[id]||(rom[id]={v:0,ms:[]});x.v=Math.max(x.v,Math.min(30,Math.round((r.v||0)*.5)))}
 if(t=='mentor'&&!r.role)r.role='master';r.fork=0;r.forkDone=1;
 r.hist=(r.hist||[]).concat({s:'Path: '+rpath(t).label,i:-1,t:Date.now(),ty:t}).slice(-14);
 saveSoon();head();bondDraw();if(!$('#mem').hidden)renderMem();fx(rpath(t).icon+' '+rpath(t).label,rpath(t).color)}
function setMood(id,m){const s=stOf(id);s.mood=m;s.emoji=S.emo[m]||'🙂';delete LIVE[id];saveSoon();head();bondDraw()}

/* ---------- what is shown: the real state, or a provisional reaction while the tracker is still reading ---------- */
const focusId=()=>{if(!G)return cur?.id;const l=[...hist].reverse().find(x=>x.role=='assistant'&&x.cid&&x.cid!='__narrator__');return l?l.cid:G.members.find(i=>i!='__narrator__')};
const mids=()=>G?G.members.filter(i=>i!='__narrator__'&&memberById(i)):[cur.id];
function shown(id){const s=stOf(id),L=LIVE[id];return L&&L.mood?{mood:L.mood,emoji:L.emoji,aff:Math.max(0,Math.min(100,s.affection+(L.d||0))),en:L.energy||s.energy,prov:1}:{mood:s.mood,emoji:s.emoji,aff:s.affection,en:s.energy}}
function liveDrop(id,ch,age){const L=LIVE[id];if(!L||(chat!==ch)||Date.now()-L.ts<age)return;delete LIVE[id];const s=shown(id);if(PREV[id]){PREV[id].mood=s.mood;PREV[id].aff=s.aff}head()}
function pop(sel,c='bump'){const e=typeof sel=='string'?$(sel):sel;if(!e)return;e.classList.remove('bump','bumps');void e.offsetWidth;e.classList.add(c)}
function fx(txt,color,anchor){const L=$('#bondfx'),C=$('#chat'),a=$(anchor||'#hchip'),t=a&&!a.hidden&&a.offsetParent?a:$('#hbond');if(!L||!C||!t)return;
 const ar=t.getBoundingClientRect(),cr=C.getBoundingClientRect(),e=document.createElement('div');e.className='bfl';e.textContent=txt;
 e.style.cssText=`left:${ar.left-cr.left+ar.width/2}px;top:${ar.bottom-cr.top+2}px;color:${color||'var(--tx)'}`;L.append(e);setTimeout(()=>e.remove(),1800)}
function toast(cls,color,icon,small,big,sub,id){const L=$('#bondfx');if(!L)return;const e=document.createElement('div');e.className='btoast '+cls;e.style.setProperty('--rc',color);
 e.innerHTML=`<span class=bti>${icon}</span><div><small>${small}</small><b>${big}</b><span>${sub}</span></div>`;e.onclick=()=>{e.remove();bondOpen(id)};L.append(e);
 if(typeof beep=='function')beep(cls=='up'?880:660,.1);setTimeout(()=>{e.classList.add('out');setTimeout(()=>e.remove(),420)},4800)}
const stageToast=u=>toast('up',u.P.color,u.P.icon,'Relationship milestone',esc(u.label),'with '+esc(chOf(u.id)?.name||'them'),u.id);
const forkToast=id=>toast('fork','#f5b84b','✨','Your bond is growing',esc(chOf(id)?.name||'They')+' and you','Choose where it is heading',id);

/* called at the end of head(): colours, chip, relationship pill and the animations for whatever just changed */
function bondHead(){const hr=$('#hrom');if(hr)hr.hidden=true;const C=$('#chat'),hb=$('#hbond');
 if(!chat||!cur||!S||!hb){if(hb)hb.hidden=true;return}
 const key=(G?G.id:cur.id)+':'+chat.id;if(key!=PK){PK=key;PREV={};LIVE={}}
 const f=focusId();if(!f){hb.hidden=true;return}
 const sk=shown(f),col=mcol(sk.mood);C.style.setProperty('--mood',col);C.style.setProperty('--moodi',ENI[sk.en]||.55);C.dataset.en=sk.en||'medium';C.classList.toggle('prov',!!sk.prov);
 if(!G&&U.track){$('#hemo').textContent=sk.emoji;$('#hmood').textContent=sk.mood;$('#hmeter').style.width=sk.aff+'%';$('#hstage').textContent=stg(sk.aff);
  const b=$('#hav .bd');if(b)b.textContent=sk.emoji;$('#hchip').classList.toggle('prov',!!sk.prov)}
 if(G)$$('#gstrip [data-mid]').forEach(e=>{const id=e.dataset.mid;if(id=='__narrator__')return;const s=shown(id);e.style.setProperty('--mc',mcol(s.mood));e.insertAdjacentHTML('beforeend',`<span class=bd>${s.emoji}</span>`)});
 const si=sInfo(f),pend=!G&&!!relRec(f)?.fork;hb.hidden=false;hb.style.setProperty('--rc',si.P.color);hb.style.setProperty('--p',Math.round(si.frac*100));hb.classList.toggle('fork',pend);
 hb.querySelector('.bi').textContent=G?'👥':si.P.icon;hb.querySelector('b').textContent=G?'Bonds':pend?'Choose a path':si.label;hb.title=G?'Relationships in this group':`${si.P.label}: ${si.label}. Click to open.`;
 mids().forEach(id=>{const s=shown(id),i=sInfo(id),p=PREV[id];
  if(p&&id==f&&!s.prov){if(p.mood!=s.mood)pop('#hemo');const da=Math.round(s.aff)-Math.round(p.aff);if(da)fx(`${da>0?'▲':'▼'} ${Math.abs(da)}`,da>0?'var(--ok)':'var(--bad)');
   if(Math.round(i.v)-Math.round(p.v)>=1&&p.t==i.t)pop(hb,'bumps')}
  PREV[id]={mood:s.mood,aff:s.aff,v:i.v,i:i.i,t:i.t}});
 if(BP.open)bondDraw()}

/* ---------- instant reaction to what you just sent ---------- */
async function feelPeek(text){if(!U.track||!chat||!cur?.id||!S.rels)return;const ch=chat;let ids=mids();
 if(G){const hit=ids.filter(i=>{const c=memberById(i);return c&&new RegExp('@'+first(c).replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?![\\w])','i').test(text)});if(hit.length)ids=hit}
 const states={};ids.forEach(i=>{const s=stOf(i);states[i]={mood:s.mood,energy:s.energy,affection:s.affection,pers:s.pers}});
 let r;try{r=await api('/api/feel','POST',{cids:ids,states,text})}catch(e){return}
 if(chat!==ch||!r||!r.feel)return;let any=null;
 for(const id of ids){const f=r.feel[id];if(!f||f.quiet||!f.mood)continue;LIVE[id]={...f,d:f.delta||0,ts:Date.now()};any=any||[id,f];setTimeout(()=>liveDrop(id,ch,24e3),25e3)}
 if(!any)return;head();const[id,f]=any;pop('#hemo');
 fx(`${f.emoji} ${f.why||f.mood}${f.delta?` · ${f.delta>0?'▲':'▼'} ${Math.abs(f.delta)}`:''}`,mcol(f.mood))}
/* reactions on a message are noticed at once: a small, real change in how they feel, and a visible reaction */
const RXW={'❤️':[1,'affectionate'],'👍':[1,'happy'],'😂':[0,'amused'],'😮':[0,'surprised'],'😢':[0,'worried'],'😡':[-1,'hurt']};
function reactFx(m,prev){if(m.role!='assistant'||!U.track||!chat)return;const id=G?m.cid:cur?.id;if(!id||id=='__narrator__')return;
 const now=RXW[m.react]?.[0]||0,d=now-(m.rxd||0);m.rxd=now;if(d)addAff(id,d);
 if(m.react&&RXW[m.react]){const mo=RXW[m.react][1];const ch=chat;LIVE[id]={mood:mo,emoji:S.emo[mo]||'🙂',d:0,ts:Date.now()};setTimeout(()=>liveDrop(id,ch,4800),5000);
  fx(m.react+' noticed'+(d?` · ${d>0?'▲':'▼'} ${Math.abs(d)}`:''),mcol(mo))}else delete LIVE[id];head()}

/* ---------- the panel: mood, relationship path, progress, milestones ---------- */
function animW(root){root.querySelectorAll('[data-w]').forEach(e=>{const k=e.dataset.k,to=+e.dataset.w,from=PW[k];PW[k]=to;
 if(from==null||from==to){e.style.width=to+'%';return}e.style.width=from+'%';void e.offsetWidth;e.style.width=to+'%'})}
const MOODS=['neutral','happy','playful','affectionate','curious','shy','sad','annoyed','angry'];
function bpOne(id){const c=chOf(id),s=shown(id),st=stOf(id),i=sInfo(id),P=i.P,rec=relRec(id)||{},n=esc(c?.name||'Character'),log=(st.log||[]).slice(-14),col=mcol(s.mood),
 th=U.thoughts&&!s.prov?(log.at(-1)?.thought||''):'',sel=BP.sel>=0?log[BP.sel]:null,en=['low','medium','high'].indexOf(s.en||'medium')+1,
 types=Object.keys(S.rels).filter(k=>k!='romance'||isAdult(c)),pend=!G&&!!rec.fork,fill=Math.min(100,(i.i+i.frac)/5*100),
 ms=[...(rec.hist||[])].reverse().slice(0,5),rms=i.t=='romance'?(chat.rp?.rom?.[id]?.ms||[]):[];
 const spark=log.length?`<div class=bp-spark>${log.map((l,k)=>`<button data-b=sel data-k=${k} class="${k==BP.sel?'on':''}" style="--c:${mcol(l.mood)};height:${10+Math.round((mval(l.mood)+1)/2*30)}px" title="${at(l.emoji+' '+l.mood+' · '+hm(l.ts))}"></button>`).join('')}</div>`:'<p class=small>Mood history appears after a few messages.</p>';
 return`${G?`<button class=bp-back data-b=back>‹ All characters</button>`:''}
 <div class=bp-top style="--mc:${col}"><div class="bp-emo" id=bpemo>${s.emoji}</div><div class=bp-mw><span class=bp-k>${s.prov?'Reacting…':'Feeling'}</span><b>${esc(s.mood)}</b>
  <span class=bp-en title="${ENL[s.en||'medium']}"><i class="${en>0?'on':''}"></i><i class="${en>1?'on':''}"></i><i class="${en>2?'on':''}"></i><em>${ENL[s.en||'medium']}</em></span></div>
  <div class=bp-who>${avatar(c,'sm')}<span>${n}</span></div></div>
 ${th?`<div class=bp-th>💭 ${esc(th)}</div>`:''}${spark}${sel?`<div class=bp-sel>${sel.emoji} <b>${esc(sel.mood)}</b> · ${hm(sel.ts)} · ${stg(sel.aff)}${U.thoughts&&sel.thought?`<br><i>${esc(sel.thought)}</i>`:''}</div>`:''}
 <div class=bp-aff><span>How ${n} feels about you</span><b>${stg(s.aff)}</b></div><div class=bp-bar><i data-w="${s.aff}" data-k="aff${id}"></i></div>
 <div class=bp-sec><span>Relationship</span><b style="color:${P.color}">${P.icon} ${esc(P.label)}</b></div>
 ${pend?`<div class=bp-fork><b>Where is this heading?</b><span>Your bond with ${n} is growing. Choose what it is becoming; you can change it at any time.</span><button data-b=forkoff>Keep it open</button></div>`:''}
 <div class=bp-types>${types.map(k=>{const R=S.rels[k];return`<button data-b=type data-t=${k} class="${k==i.t?'on':''}" style="--rc:${R.color}" title="${at(R.blurb)}"><span>${R.icon}</span>${esc(k=='auto'?'Undecided':R.label)}</button>`}).join('')}</div>
 ${i.t=='mentor'?`<div class=bp-roles>${(P.roles||[]).map(([k,l])=>`<button data-b=role data-r=${k} class="${(rec.role||'master')==k?'on':''}">${esc(l.replace('{name}',c?.name||'They'))}</button>`).join('')}</div>`:''}
 <div class=bp-track style="--rc:${P.color}"><div class=bp-line><i data-w="${fill}" data-k="trk${id}"></i>${P.stages.map((_,k)=>`<span class="bp-dot ${k<i.i?'done':k==i.i?'now':''}" style="left:${k/5*100}%"></span>`).join('')}</div>
  <div class=bp-names>${P.stages.map((x,k)=>`<em class="${k<i.i?'done':k==i.i?'now':''}">${esc(x)}</em>`).join('')}</div></div>
 <div class=bp-now><b style="color:${P.color}">${esc(i.label)}</b><span>${i.next?`${Math.round(i.frac*100)}% toward ${esc(i.next)}`:'The deepest stage of this bond'}</span></div>
 ${ms.length||rms.length?`<div class=bp-ms>${ms.map(h=>`<div><span>${h.i<0?'🧭':rpath(h.ty).icon}</span><b>${esc(h.s)}</b><small>${new Date(h.t).toLocaleDateString([],{month:'short',day:'numeric'})}</small></div>`).join('')}${rms.map(x=>`<div><span>💞</span><b>${esc(x)}</b></div>`).join('')}</div>`:''}
 <details class=bp-adj><summary>Adjust by hand</summary><label>Mood</label><div class=chips>${MOODS.map(m=>`<button data-b=mood data-m=${m} class="${m==st.mood?'on':''}">${S.emo[m]||''} ${m}</button>`).join('')}</div>
  <label>How ${n} feels about you: <b id=bpa>${stg(st.affection)} (${st.affection})</b></label><input type=range min=0 max=100 value=${st.affection} data-bi=aff>
  <label>Bond progress: <b id=bpp>${esc(i.label)} (${Math.round(i.v)})</b></label><input type=range min=0 max=100 value=${Math.round(i.v)} data-bi=prog></details>
 <div class=bp-foot><button data-b=mem>Open memory tab</button></div>`}
function bpList(){return`<div class=bp-sec style="margin-top:0"><span>Everyone in this group</span></div>${mids().map(id=>{const c=chOf(id),s=shown(id),i=sInfo(id);
 return`<button class=bp-row data-b=focus data-id=${id} style="--mc:${mcol(s.mood)};--rc:${i.P.color}">${avatar(c,'sm')}<span class=bp-rn><b>${esc(c.name)}</b><small>${s.emoji} ${esc(s.mood)} · ${i.P.icon} ${esc(i.label)}</small></span><span class=bp-mini><i data-w="${Math.round((i.i+i.frac)/5*100)}" data-k="mini${id}"></i></span></button>`}).join('')}`}
function bondDraw(){const el=$('#bondpop');if(!el)return;if(!BP.open||!chat||!cur||!S.rels){el.hidden=true;return}
 const sc=el.scrollTop,id=BP.f&&mids().includes(BP.f)?BP.f:focusId();BP.f=id;if(G&&BP.view=='list')el.innerHTML=`<div class=bp-hd><b>Mood and relationships</b><button data-b=close class=ib aria-label=Close>✕</button></div>`+bpList();
 else el.innerHTML=`<div class=bp-hd><b>Mood and relationship</b><button data-b=close class=ib aria-label=Close>✕</button></div>`+bpOne(id);
 el.hidden=false;animW(el);el.scrollTop=sc;const s=shown(id);if(PM[id]&&PM[id]!=s.mood)pop('#bpemo');PM[id]=s.mood}
function bondOpen(id){BP.open=true;BP.sel=-1;if(id){BP.f=id;BP.view='one'}else{BP.f=focusId();BP.view=G?'list':'one'}$('.chead').classList.remove('open');bondDraw()}
const bondClose=()=>{BP.open=false;const e=$('#bondpop');if(e)e.hidden=true},bondToggle=()=>BP.open?bondClose():bondOpen();
$('#hchip').onclick=()=>bondToggle();$('#hbond').onclick=()=>bondToggle();
$('#bondpop').addEventListener('click',e=>{const b=e.target.closest('[data-b]');if(!b||!chat)return;const k=b.dataset.b,f=BP.f;
 if(k=='close')bondClose();else if(k=='back'){BP.view='list';bondDraw()}else if(k=='focus'){BP.f=b.dataset.id;BP.view='one';BP.sel=-1;bondDraw()}
 else if(k=='sel'){BP.sel=BP.sel==+b.dataset.k?-1:+b.dataset.k;bondDraw()}else if(k=='type')setRelType(f,b.dataset.t);
 else if(k=='role'){relRec(f,true).role=b.dataset.r;saveSoon();bondDraw()}else if(k=='mood')setMood(f,b.dataset.m);
 else if(k=='forkoff'){const r=relRec(f,true);r.fork=0;r.forkDone=1;saveSoon();head()}else if(k=='mem'){bondClose();tab('mem')}});
$('#bondpop').addEventListener('input',e=>{const k=e.target.dataset.bi,id=BP.f;if(!k||!chat)return;const v=+e.target.value;
 if(k=='aff'){stOf(id).affection=v;$('#bpa').textContent=`${stg(v)} (${v})`}else{setRelV(id,v);$('#bpp').textContent=`${sInfo(id).label} (${v})`}head();saveSoon()});
$('#bondpop').addEventListener('change',e=>{if(e.target.dataset.bi)bondDraw()});
document.addEventListener('click',e=>{if(BP.open&&!e.target.closest('#bondpop,#hchip,#hbond,.btoast,.ddo,#ddpop'))bondClose()});
document.addEventListener('keydown',e=>{if(e.key=='Escape'&&BP.open)bondClose()});

/* ---------- memory tab: one place to steer every relationship ---------- */
function bondMem(){if(!chat||!S.rels)return'';
 return`<details open><summary>Relationships</summary><p class=small>Every character has a path and a progress bar. It moves with how they feel about you, and you can steer it here.</p>${mids().map(id=>{const c=chOf(id),i=sInfo(id),r=relRec(id)||{},ty=Object.keys(S.rels).filter(k=>k!='romance'||isAdult(c));
  return`<div class=bm><label>${esc(c.name)}: <b>${i.P.icon} ${esc(i.label)} (${Math.round(i.v)})</b></label><div class=row><select data-bm=type data-c=${id}>${ty.map(k=>`<option value=${k} ${k==i.t?'selected':''}>${esc(k=='auto'?'Undecided':S.rels[k].label)}</option>`).join('')}</select>
  ${i.t=='mentor'?`<select data-bm=role data-c=${id}>${(i.P.roles||[]).map(([k,l])=>`<option value=${k} ${(r.role||'master')==k?'selected':''}>${esc(l.replace('{name}',c.name))}</option>`).join('')}</select>`:''}</div>
  <input type=range min=0 max=100 value=${Math.round(i.v)} data-bm=prog data-c=${id}>${(r.hist||[]).length?`<div class=small>${esc(r.hist.slice(-4).map(h=>h.s).join(' → '))}</div>`:''}</div>`}).join('')}</details>`}
$('#memf').addEventListener('input',e=>{const k=e.target.dataset.bm;if(k!='prog'||!chat)return;const id=e.target.dataset.c;setRelV(id,+e.target.value);e.target.previousElementSibling.previousElementSibling.querySelector('b').textContent=`${sInfo(id).P.icon} ${sInfo(id).label} (${e.target.value})`;head();saveSoon()});
$('#memf').addEventListener('change',e=>{const k=e.target.dataset.bm,id=e.target.dataset.c;if(!chat||!k)return;
 if(k=='type')setRelType(id,e.target.value);else if(k=='role'){relRec(id,true).role=e.target.value;saveSoon()}else if(k=='prog')renderMem()});

/* ---------- a message remembers the mood it was written in ---------- */
function moTag(m){if(!m.mo||m.role!='assistant')return'';const o=m.mo,nw=o.f;if(nw)setTimeout(()=>{if(m.mo)m.mo.f=0},60);
 return`<span class="mtag${nw?' new':''}" style="--c:${mcol(o.m)}" title="${at(o.m)}">${o.e||''} ${esc(o.m)}${o.d?`<b class=${o.d>0?'up':'dn'}>${o.d>0?'▲':'▼'}${Math.abs(o.d)}</b>`:''}</span>`}
const moAttr=m=>m.mo&&m.role=='assistant'?` data-mo style="--mc:${mcol(m.mo.m)}"`:'';
