/* ---------- the living world: story clock, weather, everyone's place in their day (js/22-world.js) ----------
   Everything here is read from the chat by the server (no model call). The header chip shows the story time and the sky; click it for the
   panel: set the clock by hand, skip time, see what each character is doing right now and what is about to happen. */
const WX={rain:['🌧','Rain'],storm:['⛈','Storm'],snow:['❄️','Snow'],fog:['🌫','Fog'],wind:['💨','Windy'],hot:['🥵','Hot'],cold:['🥶','Cold'],clear:['☀️','Clear'],overcast:['☁️','Overcast']};
const W={info:null,open:false,t:0};
const storyCfg=()=>({on:U.story!==false,routines:U.storyRoutines!==false,weather:U.storyWeather||'dynamic',events:U.storyEvents||'normal',humor:U.storyHumor||'auto',endings:U.storyEndings!==false,wildlife:U.storyWildlife||'normal',scare:U.storyScare||'some'});
const wIcon=i=>i.weather&&WX[i.weather]&&i.period!='night'&&i.period!='late at night'?WX[i.weather][0]:/night/.test(i.period||'')?'🌙':/morning/.test(i.period||'')?'🌅':/evening/.test(i.period||'')?'🌇':'🕒';
const wShort=i=>{const m=/^(?:(\w{3})\w*, )?around (.+?) \(/.exec(i.clock||'');return m?(m[1]?m[1]+' ':'')+m[2]:''};
function worldHead(){const e=$('#hworld');if(!e)return;const wk=chat?(chat.id+':'+hist.length+':'+(chat.cfg.start||'')):'';if(wk!==W.key){W.key=wk;if(chat)worldRefresh()}const i=W.info;
 if(!chat||!cur||U.story===false||!i||!i.clock){e.hidden=true;if(W.open)worldClose();return}
 e.hidden=false;e.innerHTML=`<span>${wIcon(i)}</span><b>${esc(wShort(i))}</b>${i.weather?`<span class=small>${esc((WX[i.weather]||[0,i.weather])[1])}</span>`:''}`;
 e.title='Story time, weather and what everyone is doing. Click for details';if(W.open)worldDraw()}
function worldRefresh(now){clearTimeout(W.t);const go=async()=>{if(!chat||!cur?.id||U.story===false){W.info=null;worldHead();return}
  try{const ic=hist.filter(m=>!m.ooc);const r=await api('/api/world','POST',{...(G?{group:G.id}:{cid:cur.id}),history:apiHist(ic),scene:chat.cfg.scene||'',clock:U.timeaware?clock():'',story_start:chat.cfg.start||'',story:storyCfg(),place:placeSpec()});
   if(r&&r.world){W.info=r.world;worldHead()}}catch(e){}};
 if(now)go();else W.t=setTimeout(go,250)}
const freeW=f=>f>=.8?'free to talk':f>=.55?'a bit busy':f>=.3?'busy':'not available';
function worldDraw(){const el=$('#worldpop'),i=W.info;if(!el)return;if(!W.open||!i||!chat){el.hidden=true;return}
 const days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
 const who=(i.who||[]).map(s=>`<div class=wrow><b>${esc(s.name||'')}</b><span>${esc(s.act)}</span><i style="--f:${Math.round(s.free*100)}%" title="${freeW(s.free)}"></i><small>${s.mins<90?`next in ~${s.mins} min: `:'next: '}${esc(s.next)}</small></div>`).join('');
 const wi=i.weather?WX[i.weather]||['🌡',i.weather]:null;
 el.hidden=false;el.innerHTML=`<div class=wh><b>${wIcon(i)} ${esc(i.clock||'The story has no clock yet')}</b><button class=ghost data-w=x>✕</button></div>
 <div class=wsec><div class=small>${i.day?(i.who?.[0]?.weekend?'Weekend':'Weekday'):''}${i.season?' · '+esc(i.season):''}${i.real?' · following the real clock':''}</div>
 ${wi?`<div class=wline>${wi[0]} <b>${wi[1]}</b>${i.trend?` <span class=small>${esc(i.trend)}</span>`:''}<span class=small> · ${i.wsrc=='story'?'set by the story':'today\'s weather'}</span></div>`:''}
 ${i.place?`<div class=wline>📍 ${esc(i.place)} <span class=small>${i.indoors===false?'outdoors':i.indoors?'indoors':''}</span></div>`:''}
 ${i.tension?`<div class=wline>${i.tension>1?'⚠ <b>Danger</b>':'🌩 <b>Tension</b>'} <span class=small>${i.tension>1?'Real danger is in the scene.':'Things are heated.'}</span></div>`:''}
 ${i.beat?`<div class="small wbeat">Just now in the world: ${esc(i.beat)}</div>`:''}</div>
 ${who?`<div class=wsec><div class=lb>Right now</div>${who}</div>`:''}
 <div class=wsec><div class=lb>Time</div><div class=wset><select id=wday>${days.map(d=>`<option>${d}</option>`).join('')}</select><input id=wtime type=time value="08:00"><button data-w=set>Set the clock</button></div>
  <div class=wset><button data-w=skip data-s="30 minutes">+30 min</button><button data-w=skip data-s="2 hours">+2 h</button><button data-w=skip data-s="evening">Evening</button><button data-w=skip data-s="night">Night</button><button data-w=skip data-s="morning">Next morning</button></div>
  <div class=small>Setting the clock only tells the story where it begins; skipping adds a short “later” line to the chat. Characters live by this clock: they sleep, work, get hungry, and have to leave.</div></div>`;
 if(chat.cfg.start){const m=/^(\w+) (\d+):(\d+)\s*(AM|PM)/i.exec(chat.cfg.start);if(m){$('#wday').value=days.find(d=>d.startsWith(m[1]))||'Monday';let h=+m[2]%12+(/pm/i.test(m[4])?12:0);$('#wtime').value=String(h).padStart(2,'0')+':'+m[3]}}}
const worldClose=()=>{W.open=false;const e=$('#worldpop');if(e)e.hidden=true};
function worldSkip(arg){const a=(arg||'').trim().toLowerCase();
 if(/^(?:the )?next morning$|^morning$/.test(a))return'*The next morning.*';if(/^evening$/.test(a))return'*That evening.*';if(/^night$/.test(a))return'*Later that night.*';
 if(/^\d+(?:\.\d+)?\s*(?:min|minute|hour|hr|day)s?$/.test(a)||/^(?:an?|one|two|three|four|five|six|half an?)\s+(?:minute|hour|day)s?$/.test(a))return`*${a.replace(/^\d/,x=>x)} later.*`.replace(/^\*(\d+)\s*(min|hr)s?\b/,(m,n,u)=>`*${n} ${u=='min'?'minutes':'hours'}`);
 return`*${arg||'A little while'} later.*`}
$('#hworld')?.addEventListener('click',()=>{W.open?worldClose():(W.open=true,worldDraw())});
$('#worldpop')?.addEventListener('click',e=>{const b=e.target.closest('button');if(!b||!chat)return;const k=b.dataset.w;
 if(k=='x')worldClose();
 else if(k=='set'){const d=$('#wday').value,[h,m]=($('#wtime').value||'08:00').split(':').map(Number);chat.cfg.start=`${d} ${h%12||12}:${String(m).padStart(2,'0')} ${h<12?'AM':'PM'}`;saveChat();worldRefresh(true)}
 else if(k=='skip'&&!ctl&&!rounding){worldClose();post(worldSkip(b.dataset.s))}});
document.addEventListener('click',e=>{if(W.open&&!e.target.closest('#worldpop,#hworld'))worldClose()});

/* ---------- wildlife encounters: the card on a reply that tells one (js/22-world.js) ---------- */
const WMOOD={awe:['Awe','a quiet, strange sighting'],fun:['Fun','something charming'],tense:['Tense','something is not right'],terror:['Terror','real danger']};
const WEMO={Mammal:'🐾',Bird:'🐦',Reptile:'🦎',Amphibian:'🐸',Fish:'🐟',Insect:'🐞',Arachnid:'🕷',Crustacean:'🦀',Mollusk:'🐚',Cnidarian:'🪼',Echinoderm:'⭐',Annelid:'🪱'};
function wildHTML(w){if(!w||!w.name||U.story===false)return'';const mo=WMOOD[w.mood]||WMOOD.awe,pips=Array.from({length:w.of||1},(_,k)=>`<i${k<w.stage?' class=on':''}></i>`).join('');
 const img=w.sprite?`<img src="${at(w.sprite)}" alt="" loading=lazy onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'wemo',textContent:'${WEMO[w.class]||'🐾'}'}))">`:`<span class=wemo>${WEMO[w.class]||'🐾'}</span>`;
 return`<div class="wild w-${w.mood}" title="${at(w.sci||'')}">${img}<div class=wi><b>${esc(w.name)}</b><span class=small>${mo[0]} · ${esc(w.habitat||'')}</span></div><span class=pips title="${at(mo[1])}">${pips}</span></div>`}
