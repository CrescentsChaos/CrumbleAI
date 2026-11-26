/* ---------- the circle: how the characters feel about each other ---------- */
let CV=null,autoOn=false,autoRuns=0,autoT=0;
const circ=()=>{chat.cfg.circle=chat.cfg.circle||{v:1,pairs:{}};return chat.cfg.circle};
const affMap=()=>{const o={};(G?G.members:[]).forEach(i=>o[i]=mst(i).affection);return o};
const romMap=()=>{const o={};(G?G.members:[]).forEach(i=>o[i]=chat.rp?.rom?.[i]?.v||0);return o};
const CWHY={interrupt:'cut in',jealous:'jealous',disagree:'disagrees',back:'backs them up',thread:'side talk',branch:'new topic'};
function circToast(n){try{toast('up','#8e6bd8','🔗','Group',esc(n.t),'',null)}catch(e){}}
async function circleSync(extra){if(!G||!chat)return null;const ch=chat,g=G;
 const r=await api(extra?'/api/circle/observe':'/api/circle','POST',{group:g.id,circle:ch.cfg.circle,user:uname(),aff:affMap(),rom:romMap(),present:sceneOn()?presentIds():undefined,...extra}).catch(()=>null);
 if(!r||r.err||chat!==ch)return null;ch.cfg.circle=r.circle;CV={...r,gid:g.id+ch.id};(r.notes||[]).forEach(circToast);return r}
async function circleSeen(m,speaker,text,prev){if(!G||!chat||!text)return;const snap=JSON.stringify(chat.cfg.circle||null);
 const r=await circleSync({speaker,text,prev});if(r){m.csnap=snap;saveSoon();if(!$('#mem').hidden)renderMem()}}
async function circleUser(m,text){if(!G||!chat||!text)return;const snap=JSON.stringify(chat.cfg.circle||null);
 const r=await circleSync({from:'user',text});if(r){m.csnap=snap;saveSoon()}}
function circleMem(){if(!G||!chat)return'';
 if(!CV||CV.gid!=G.id+chat.id){circleSync().then(r=>{if(r&&!$('#mem').hidden)renderMem()});return`<details open><summary>Between the characters</summary><div class=small>Reading how they know each other…</div></details>`}
 const V=CV,nm=id=>esc(memberById(id)?.name||'?'),kinds=Object.entries(V.kinds);
 const sl=(lab,c,k,v)=>`<label>${lab} <b>${v}</b></label><input type=range min=0 max=100 value=${v} data-cc=${c} data-k="${k}">`;
 const peo=Object.values(V.people).map(p=>`<div class=cc-p><b>${esc(p.name)}</b> ${esc(p.stance)}<small>loyal to ${esc(p.loyal)}</small></div>`).join('');
 const rows=V.pairs.map(p=>{const k=p.a+'|'+p.b,hot=(p.ja>=40||p.jb>=40?'<em title="Jealousy">😒</em>':'')+(p.x>=60?'<em title="Tension">⚡</em>':'');
  return`<details class=cc-pair><summary><span>${p.icon}</span><b>${nm(p.a)}</b> &amp; <b>${nm(p.b)}</b><small>${esc(p.label)}</small>${hot}</summary>
  <div class=small>${nm(p.a)} and ${nm(p.b)} ${esc(p.phrase)}.</div>
  <label>Bond</label><select data-cc=kind data-k="${k}">${kinds.map(([v,o])=>`<option value=${v} ${v==p.kind?'selected':''}>${o.icon} ${o.label}</option>`).join('')}</select>
  ${sl('Warmth','f',k,p.f)}${sl('Trust','t',k,p.t)}${sl('Tension','x',k,p.x)}${sl(nm(p.a)+' is jealous of '+nm(p.b),'ja',k,p.ja)}${sl(nm(p.b)+' is jealous of '+nm(p.a),'jb',k,p.jb)}
  ${p.ev.length?`<div class=small>${p.ev.map(esc).join(' · ')}</div>`:''}</details>`}).join('');
 return`<details open><summary>Between the characters</summary><div class=cc-co><span>Group trust: <b>${esc(V.cohesion.label)}</b></span><span class=meter><i style="width:${V.cohesion.v}%"></i></span></div>
  <div class=small>Bonds start from each sheet's Relationships field, grow with what they say to each other, and you can set them by hand. Each character only acts on their own side of it.</div>
  <div class=cc-pp>${peo}</div>${rows}</details>`}
$('#memf').addEventListener('input',e=>{const t=e.target,c=t.dataset.cc;if(!c||!G||!chat)return;const k=t.dataset.k,p=circ().pairs[k];if(!p)return;const v=+t.value,[a,b]=k.split('|');
 if(c=='f')p.f=v;else if(c=='t')p.t=v;else if(c=='x')p.x=v;else if(c=='ja')p.j[a]=v;else if(c=='jb')p.j[b]=v;else return;
 const l=t.previousElementSibling?.querySelector('b');if(l)l.textContent=v;saveSoon()});
$('#memf').addEventListener('change',async e=>{const t=e.target;if(t.dataset.cc!='kind'||!G||!chat)return;const p=circ().pairs[t.dataset.k];if(!p)return;p.k=t.value;p.m=1;saveSoon();await circleSync();renderMem()});

/* ---------- let them talk on their own (only when the group allows it) ---------- */
const autoOK=()=>!!(G&&G.auto);
function autoUI(){const b=$('#auto');if(!b)return;b.hidden=!autoOK();b.classList.toggle('on',autoOn&&autoOK())}
function autoStop(){autoOn=false;autoRuns=0;clearTimeout(autoT);autoUI()}
function autoTick(){clearTimeout(autoT);if(!autoOn||!autoOK())return;
 autoT=setTimeout(async()=>{if(!autoOn||!autoOK())return;
  if(ctl||rounding||typingNow||document.hidden||$('#inp').value.trim()||!chat||$('#chat').hidden){autoTick();return}
  if(autoRuns>=(G.auto_max||6)){autoStop();try{toast('up','#8e6bd8','💬','Group','They paused','Press Auto-talk to let them go on.',null)}catch(e){}return}
  autoRuns++;await round({keep:true});autoTick()},Math.max(2,U.autoGap||5)*1000)}
$('#auto').onclick=()=>{if(!autoOK())return;autoOn=!autoOn;autoRuns=0;autoUI();if(!autoOn){clearTimeout(autoT);return}if(!ctl&&!rounding&&chat)round({keep:true}).then(autoTick);else autoTick()};
