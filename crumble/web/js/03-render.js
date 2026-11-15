/* ---------- rendering ---------- */
function msgHTML(m,i){
 if(m.ooc)return oocHTML(m,i);
 const u=m.role=='user',sp=u?null:(G?(memberById(m.cid)||{name:m.name||'?'}):cur),n=u?uname():(sp?.name||'Character'),mode=chat.cfg.mode,last=i==hist.length-1;
 let tx;
 if(u)tx=`<div class=tx>${fmt(m.content,mode!='text',true)}</div>`;
 else{const s=split(m.content),parts=mode=='text'?s.body.split(/\n+/).filter(Boolean):[s.body];
  tx=parts.map(p=>{const h=fmt(p,mode!='text');return h?`<div class=tx>${h}</div>`:''}).join('')||'<div class=tx><span class=small>…</span></div>'}
 const th=u?'':(m.think||split(m.content).th),think=U.think&&th?`<details class=think><summary>Thought process</summary><div>${esc(th)}</div></details>`:'';
 const acts=`<div class=acts><button data-a=copy title=Copy>⧉</button><button data-a=edit title=Edit>✎</button>${u?'':'<button data-a=react title=React>☺</button><button data-a=speak title="Read aloud">🔊</button>'}<button data-a=rewind title="Delete this and everything after">⏪</button><button data-a=del title="Delete message">🗑</button>
  <span class=rxp>${['👍','❤️','😂','😮','😢','😡'].map(e=>`<button data-a=rx data-e=${e}>${e}</button>`).join('')}</span></div>`;
 const nx=hist[i+1],seen=u&&U.stamps&&nx&&nx.role=='assistant'&&nx.seen?`<div class=seen>Seen ${hm(nx.seen)}</div>`:'';
 const sw=!u&&last&&m.sw&&m.sw.length>1?`<div class=sw><button data-a=swp>‹</button>${m.si+1} / ${m.sw.length}<button data-a=swn>›</button></div>`:'';
 const thought=!u&&U.thoughts&&U.track&&m.thought?`<div class=thought>💭 ${esc(m.thought)}</div>`:'';
 const stat=m.stat?`${m.stat.tok} tokens · ${(m.stat.ms/1000).toFixed(1)}s`+(m.pers?` · voice ${m.pers.score}/100`:''):'';
 return`<div class="m ${m.role}" data-i=${i}>${u?'':avatar(sp)}<div class=bub><div class=nm title="${at(stat)}">${esc(n)}${U.stamps&&m.ts?`<span class=ts>${hm(m.ts)}</span>`:''}${U.persScore&&U.pers&&m.pers?persBadge(m.pers):''}</div>${acts}${think}${tx}${u&&m.card?cardHTML(m.card):''}${m.react?`<span class=rx>${m.react}</span>`:''}${thought}${sw}${seen}</div></div>`}
function draw(){skipTyping();head();const L=$('#log');if(!chat){L.innerHTML='';return}let h=G?grpIntro():'',prev=0;
 hist.forEach((m,i)=>{if(m.ts&&(!prev||m.ts-prev>108e5||new Date(m.ts).toDateString()!=new Date(prev).toDateString()))h+=`<div class=sep>${dayLabel(m.ts)}</div>`;if(m.ts)prev=m.ts;h+=msgHTML(m,i)});
 L.innerHTML=h;if(ctl)showPending(pendLabel);L.scrollTop=L.scrollHeight}
function redrawMsg(i){const e=$(`.m[data-i="${i}"]`);if(e&&hist[i]){const t=document.createElement('div');t.innerHTML=msgHTML(hist[i],i);e.replaceWith(t.firstElementChild)}}
function head(){const c=cur||{name:'Character'},st=G?null:chat?.state;$('#hname').textContent=c.name||'Character';$('#hav').style.cssText=G?`background:${grad(c.name)}`:avs(c);
 $('#hav').innerHTML=G?'👥':avin(c)+(st&&U.track?`<span class=bd>${st.emoji}</span>`:'');setStatus(status);
 const rm=!G&&cur?.id&&chat?.rp?.rom?.[cur.id];$('#hrom').hidden=!(rm&&rm.v>0&&U.romance&&U.rp!='off');if(rm)$('#hrom b').textContent=romStage(rm.v);
 $('#gstrip').hidden=!G;if(G)$('#gstrip').innerHTML=gmem().concat(G.narrator?[NARR]:[]).map(m=>`<div class=av data-mid=${m.id} title="@${at(first(m))}" style="${avs(m)}">${avin(m)}</div>`).join('')+(S.role!='guest'?'<button class=ib id=gedit2 title="Edit group">⚙</button>':'');
 $('#greet').hidden=!!G;cbtDraw();
 $('#hchip').hidden=!(U.track&&st);if(st){$('#hemo').textContent=st.emoji;$('#hmood').textContent=st.mood;$('#hmeter').style.width=st.affection+'%';$('#hstage').textContent=stg(st.affection)}
 $('#mode').value=chat?.cfg.mode||U.mode;$('#len').value=chat?.cfg.length||U.length;oocUI()}
function setStatus(t){status=t;$('#hstat').textContent=t;$('#hstat').classList.toggle('on',t!='online')}
function showPending(l){pendLabel=l;let e=$('#pend');if(!e){e=document.createElement('div');e.id='pend';e.className='m assistant';$('#log').append(e)}
 const w=pendWho||cur;e.innerHTML=avatar(w)+`<div class=bub><div class=nm>${esc(w?.name||'Character')}</div><div class="tx dt"><div class=dots><i></i><i></i><i></i><span>${l}</span></div></div></div>`;
 const L=$('#log');L.scrollTop=L.scrollHeight}
const hidePending=()=>{pendLabel='';$('#pend')?.remove()};
const phase=l=>{setStatus(l);showPending(l)};
function errBox(msg,kind){const e=document.createElement('div');e.className='sys';e.innerHTML=`<span>⚠ ${esc(msg)}</span><button data-a=retry data-k=${kind}>Retry</button>`;$('#log').append(e);$('#log').scrollTop=1e9}
const busy=b=>{$('#send').hidden=b;$('#stop').hidden=!b};
