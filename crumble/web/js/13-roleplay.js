/* dice cards */
function cardHTML(c){const rows=(c.rows||[]).map(r=>`<div class=fxr><span class=fxw>${esc(r.who||'')}</span>${r.d?`<code>${esc(r.d)}</code>`:''}<b style="color:${TIERC[r.tier]||'var(--tx)'}">${esc(r.res||'')}</b>${r.ex?`<span class=small>${esc(r.ex)}</span>`:''}</div>`).join('');
 return`<div class=fxc><div class=fxh>🎲 ${esc(c.title||'')}<span class=sp></span><button data-a=fxre title="Re-roll">↻</button><button data-a=fxno title="Ignore this roll">✕</button></div>${rows}${c.note?`<div class="small fxn">${esc(c.note)}</div>`:''}</div>`}
async function resolveFx(m,forced){
 m.rpsnap=JSON.stringify(chat.rp||{});const ids=G?G.members:[cur.id],aff={},mood={};ids.forEach(i=>{const s=G?mst(i):chat.state;aff[i]=s.affection;mood[i]=s.mood});
 const lastSp=[...hist].reverse().find(x=>x.role=='assistant'&&x.cid)?.cid||'';
 const r=await api('/api/rp/resolve','POST',{...(G?{group:G.id}:{cid:cur.id}),text:m.content,forced:forced||null,user:uname(),ustats:U.ustats,ugear:U.ugear,rp:chat.rp||{},aff,mood,last:lastSp,cfg:rpCfg()});
 if(r.err||!r.rp){delete m.rpsnap;return}
 chat.rp=r.rp;if(!r.card&&!r.brief){delete m.rpsnap;return}
 m.card=r.card;m.fx=r.brief;m.acting=r.acting||[];m.affd=r.aff||{};for(const[id,d]of Object.entries(m.affd))addAff(id,d)}
async function fxRe(i){if(ctl||rounding)return;const m=hist[i];if(!m?.card)return;if(i<hist.length-1&&!confirm('Re-roll and replace the replies after this message?'))return;
 const k=m.card.type;restore(m);hist.splice(i+1);delete m.card;delete m.fx;draw();await resolveFx(m,k);draw();saveChat();G?await round():await gen('reply')}
function fxNo(i){const m=hist[i];if(!m)return;restore(m);delete m.card;delete m.fx;delete m.acting;saveChat();draw()}

/* combat panel + action bar */
const ACTS={combat:[['attack','⚔','Attack','*attacks*'],['special','✨','Power','*unleashes a power*'],['defend','🛡','Defend','*braces and guards*'],['heal','🩹','Aid','*tends to wounds*'],['flee','🏃','Flee','*tries to flee*'],['persuade','🕊','Talk down','"Stop! We do not have to do this!"']],
 social:[['persuade','💬','Persuade'],['intimidate','😠','Intimidate'],['deceive','🎭','Deceive'],['comfort','🫶','Comfort'],['investigate','🔍','Investigate'],['sneak','🤫','Sneak'],['steal','🖐','Sleight of hand'],['athletics','🧗','Athletics'],['craft','🔧','Craft'],['attack','⚔','Start a fight']],
 romance:[['flirt','😏','Flirt'],['touch','🤝','Touch'],['date','🌹','Ask out'],['kiss','💋','Kiss'],['confess','💞','Confess'],['intimate','🌙','Closer']]};
function cbtDraw(){const cb=chat?.rp?.combat,e=$('#cbt');
 if(!cb||!cb.on||U.rp=='off'){e.hidden=true;rpbarDraw();return}
 e.hidden=false;e.innerHTML=`<div class=cbh><b>⚔ Combat · round ${cb.round}</b><span class=small>${G?'@Name to pick a target':''}</span><span class=sp></span><button data-c=peace class=ghost>🕊 End fight</button></div><div class=units>${cb.units.map(u=>{const p=Math.max(0,u.hp/u.max*100),st=u.fled?'🏃 fled':u.hp<=0?'💫 down':u.def?'🛡 braced':'';
  return`<div class="unit ${u.side}"><div class=un>${esc(u.name)}${u.side=='ally'?' 🤝':u.side=='player'?' (you)':''}</div><div class=hp><i style="width:${p}%;background:${p>50?'#58d68d':p>25?'var(--ac)':'var(--bad)'}"></i></div><div class=small>${Math.max(0,u.hp)}/${u.max} ${st}</div></div>`}).join('')}</div>`;rpbarDraw()}
$('#cbt').onclick=e=>{if(e.target.dataset.c=='peace'&&!ctl&&!rounding)post('*lowers their guard and calls off the fight*','peace')};
function armUI(){$$('#rpbar .pill').forEach(b=>b.classList.toggle('arm',b.dataset.k==armed&&!b.dataset.d));$('#inp').placeholder=armed?`Describe how you try to ${(ACTS.combat.concat(ACTS.social,ACTS.romance).find(a=>a[0]==armed)||[0,0,armed])[2].toLowerCase()}… (Enter to send)`:(innerWidth<=760?'Message…':'Message… (Enter sends, Shift+Enter adds a line)')}
function rpbarDraw(){const e=$('#rpbar'),cb=chat?.rp?.combat?.on&&U.rp!='off';$('#tact2').hidden=U.rp=='off';$('#keep').hidden=!G;
 e.hidden=!(cb||(U.actbar&&U.rp!='off'));if(e.hidden)return;
 const pl=(l,a)=>`<span class=lb>${l}</span>`+a.map(x=>`<button class=pill data-k=${x[0]} ${x[3]?`data-d="${at(x[3])}"`:''} title="${x[2]}">${x[1]} ${x[2]}</button>`).join('');
 e.innerHTML=cb?pl('Combat',ACTS.combat):pl('Do',ACTS.social)+(U.romance?pl('Romance',ACTS.romance):'');armUI()}
$('#rpbar').onclick=e=>{const b=e.target.closest('button');if(!b||ctl||rounding)return;const k=b.dataset.k,d=b.dataset.d,t=$('#inp').value.trim();
 if(t){armed=k;send()}else if(d){$('#inp').value=d;armed=k;send()}else{armed=armed==k?null:k;armUI();$('#inp').focus()}};
$('#tact2').onclick=()=>{U.actbar=!U.actbar;pills();rpbarDraw()};

/* slash commands */
function slash(t){const[c,...r]=t.slice(1).split(/\s+/),arg=r.join(' ').trim();
 if(c=='roll'){const m=/^(\d*)d(\d+)\s*([+-]\s*\d+)?$/i.exec(arg||'1d20');if(!m)return{text:'*tries to roll dice* (usage: /roll 2d6+3)',nofx:1};
  const n=Math.min(20,+m[1]||1),s=Math.min(1000,+m[2]),b=+(m[3]||'0').replace(/\s/g,''),ds=Array.from({length:n},()=>1+Math.floor(Math.random()*s));
  return{text:`🎲 *rolls ${n}d${s}${b?(b>0?'+':'')+b:''}* → **${ds.reduce((a,x)=>a+x,0)+b}**${n>1?' ('+ds.join(' + ')+(b?', '+(b>0?'+':'')+b:'')+')':''}`,nofx:1}}
 if(c=='fight')return{text:`*attacks${arg?' '+arg.replace(/^@/,''):''}*`,forced:'attack'};
 if(c=='peace')return{text:'*lowers their guard and calls off the fight*',forced:'peace'};
 if(c=='rest')return{text:'*takes a long rest to recover*',forced:'rest'};
 return null}

/* group round: the server decides who speaks next, one speaker at a time */
async function round(opts={}){
 if(!G||ctl||rounding)return;rounding=true;roundAbort=false;busy(true);const spoke=[];let cap=0;
 const lu=hist.at(-1),acting=lu?.role=='user'?(lu.acting||[]):[],fx0=!!lu?.fx;
 try{for(let n=0;n<9&&!roundAbort;n++){
  const aff={};G.members.forEach(i=>aff[i]=mst(i).affection);
  const r=await api('/api/group_next','POST',{group:G.id,user:uname(),history:apiHist(hist.slice(-30)),spoke,cap,n,keep:!!opts.keep,fx:n==0&&fx0,acting,aff,pers:U.pers});
  if(r.err){errBox(r.err,'round');break}
  cap=r.cap;if(!r.next)break;
  if(n>0){setStatus('typing…');await sleep(500+Math.random()*1300)}if(roundAbort)break;
  const g=await gen('reply',r.next,{why:r.why,by:r.by,pass:r.pass});if(g===null)break;spoke.push(r.next)}}
 finally{rounding=false;busy(false);setStatus('online')}}
$('#keep').onclick=()=>{if(!ctl&&!rounding&&chat)round({keep:true})};

/* roleplay memory section */
function rpMem(){const rp=chat.rp||{},ids=G?G.members:[cur.id];
 return`<details open><summary>Roleplay</summary><label>Romance with each character (your choices and the dice move this; you can adjust it)</label>${ids.map(i=>{const c=memberById(i)||cur,r=rp.rom?.[i]?.v||0;
  return`<label>${esc(c.name)}: <b>${romStage(r)} (${r})</b></label><input type=range min=0 max=100 value=${r} data-m=rom data-c=${i}>`+(rp.rom?.[i]?.ms?.length?`<div class=small>${esc(rp.rom[i].ms.join(' · '))}</div>`:'')}).join('')}`
 +(U.intimacy?`<label style="margin-top:8px">Physical intimacy with each character (adult characters only; you can adjust it)</label>${ids.map(i=>{const c=memberById(i)||cur,iv=rp.intim?.[i]?.iv||0;
  return`<label>${esc(c.name)}: <b>${intimStage(iv)} (${iv})</b></label><input type=range min=0 max=100 value=${iv} data-m=intim data-c=${i}>`+(rp.intim?.[i]?.acts?.length?`<div class=small>${esc(rp.intim[i].acts.join(' · '))}</div>`:'')}).join('')}`:'')
 +`<div class=row><button data-m=rest>🛏 Rest (heal everyone)</button>${rp.combat?.on?'<button class=x data-m=endfight>End the fight</button>':''}</div><div class=small>Set your stats and gear under “About you” in the sidebar. Dice, combat, romance and intimacy can be changed in Settings.</div></details>`}
function renderMemG(){const f=$('#memf'),st=chat.state;
 f.innerHTML=`<details open><summary>Characters in this group</summary>${gmem().map(c=>{const s=mst(c.id);return`<label>${esc(c.name)}: <b>${s.emoji||'😐'} ${esc(s.mood||'neutral')}</b> · feels about you: <b>${stg(s.affection)} (${s.affection})</b></label><input type=range min=0 max=100 value=${s.affection} data-m=gaff data-c=${c.id}>`}).join('')}</details>
 <details open><summary>Scene note</summary><label>Steer the situation. It stays in every prompt for this chat.</label><textarea data-m=scene rows=3>${esc(chat.cfg.scene||'')}</textarea></details>
 <details open><summary>Memory of earlier conversation</summary><label>Long chats are summarised automatically. You can edit it.</label><textarea data-m=summary rows=6>${esc(st.summary||'')}</textarea><div class=row><button data-m=sumnow>Summarize now</button><span class=small id=msum></span></div></details>`+(U.mem?gmem().filter(c=>c.id!='__narrator__').map(c=>memHtml(mst(c.id),c.name,c.id)).join(''):'')+rpMem()}
function renderMem(){if(!chat?.state){$('#memf').innerHTML='<p class=small>Open a chat first.</p>';return}if(G)renderMemG();else{renderMemOne();$('#memf').insertAdjacentHTML('beforeend',rpMem())}persMem()}
