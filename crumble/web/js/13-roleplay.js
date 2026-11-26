/* outcome cards (no dice: every outcome is judged from skills, condition and situation) */
const isDead=id=>!!chat?.rp?.body?.[id]?.dead,bodyOf=id=>chat?.rp?.body?.[id]||null;
const CARDI={heal:'🩹',revive:'☠',rest:'🛏',persuade:'💬',intimidate:'😠'};
function cardHTML(c){const rows=(c.rows||[]).map(r=>`<div class=fxr><span class=fxw>${esc(r.who||'')}</span>${r.d?`<code>${esc(r.d)}</code>`:''}<b style="color:${TIERC[r.tier]||'var(--tx)'}">${esc(r.res||'')}</b>${r.ex?`<span class=small>${esc(r.ex)}</span>`:''}</div>`).join('');
 return`<div class=fxc><div class=fxh>${CARDI[c.type]||'✦'} ${esc(c.title||'')}<span class=sp></span><button data-a=fxno title="Ignore this outcome">✕</button></div>${rows}${c.note?`<div class="small fxn">${esc(c.note)}</div>`:''}</div>`}
async function resolveFx(m,forced){
 m.rpsnap=JSON.stringify(chat.rp||{});const ids=G?G.members:[cur.id],aff={},mood={};ids.forEach(i=>{const s=G?mst(i):chat.state;aff[i]=s.affection;mood[i]=s.mood});
 const lastSp=[...hist].reverse().find(x=>x.role=='assistant'&&x.cid)?.cid||'';
 const r=await api('/api/rp/resolve','POST',{...(G?{group:G.id}:{cid:cur.id}),present:sceneOn()?presentIds():undefined,text:m.content,forced:forced||null,user:uname(),ustats:U.ustats,ugear:U.ugear,uskills:U.uskills||'',turn:hist.length,rp:chat.rp||{},aff,mood,last:lastSp,cfg:rpCfg()});
 if(r.err||!r.rp){delete m.rpsnap;return}
 chat.rp=r.rp;if(!r.card&&!r.brief){delete m.rpsnap;return}
 m.card=r.card;m.fx=r.brief;m.acting=r.acting||[];m.affd=r.aff||{};for(const[id,d]of Object.entries(m.affd))addAff(id,d);bodyNews(r)}
/* deaths and returns: say so loudly; the bond of the dead is set aside by the server and returns only with a resurrection */
function bodyNews(r){const nm=id=>(G?memberById(id):cur)?.name||'They';
 for(const id of r.deaths||[])bodyToast('☠',nm(id)+' has died','The dead cannot speak. Only a resurrection can bring them back.');
 for(const id of Object.keys(r.revived||{})){const s=G?mst(id):chat.state;if(s){s.mood='shaken';s.emoji='😵';s.energy='low'}bodyToast('✨',nm(id)+' returns from the dead','Frail and shaken, remembering dying.')}
 head()}
function bodyToast(i,b,s){try{toast('up','#c0392b',i,'Roleplay',esc(b),esc(s),null)}catch(e){}}
/* what the narration itself says happened to a body (a wound, a sickness, a death, time passing) */
async function observeFx(text,m){if(U.rp=='off'||!chat||!text)return;const ids=G?G.members:[cur.id],aff={},mood={};ids.forEach(i=>{const s=G?mst(i):chat.state;aff[i]=s.affection;mood[i]=s.mood});
 try{const snap=JSON.stringify(chat.rp||{});const r=await api('/api/rp/observe','POST',{...(G?{group:G.id}:{cid:cur.id}),present:sceneOn()?presentIds():undefined,text,user:uname(),rp:chat.rp||{},aff,mood,turn:hist.length});
  if(r.err||!r.rp)return;if(JSON.stringify(r.rp)==snap)return;if(!m.rpsnap&&!m.obsnap)m.obsnap=snap;chat.rp=r.rp;bodyNews(r);saveChat();if(!$('#mem').hidden)renderMem()}catch(e){}}
function fxNo(i){const m=hist[i];if(!m)return;restore(m);delete m.card;delete m.fx;delete m.acting;saveChat();draw()}

/* action bar (no fight engine: conflict is story) */
const ACTS={social:[['persuade','💬','Persuade'],['intimidate','😠','Intimidate'],['deceive','🎭','Deceive'],['comfort','🫶','Comfort'],['investigate','🔍','Investigate'],['sneak','🤫','Sneak'],['steal','🖐','Sleight of hand'],['athletics','🧗','Athletics'],['craft','🔧','Craft'],['heal','🩹','Aid']],
 romance:[['flirt','😏','Flirt'],['touch','🤝','Touch'],['date','🌹','Ask out'],['kiss','💋','Kiss'],['confess','💞','Confess'],['intimate','🌙','Closer']]};
function armUI(){$$('#rpbar .pill').forEach(b=>b.classList.toggle('arm',b.dataset.k==armed&&!b.dataset.d));$('#inp').placeholder=oocOn?(innerWidth<=760?'Out of character…':'Out of character: discuss the story, correct someone, change the setting or give directions…'):armed?innerWidth<=760?'Describe your move… (Enter to send)':`Describe how you try to ${(ACTS.social.concat(ACTS.romance).find(a=>a[0]==armed)||[0,0,armed])[2].toLowerCase()}… (Enter to send)`:(innerWidth<=760?'Message…':'Message… (Enter sends, Shift+Enter adds a line)')}
function rpbarDraw(){const e=$('#rpbar');$('#tact2').hidden=U.rp=='off';$('#keep').hidden=!G;typeof autoUI=='function'&&autoUI();
 e.hidden=oocOn||!(U.actbar&&U.rp!='off');if(e.hidden)return;
 const pl=(l,a)=>`<span class=lb>${l}</span>`+a.map(x=>`<button class=pill data-k=${x[0]} ${x[3]?`data-d="${at(x[3])}"`:''} title="${x[2]}">${x[1]} ${x[2]}</button>`).join('');
 e.innerHTML=pl('Do',ACTS.social)+(U.romance?pl('Romance',ACTS.romance):'');armUI()}
$('#rpbar').onclick=e=>{const b=e.target.closest('button');if(!b||ctl||rounding)return;const k=b.dataset.k,d=b.dataset.d,t=$('#inp').value.trim();
 if(t){armed=k;send()}else if(d){$('#inp').value=d;armed=k;send()}else{armed=armed==k?null:k;armUI();$('#inp').focus()}};
$('#tact2').onclick=()=>{U.actbar=!U.actbar;pills();rpbarDraw()};

/* slash commands */
function slash(t){const[c,...r]=t.slice(1).split(/\s+/),arg=r.join(' ').trim();
 if(c=='roll'||c=='fight'||c=='peace')return{text:'*there are no dice and no fights to start here: whatever happens comes from the people and the moment*',nofx:1,local:1};
 if(c=='rest')return{text:`*rests ${arg?'for '+arg:'for 8 hours'} to recover*`,forced:'rest'};
 if(c=='revive')return{text:`*${arg||'the fallen'} is brought back from the dead*`,forced:'revive'};
 if(c=='later'||c=='skip'||c=='time')return{text:worldSkip(arg||'1 hour'),nofx:0};
 return null}

/* group round: the server decides who speaks next, one speaker at a time */
async function round(opts={}){
 if(!G||ctl||rounding)return;rounding=true;roundAbort=false;busy(true);const spoke=[];let cap=0;
 const lu=hist.at(-1),acting=lu?.role=='user'?(lu.acting||[]):[],fx0=!!lu?.fx;
 try{for(let n=0;n<9&&!roundAbort;n++){
  const aff={};G.members.forEach(i=>aff[i]=mst(i).affection);
  const r=await api('/api/group_next','POST',{group:G.id,present:sceneOn()?presentIds():undefined,user:uname(),history:apiHist(hist.slice(-30)),spoke,cap,n,keep:!!opts.keep,circle:circ(),fx:n==0&&fx0,acting,aff,pers:U.pers,dead:Object.keys(chat.rp?.body||{}).filter(isDead)});
  if(r.err){errBox(r.err,'round');break}
  cap=r.cap;if(!r.next)break;
  if(n>0){setStatus('typing…');await sleep(500+Math.random()*1300)}if(roundAbort)break;
  const g=await gen('reply',r.next,{why:r.why,by:r.by,pass:r.pass,to:r.to});if(g===null)break;spoke.push(r.next)}}
 finally{rounding=false;busy(false);setStatus('online')}}
$('#keep').onclick=()=>{if(!ctl&&!rounding&&chat)round({keep:true})};

/* roleplay memory section */
function rpMem(){const rp=chat.rp||{},ids=G?G.members:[cur.id];
 return`<details open><summary>Roleplay</summary><label>Romance with each character (your choices move this; you can adjust it)</label>${ids.map(i=>{const c=memberById(i)||cur,r=rp.rom?.[i]?.v||0;
  return`<label>${esc(c.name)}: <b>${romStage(r)} (${r})</b></label><input type=range min=0 max=100 value=${r} data-m=rom data-c=${i}>`+(rp.rom?.[i]?.ms?.length?`<div class=small>${esc(rp.rom[i].ms.join(' · '))}</div>`:'')}).join('')}`
 +(U.intimacy?`<label style="margin-top:8px">Physical intimacy with each character (adult characters only; you can adjust it)</label>${ids.map(i=>{const c=memberById(i)||cur,iv=rp.intim?.[i]?.iv||0;
  return`<label>${esc(c.name)}: <b>${intimStage(iv)} (${iv})</b></label><input type=range min=0 max=100 value=${iv} data-m=intim data-c=${i}>`+(rp.intim?.[i]?.acts?.length?`<div class=small>${esc(rp.intim[i].acts.join(' · '))}</div>`:'')}).join('')}`:'')
 +`<div class=row><button data-m=rest>🛏 Rest 8 hours</button></div><div class=small>Set your stats, skills and gear under “About you” in the sidebar. Skill attempts are judged from them (no dice). Wounds heal with time, care and rest.</div></details>`+bodyMem(ids)}
function bodyMem(ids){const all=[['user',uname()],...ids.map(i=>[i,(memberById(i)||cur).name])],rp=chat.rp||{};
 const rows=all.map(([id,n])=>{const b=rp.body?.[id];if(!b)return'';const L=[...(b.inj||[]).map(i=>`${i.k} (${i.p}, ${['','minor','painful','serious','critical'][i.s]}${i.care?', tended':''})`),...(b.ill||[]).map(i=>`${i.k} (${['','mild','real','bad','dangerous'][i.s]})`)];
  if(b.dead)return`<label>☠ ${esc(n)}: <b>dead</b>${b.died?.how?' · '+esc(b.died.how):''}</label><div class=row><button data-m=revive data-c=${id}>✨ Bring back (author)</button></div>`;
  return L.length||b.tired>=50?`<label>${esc(n)}: <b>${esc(L.join('; ')||'worn out')}</b>${b.tired>=50?' · exhausted':''}</label><div class=row><button data-m=heal1 data-c=${id}>🩹 Treat</button></div>`:''}).join('');
 return rows?`<details open><summary>Bodies</summary>${rows}<div class=small>Serious wounds need treatment; the dying bleed out within the hour. The dead stay dead unless someone with real revival power (or you, as the author) brings them back.</div></details>`:''}
function renderMemG(){const f=$('#memf'),st=chat.state;
 f.innerHTML=`<details open><summary>Characters in this group</summary>${gmem().map(c=>{const s=mst(c.id);return`<label>${esc(c.name)}: <b>${s.emoji||'😐'} ${esc(s.mood||'neutral')}</b> · feels about you: <b>${stg(s.affection)} (${s.affection})</b></label><input type=range min=0 max=100 value=${s.affection} data-m=gaff data-c=${c.id}>`}).join('')}</details>
 <details open><summary>Scene note</summary><label>Steer the situation. It stays in every prompt for this chat.</label><textarea data-m=scene rows=3>${esc(chat.cfg.scene||'')}</textarea></details>
 <details open><summary>Memory of earlier conversation</summary><label>Long chats are summarised automatically. You can edit it.</label><textarea data-m=summary rows=6>${esc(st.summary||'')}</textarea><div class=row><button data-m=sumnow>Summarize now</button><span class=small id=msum></span></div></details>${keepHtml(st,G?G.name:'the group')}`+(U.mem?gmem().filter(c=>c.id!='__narrator__').map(c=>memHtml(mst(c.id),c.name,c.id)).join(''):'')+rpMem()}
function renderMem(){if(!chat?.state){$('#memf').innerHTML='<p class=small>Open a chat first.</p>';return}if(G)renderMemG();else{renderMemOne();$('#memf').insertAdjacentHTML('beforeend',rpMem())}$('#memf').insertAdjacentHTML('beforeend',(G?circleMem():'')+bondMem()+notesMem());persMem()}
