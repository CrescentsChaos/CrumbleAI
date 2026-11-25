/* ---------- places: location cards you can explore (js/23-places.js) ----------
   A place card has a name, biome, description, atmosphere, a background picture, objects, characters, activities, exits, events, history and secrets.
   The chat stands in one place at a time (chat.cfg.places is a small log, so rewinding walks you back). The server reads the card itself on every
   reply; guests only ever get the public view of a card. In a one-to-one chat, residents of the place can wander over and talk (js/06-generate.js
   asks /api/places/visit after each reply). */
const PL={list:[],loaded:false,open:false,tab:'here',view:'',force:'',biomes:[],edit:null,chip:null,bgSet:'',q:'',biomeF:'',sheetAll:false,allPpl:false,bgData:'',bgClear:false};
try{if(U.placeVisitors===undefined)U.placeVisitors='normal';if(U.placeBg===undefined)U.placeBg=true}catch(e){}
const plGuest=()=>S.role=='guest';
const plChars=()=>S.chars||[];
const placeChar=id=>plChars().find(c=>c.id==id);
const plById=id=>PL.list.find(p=>p.id==id);
const plByName=n=>{n=(n||'').trim().toLowerCase();return n?PL.list.find(p=>p.name.toLowerCase()==n):null};
const lowerFirst=s=>s?s[0].toLowerCase()+s.slice(1):s;
const nounPhrase=n=>{n=(n||'').trim();if(/^(the|a|an|some|my|our|his|her|their|this|that)\b/i.test(n))return n.replace(/^The\b/,'the');
 const caps=n.split(/\s+/).filter(x=>/^[A-Z]/.test(x)).length;if(caps>1)return n;return'the '+(/^[A-Z][a-z]/.test(n)?lowerFirst(n):n)};
const exitName=t=>(t||'').split(/\s*(?:[:\u2192\u2014]|->| - )\s*/)[0].trim();
const exitPlace=t=>{const n=exitName(t).toLowerCase();return PL.list.find(p=>p.name.toLowerCase()==n)||PL.list.find(p=>n.length>3&&(n.includes(p.name.toLowerCase())||p.name.toLowerCase().includes(n)))||null};

async function placesLoad(force){if(PL.loaded&&!force)return;
 try{const r=await api('/api/places');if(r&&r.places){PL.list=r.places;PL.biomes=r.biomes||[];PL.loaded=true;placeHead();placeBg();if(PL.open)placeDraw();if(!$('#places').hidden)placesRender()}}catch(e){}}

/* where the chat stands: the last entry of the log that is still part of the story (rewinding removes the message it came with) */
function curPlace(){if(!chat)return null;let e=null;for(const x of chat.cfg.places||[])if(x.since<hist.length||x.since===0)e=x;
 return e&&e.id?{id:e.id,since:e.since,card:plById(e.id)||null}:null}
const placeSpec=()=>{const p=curPlace();return p?{id:p.id,since:p.since}:undefined};
/* the place the story stood in after its first n messages (a summary of the first n messages remembers where they ended) */
const placeSpecAt=n=>{let e=null;for(const x of chat?.cfg.places||[])if(x.since<n||x.since===0)e=x;return e&&e.id?{id:e.id,since:e.since}:undefined};
function setPlace(id,o={}){if(!chat)return;const lg=(chat.cfg.places||[]).filter(x=>x.since<hist.length||x.since===0);
 lg.push({id:id||'',since:o.silent?Math.max(0,hist.length-1):hist.length});chat.cfg.places=lg;saveChat();head();worldRefresh(true)}

/* header chip and background picture */
function placeHead(){if(!PL.chip){const hw=$('#hworld');if(!hw)return;const c=document.createElement('button');c.id='hplace';c.type='button';c.className=hw.className;
  c.addEventListener('click',()=>PL.open?placeClose():placeOpen());hw.after(c);PL.chip=c}
 const e=PL.chip,p=chat&&cur?curPlace():null;e.hidden=!(chat&&cur);if(e.hidden){if(PL.open)placeClose();return}
 e.innerHTML=`<span>📍</span><b>${esc(p?(p.card?p.card.name:'…'):'Places')}</b>`;e.title='Places: where this chat takes place. Click to explore, change place or manage cards';
 if(!PL.loaded)placesLoad();if(PL.open)placeDraw()}
function placeBg(){const ch=$('#chat');if(!ch)return;const p=curPlace(),c=p&&p.card;
 if(c&&c.bg_url&&U.placeBg!==false){ch.style.setProperty('--placeimg',`url("${String(c.bg_url).replace(/["\\\n]/g,'')}")`);ch.dataset.pbg='1'}
 else{delete ch.dataset.pbg;ch.style.removeProperty('--placeimg')}
 const L=$('#log');if(L&&PL.bgSet){L.style.backgroundImage='';L.style.backgroundSize='';L.style.backgroundPosition='';PL.bgSet=''}}   // (older builds painted the log itself)

/* the panel */
function placeOpen(tab){PL.open=true;PL.tab=tab||(curPlace()?'here':'all');PL.view='';placesLoad(true);placeDraw()}
function placeClose(){PL.open=false;const e=$('#placepop');if(e)e.hidden=true}
function plPop(){let e=$('#placepop');if(!e){e=document.createElement('div');e.id='placepop';e.hidden=true;document.body.append(e);
  e.addEventListener('click',plClick)}return e}
const plList=(a,cls='')=>a&&a.length?`<ul class="pl-list ${cls}">${a.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'';
function plDetail(p){const cur_=curPlace(),here=cur_&&cur_.id==p.id,adm=!plGuest(),can=here&&chat,
 chip=(act,v,txt,extra='')=>can?`<button class="pl-chip" data-pa=${act} data-v="${at(v)}"${extra}>${esc(txt)}</button>`:`<span class="pl-chip off">${esc(txt)}</span>`,
 ppl0=(p.characters||[]).map(placeChar).filter(Boolean),ppl=PL.allPpl?ppl0:ppl0.slice(0,6),
 sec=(t,h)=>h?`<div class=pl-sec><div class=lb>${t}</div>${h}</div>`:'';
 return`<div class=pl-hero style="background-image:${p.bg_url?`linear-gradient(transparent 20%,rgba(0,0,0,.72)),url('${at(p.bg_url)}')`:`linear-gradient(transparent 20%,rgba(0,0,0,.55)),${grad(p.name)}`}"><div class=pl-ht><b>${esc(p.name)}</b>${p.biome?`<span class=pl-biome>${esc(p.biome)}</span>`:''}${here?'<span class=pl-here>You are here</span>':''}</div></div>
 ${p.description?`<p class=pl-desc>${esc(p.description)}</p>`:''}${p.atmosphere?`<p class=pl-atm>${esc(p.atmosphere)}</p>`:''}
 ${sec('Objects',(p.objects||[]).length?`<div class=pl-chips>${p.objects.map(x=>chip('obj',x,x)).join('')}</div>`:'')}
 ${sec('Activities',(p.activities||[]).length?`<div class=pl-chips>${p.activities.map(x=>chip('act',x,x)).join('')}</div>`:'')}
 ${sec('Lives or turns up here',ppl0.length?`<div class=pl-chips>${ppl.map(c=>{const mine=!G&&cur&&c.id==cur.id,dg=sceneOn()?doingNow()?.people?.[c.id]:null;if(sceneOn())return `<span class="pl-chip pl-who off${dg&&dg.here?'':' away'}"><span class=av style="${avs(c)}">${avin(c)}</span>${esc(c.name)}<small> · ${esc(dg?(dg.here?dg.doing||'here':dg.away||'not here'):'not around')}</small></span>`;return can&&!mine&&!G?`<button class="pl-chip pl-who" data-pa=call data-v="${at(c.id)}"><span class=av style="${avs(c)}">${avin(c)}</span>${esc(c.name)}</button>`:`<span class="pl-chip pl-who off"><span class=av style="${avs(c)}">${avin(c)}</span>${esc(c.name)}${mine?' (with you)':''}</span>`}).join('')}</div>${ppl0.length>6?`<button class="pl-chip pl-more" data-pa=morepl>${PL.allPpl?'Show fewer':'+'+(ppl0.length-6)+' more'}</button>`:''}${can&&!G&&!ppl.every(c=>cur&&c.id==cur.id)?'<div class=small>Tap someone to call them over, or just speak to them by name.</div>':''}`:'')}
 ${sec('Exits',(p.exits||[]).length?`<div class=pl-chips>${p.exits.map(x=>{const t=exitPlace(x);return can?`<button class="pl-chip pl-exit" data-pa=exit data-v="${at(x)}" title="${at(t?'Go to '+t.name:'Just a direction')}">➜ ${esc(x)}</button>`:`<span class="pl-chip off">➜ ${esc(x)}</span>`}).join('')}</div>`:'')}
 ${adm&&(p.history||(p.events||[]).length||(p.secrets||[]).length)?`<details class=pl-auth><summary>Author notes (guests cannot see these)</summary>${p.history?sec('History',`<p class=pl-desc>${esc(p.history)}</p>`):''}${sec('Events',plList(p.events))}${sec('Secrets',plList(p.secrets))}</details>`:''}
 <div class=pl-foot>${chat?(here?'<button class=ghost data-pa=leave>Leave this place</button>':`<button data-pa=go data-v="${at(p.id)}">Go here</button>`):''}${adm?`<button class=ghost data-pa=edit data-v="${at(p.id)}">Edit</button><button class=ghost data-pa=del data-v="${at(p.id)}">Delete</button>`:''}</div>`}
const plCards=()=>PL.list.filter(p=>plMatch(p,PL.q)).map(p=>`<button class="pl-card${(curPlace()||{}).id==p.id?' on':''}" data-pa=view data-v="${at(p.id)}" style="background-image:${p.bg_url?`linear-gradient(transparent 30%,rgba(0,0,0,.75)),url('${at(p.bg_url)}')`:`linear-gradient(transparent 30%,rgba(0,0,0,.5)),${grad(p.name)}`}"><b>${esc(p.name)}</b><span>${esc(p.biome||'')}${(p.characters||[]).length?` · ${p.characters.length} ${p.characters.length==1?'person':'people'}`:''}</span></button>`).join('');
function plGallery(){const adm=!plGuest();
 return`<label class=pl-find>${ico('search')}<input id=plq placeholder="Search places" value="${at(PL.q)}" autocomplete=off></label><div class=pl-grid id=plgrid>${plCards()}${adm?'<button class="pl-card pl-new" data-pa=new>＋<span>New place</span></button>':''}</div>${PL.list.length||adm?'':'<div class=small>The host has not made any places yet.</div>'}<div class=pl-foot><button class=ghost data-pa=page>Open the Places page</button></div>`}
function placeDraw(){const el=plPop();if(!PL.open||!chat){el.hidden=true;return}
 const c=curPlace(),shown=PL.view?plById(PL.view):(PL.tab=='here'?(c&&c.card):null),tab=PL.view?'all':PL.tab;
 el.hidden=false;el.innerHTML=`<div class=wh><b>📍 ${shown?esc(shown.name):'Places'}</b><span class=pl-tabs><button data-pa=tab data-v=here class="${tab=='here'?'on':''}">Here</button><button data-pa=tab data-v=all class="${tab=='all'?'on':''}">All places</button></span><button class=ghost data-pa=x>✕</button></div>
 ${PL.view&&shown?'<button class="ghost pl-back" data-pa=back>‹ All places</button>':''}
 ${shown?plDetail(shown):tab=='here'?`<div class=pl-empty>${c?'This place has been deleted.':'This chat is not at any place yet.'}<br><button data-pa=tab data-v=all>Choose a place</button></div>`:plGallery()}`}
function plClick(e){const b=e.target.closest('button[data-pa]');if(!b)return;const k=b.dataset.pa,v=b.dataset.v,busyNow=!chat||ctl||rounding;
 if(k=='x')return placeClose();
 if(k=='tab'){PL.tab=v;PL.view='';return placeDraw()}
 if(k=='view'){PL.view=v;return placeDraw()}
 if(k=='back'){PL.view='';return placeDraw()}
 if(k=='new'){return placeEditor(null)}
 if(k=='page'){placeClose();return tab('places')}
 if(k=='morepl'){PL.allPpl=!PL.allPpl;return placeDraw()}
 if(k=='edit')return placeEditor(plById(v));
 if(k=='del')return placeDelete(v);
 if(busyNow)return;
 if(k=='go'){const p=plById(v);if(p)placeGo(p.id,`*We make our way to ${nounPhrase(p.name)}.*`)}
 else if(k=='leave'){placeClose();if(sceneOn())return void sceneLeave();setPlace('');post('*We head out.*')}
 else if(k=='obj')placeSay(`*I take a closer look at ${nounPhrase(v)}.*`);
 else if(k=='act')placeSay(`*I suggest we ${lowerFirst(v)}.*`);
 else if(k=='call'){const c=placeChar(v);if(c){PL.force=c.id;placeSay(`*I call ${first(c)} over.*`)}}
 else if(k=='exit'){const t=exitPlace(v);if(t)placeGo(t.id,`*We head for ${nounPhrase(exitName(v))}.*`);else placeSay(`*We head for ${nounPhrase(exitName(v))}.*`)}}
function placeSay(t){placeClose();post(t)}
function placeGo(id,line){if(!chat||ctl||rounding)return;placeClose();if(sceneOn())return void sceneOpen(id);setPlace(id);post(line)}
document.addEventListener('click',e=>{if(PL.open&&!e.target.closest('#placepop,#hplace'))placeClose()});
document.addEventListener('input',e=>{if(e.target.id=='plq'){PL.q=e.target.value;const g=$('#plgrid');if(g)g.innerHTML=plCards()+(plGuest()?'':'<button class="pl-card pl-new" data-pa=new>＋<span>New place</span></button>')}});

/* ---------- the Places page (gallery, search, place sheet) ---------- */
const plMatch=(p,q)=>{q=(q||'').trim().toLowerCase();if(!q)return true;
 const t=[p.name,p.biome,p.description,p.atmosphere,(p.objects||[]).join(' '),(p.characters||[]).map(i=>placeChar(i)?.name||'').join(' ')].join(' ').toLowerCase();return q.split(/\s+/).every(w=>t.includes(w))};
const plBlurb=p=>{const t=(p.description||p.atmosphere||'').replace(/\s+/g,' ').trim(),m=t.match(/^.{24,150}?[.!?](\s|$)/);return m?m[0].trim():t.slice(0,140)};
function plCard(p){const c=curPlace(),here=c&&c.id==p.id,n=(p.characters||[]).length;
 return`<button class="card plc" data-pid="${at(p.id)}" style="--h:${hue(p.name)};--s:44%"><div class="art${p.bg_url?'':' ph'}" style="${p.bg_url?`background-image:url('${at(p.bg_url)}')`:''}">${p.bg_url?'':ico('pin')}</div>${here?`<span class=cm>${ico('pin')}Here</span>`:''}\
<div class=cb><span class=cn>${esc(p.name)}</span><span class=cs>${esc(plBlurb(p))}</span><div class=ct>${p.biome?`<i>${esc(p.biome)}</i>`:''}${n?`<i>${n} ${n==1?'person':'people'}</i>`:''}</div></div></button>`}
function placesPage(){placesRender();placesLoad(true)}
function placesRender(){const el=$('#pgrid');if(!el||!PL)return;const q=$('#ps2').value||'',adm=!plGuest(),bc={};
 PL.list.forEach(p=>p.biome&&(bc[p.biome]=(bc[p.biome]||0)+1));const top=Object.entries(bc).sort((a,b)=>b[1]-a[1]).slice(0,12).map(x=>x[0]);if(PL.biomeF&&!top.includes(PL.biomeF))PL.biomeF='';
 $('#ptags').innerHTML=top.length>1?`<button class="tagc${PL.biomeF?'':' on'}" data-bm="">All</button>`+top.map(t=>`<button class="tagc${t==PL.biomeF?' on':''}" data-bm="${at(t)}">${esc(t)}</button>`).join(''):'';
 const list=PL.list.filter(p=>plMatch(p,q)&&(!PL.biomeF||p.biome==PL.biomeF));
 $('#pcnt').textContent=PL.list.length?`${PL.list.length} ${PL.list.length==1?'place':'places'}${q.trim()||PL.biomeF?`, ${list.length} shown`:''}. Any chat can be set in any of them.`:(PL.loaded?(adm?'No places yet. Make one for your characters to live in.':'The host has not made any places yet.'):'Loading…');
 el.innerHTML=(adm?`<button class="card new" data-act=new>${ico('pin')}<b>New place</b><small>Blank card or AI draft</small></button>`:'')+list.map(plCard).join('')+(PL.list.length&&!list.length?'<div class="small pl-none">No place matches that.</div>':'')}
$('#ps2').oninput=placesRender;$('#pnew').onclick=()=>placeEditor(null);
$('#places').onclick=e=>{const t=e.target.closest('[data-bm]');if(t){PL.biomeF=t.dataset.bm;return placesRender()}
 const b=e.target.closest('.card');if(!b)return;if(b.dataset.pid)return openPlaceSheet(b.dataset.pid);if(b.dataset.act=='new')placeEditor(null)};
$('#pgrid').addEventListener('pointermove',e=>{if(e.pointerType!='mouse'||calm.matches)return;const c=e.target.closest('.card:not(.new)');if(!c)return;const r=c.getBoundingClientRect(),px=(e.clientX-r.left)/r.width-.5,py=(e.clientY-r.top)/r.height-.5;
 c.classList.add('t');c.style.setProperty('--ry',(px*7).toFixed(2)+'deg');c.style.setProperty('--rx',(-py*7).toFixed(2)+'deg')});
$('#pgrid').addEventListener('pointerout',e=>{const c=e.target.closest('.card');if(c&&!c.contains(e.relatedTarget)){c.classList.remove('t');c.style.removeProperty('--ry');c.style.removeProperty('--rx')}});
const closePSheet=()=>{$('#pview').hidden=true};
function openPlaceSheet(id){const p=plById(id);if(!p)return;PL.sheetAll=false;placeSheetDraw(p);$('#pview').hidden=false}
function placeSheetDraw(p){const adm=!plGuest(),c=curPlace(),here=c&&c.id==p.id,ppl=(p.characters||[]).map(placeChar).filter(Boolean),show=PL.sheetAll?ppl:ppl.slice(0,6),
 sec=(t,v)=>v&&v.trim()?`<div><h3>${t}</h3><p>${esc(v.trim())}</p></div>`:'',cnt=(k,w,w1)=>(p[k]||[]).length?`<span><b>${p[k].length}</b> ${p[k].length==1?w1:w}</span>`:'';
 const v=$('#pview');v.dataset.id=p.id;
 v.innerHTML=`<div class=mbox style="--h:${hue(p.name)}" role=dialog aria-modal=true aria-label="${at(p.name)}"><button class=mclose data-x=1 title=Close>${ico('close')}</button>
 <div class="mart${p.bg_url?'':' ph'}" style="${p.bg_url?`background-image:url('${at(p.bg_url)}')`:''}">${p.bg_url?'':`<div class=big>${ico('pin')}</div>`}<div class=cap><b>${esc(p.name)}</b><span>${esc([p.biome,here?'You are here':''].filter(Boolean).join(' · ')||'No biome set')}</span></div></div>
 <div class=mbody>${sec('About',p.description)}${sec('Atmosphere',p.atmosphere)}
 ${ppl.length?`<div><h3>Lives or turns up here</h3><div class=pv-ppl>${show.map(x=>`<span class=mp-chip>${avatar(x,'sm')}<b>${esc(x.name)}</b></span>`).join('')}${ppl.length>6?`<button type=button class=mp-more data-sa=more>${PL.sheetAll?'Show fewer':`+${ppl.length-6} more`}</button>`:''}</div></div>`:''}
 <div class=mfacts>${cnt('objects','objects','object')}${cnt('activities','activities','activity')}${cnt('exits','exits','exit')}</div>
 <div class=pv-visit><button class=go data-sa=visit>Visit ${esc(p.name)}</button><span id=pv-last></span>
  <div class=small>You walk in on your own. Whoever lives or turns up here is only there if they would be, busy with their own things, and meets you the way they would, not as a host.</div></div>
 <details class=pv-with><summary>Go there with someone</summary><div id=pv-pick></div></details>
 <div class=mact>${chat?(here?'<button class=go data-sa=leave>Leave this place</button>':'<button class=go data-sa=use>Use in current chat</button>'):''}${adm?`<button data-sa=edit>${ico('edit')}Edit</button><button class=x data-sa=del>${ico('trash')}Delete</button>`:''}</div></div></div>`;
 mpMount('#pv-pick','pv',{pool:()=>[...mpChars(),...(S.groups||[]).map(g=>({id:'g:'+g.id,name:g.name,group:1,sub:g.members.map(i=>memberById(i)?.name||'?').slice(0,4).join(', ')}))],
  placeholder:'Search a character or group…',hint:'Pick someone to go there with you. They come along as your companion.',pick:id=>placeChatHere(p.id,id)});
 api('/api/chats/pl_'+p.id).then(r=>{const l=(r&&r.chats)||[],e=$('#pv-last');if(e&&l.length&&$('#pview').dataset.id==p.id)e.innerHTML=`<button data-sa=cont>Continue last visit</button>`}).catch(()=>{})}
$('#pview').onclick=e=>{if(e.target==$('#pview')||e.target.closest('[data-x]'))return closePSheet();const b=e.target.closest('[data-sa]');if(!b)return;const id=$('#pview').dataset.id,p=plById(id),a=b.dataset.sa;if(!p)return;
 if(a=='more'){PL.sheetAll=!PL.sheetAll;return placeSheetDraw(p)}closePSheet();
 if(a=='visit'){closePSheet();sceneOpen(id)}else if(a=='cont'){closePSheet();sceneOpen(id,{last:true})}else if(a=='use'){setPlace(id,{silent:true});placeHead();placeBg();tab('chat')}else if(a=='leave'){setPlace('');placeHead();placeBg();tab('chat')}
 else if(a=='edit')placeEditor(p);else if(a=='del')placeDelete(id)};
document.addEventListener('keydown',e=>{if(e.key=='Escape'&&!$('#pview').hidden)closePSheet()});
async function placeChatHere(pid,id){closePSheet();
 try{if(String(id).startsWith('g:'))await pickGroup(String(id).slice(2));else await pick(id);if(hist.some(m=>m.role=='user'))await newChat();
  setPlace(pid,{silent:true});placeHead();placeBg();tab('chat')}catch(e){}}

/* ---------- the place editor: a full page, like the character editor ---------- */
const PE_LISTS=[['objects','Objects','the brass telescope\nan old jukebox','Things that can be seen, touched or used. One per line, written like “the brass telescope”.'],
 ['activities','Activities','watch the boats\nplay a record','What people do here. One per line, as short verb phrases.'],
 ['exits','Exits','The Pier\nLighthouse Road','Where you can go from here. Use the name of another place to make it a one-click trip.'],
 ['events','Events','A fog horn sounds far out.\nThe lights flicker.','Things that can happen here now and then (guests never see these).'],
 ['secrets','Secrets','There is a trapdoor under the jukebox.','Hidden truths. They only come out when you search, investigate or ask the right person (guests never see these).']];
const peVal=k=>(document.querySelector(`#pedit [data-pk=${k}]`)?.value||'').trim();
const peBiome=()=>{const s=$('#pe-biome');return !s?'':s.value=='__other'?peVal('biome2'):s.value};
const peList=k=>{const x=PE_LISTS.find(a=>a[0]==k),d=PL.edit;return`<label>${x[1]}</label><textarea data-pk=${k} rows=3 placeholder="${at(x[2])}">${esc((d[k]||[]).join('\n'))}</textarea><div class="small pe-h">${x[3]}</div>`};
function placeEditor(p){placeClose();PL.edit=p?{...p}:{id:'',name:'',biome:'',description:'',atmosphere:'',history:'',objects:[],activities:[],exits:[],events:[],secrets:[],characters:[],bg:'',bg_url:''};PL.bgData='';PL.bgClear=false;
 const d=PL.edit,known=!d.biome||PL.biomes.includes(d.biome);
 $('#pform').innerHTML=`<details open><summary>Basics</summary><div class=pe-row><div><label>Name</label><input data-pk=name maxlength=80 value="${at(d.name)}" placeholder="e.g. Harbour Café"></div>
 <div><label>Biome</label><select id=pe-biome><option value="">(none)</option>${PL.biomes.map(b=>`<option${b==d.biome?' selected':''}>${esc(b)}</option>`).join('')}<option value=__other${known?'':' selected'}>Other…</option></select>
 <input id=pe-biome2 data-pk=biome2 maxlength=60 placeholder="Your own biome" value="${known?'':at(d.biome)}" ${known?'hidden':''} style="margin-top:8px"></div></div>
 <label>Description</label><textarea data-pk=description rows=4 placeholder="What this place is and what it looks like">${esc(d.description)}</textarea>
 <label>Atmosphere</label><textarea data-pk=atmosphere rows=2 placeholder="Sounds, smells, light, temperature, mood">${esc(d.atmosphere)}</textarea></details>
 <details open><summary>Who lives or turns up here</summary><div class="small pe-h">They are not always in and do not open a chat. When you visit, the AI decides who is around, what they are doing and how they meet you.</div><div id=pe-mem></div></details>
 <details open><summary>Chat background</summary><div class=pe-chatprev id=pe-prev><div class="pb bot">Salt wind rattles the shutters.</div><div class="pb me">*I look around the room.*</div></div>
 <div class=row style="margin-top:10px"><button type=button id=pe-pick2>${ico('upload')}Choose a picture</button><button type=button class=x id=pe-rm2>${ico('trash')}Remove</button></div>
 <div class="small pe-h">It shows behind the messages of every chat that is set in this place, one-to-one or group. Large pictures are shrunk automatically.</div></details>
 <details><summary>Things here</summary>${peList('objects')}${peList('activities')}${peList('exits')}</details>
 <details><summary>Author notes (guests cannot see these)</summary>${peList('events')}${peList('secrets')}<label>History</label><textarea data-pk=history rows=3 placeholder="What happened here before the story began">${esc(d.history)}</textarea></details>`;
 mpMount('#pe-mem','pm',{sel:d.characters||[],pool:mpChars,max:16,empty:'Nobody lives here yet. Search to add people.',hint:'They belong here: they can be in the background, and in a one-to-one chat they may wander over and talk to you.',onChange:peLive});
 $('#pe-biome').onchange=()=>{$('#pe-biome2').hidden=$('#pe-biome').value!='__other';peLive()};
 $('#pe-pick2').onclick=()=>$('#pefile').click();$('#pe-rm2').onclick=peNoBg;
 $('#pedel').hidden=!d.id;$('#pe-err').textContent='';$('#pe-concept').value='';$('#pe-gstat').textContent='';peLive();tab('pedit');$('#pedit').scrollTop=0}
function peLive(){if(!PL.edit||$('#pedit').hidden&&!$('#pform').children.length)return;const n=peVal('name'),b=peBiome(),ids=mpSelected('pm'),url=PL.bgClear?'':(PL.bgData||PL.edit.bg_url||'');
 $('#pen').textContent=n||'New place';$('#pet').innerHTML=[b,ids.length?`${ids.length} ${ids.length==1?'person':'people'}`:''].filter(Boolean).map(x=>`<i>${esc(x)}</i>`).join('');
 const a=$('#peart');a.style.backgroundImage=url?`url("${String(url).replace(/["\\\n]/g,'')}")`:grad(n||'?');a.innerHTML=url?'':ico('pin');
 const pv=$('#pe-prev');if(pv)pv.style.backgroundImage=url?`linear-gradient(color-mix(in srgb,var(--bg) 34%,transparent),color-mix(in srgb,var(--bg) 58%,transparent)),url("${String(url).replace(/["\\\n]/g,'')}")`:'none'}
document.querySelector('#pedit').addEventListener('input',e=>{if(e.target.matches('[data-pk=name],[data-pk=biome2]'))peLive()});
function plImg(file){return new Promise((ok,no)=>{const r=new FileReader();r.onerror=()=>no(new Error('Could not read that file.'));
 r.onload=()=>{const im=new Image();im.onerror=()=>no(new Error('That is not a picture.'));
  im.onload=()=>{const s=Math.min(1,1600/Math.max(im.width,im.height)),c=document.createElement('canvas');c.width=Math.round(im.width*s);c.height=Math.round(im.height*s);c.getContext('2d').drawImage(im,0,0,c.width,c.height);ok(c.toDataURL('image/jpeg',.82))};
  im.src=r.result};r.readAsDataURL(file)})}
const peErr=t=>{$('#pe-err').textContent=t||''};
function peNoBg(){PL.bgData='';PL.bgClear=true;peLive()}
$('#pebg').onclick=()=>$('#pefile').click();$('#pebgrm').onclick=peNoBg;
$('#pefile').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f||!PL.edit)return;try{PL.bgData=await plImg(f);PL.bgClear=false;peErr('');peLive()}catch(x){peErr(x.message)}};
$('#pe-draft').onclick=async()=>{const c=$('#pe-concept').value.trim();if(!c)return;const b=$('#pe-draft');b.disabled=true;peErr('');$('#pe-gstat').textContent='Drafting... (can take a minute)';
 try{const r=await api('/api/gen_place','POST',{concept:c});if(r.err)throw new Error(r.err);
  for(const f of ['name','description','atmosphere','history'])if(r[f]){const e=document.querySelector(`#pedit [data-pk=${f}]`);if(e)e.value=r[f]}
  for(const [f] of PE_LISTS)if(r[f]&&r[f].length){const e=document.querySelector(`#pedit [data-pk=${f}]`);if(e)e.value=r[f].join('\n')}
  if(r.biome){const s=$('#pe-biome');if(PL.biomes.includes(r.biome))s.value=r.biome;else{s.value='__other';$('#pe-biome2').value=r.biome}$('#pe-biome2').hidden=s.value!='__other'}
  $('#pe-gstat').textContent='Done. Review the fields, then save.';peLive()}catch(x){$('#pe-gstat').textContent='';peErr(x.message||'The model could not draft that.')}b.disabled=false};
$('#pecancel').onclick=()=>{PL.edit=null;tab('places')};
$('#pedel').onclick=()=>{const id=PL.edit&&PL.edit.id;if(id)placeDelete(id)};
$('#pesave').onclick=async()=>{const d=PL.edit;if(!d)return;
 const o={id:d.id||undefined,name:peVal('name'),biome:peBiome(),description:peVal('description'),atmosphere:peVal('atmosphere'),history:peVal('history'),characters:mpSelected('pm')};
 for(const [f] of PE_LISTS)o[f]=peVal(f);if(!o.name){peErr('Give the place a name.');$('#pedit [data-pk=name]').focus();return}
 if(PL.bgData)o.bg_data=PL.bgData;else if(PL.bgClear)o.bg_clear=true;const b=$('#pesave');b.disabled=true;
 try{const r=await api('/api/places','POST',o);if(r.err)throw new Error(r.err);const i=PL.list.findIndex(p=>p.id==r.id);if(i<0)PL.list.push(r);else PL.list[i]=r;
  PL.list.sort((a,c)=>a.name.localeCompare(c.name));PL.edit=null;PL.loaded=true;placeHead();placeBg();tab('places');openPlaceSheet(r.id)}
 catch(x){peErr(x.message||'Could not save.')}b.disabled=false};
async function placeDelete(id){const p=plById(id);if(!p||!confirm(`Delete “${p.name}”? Chats that were set there simply carry on without a place.`))return;
 try{await api('/api/places/'+id,'DELETE');PL.list=PL.list.filter(x=>x.id!=id);PL.view='';PL.edit=null;closePSheet();placeHead();placeBg();placeDraw();if(!$('#pedit').hidden)tab('places');placesRender()}catch(e){}}

/* residents who wander over (one-to-one chats): called after each reply */
async function placeVisit(text){
 if(G||!chat||!cur?.id||ctl||rounding)return;const p=curPlace();if(!p||chat.cfg.mode=='call')return;
 const setting=U.placeVisitors||'normal',force=PL.force;PL.force='';if(setting=='off')return;
 try{const ic=hist.filter(m=>!m.ooc),dead=U.rp!='off'?plChars().filter(c=>isDead(c.id)).map(c=>c.id):[];
  const r=await api('/api/places/visit','POST',{cid:cur.id,place:{id:p.id,since:p.since},history:apiHist(ic),turn:hist.length,text,setting,seed:chat.id,force,dead,
   clock:U.timeaware?clock():'',story_start:chat.cfg.start||'',scene:chat.cfg.scene||'',story:storyCfg()});
  if(!r||!r.visit)return;const vc=placeChar(r.visit.id);if(!vc)return;
  await gen('reply',undefined,undefined,{char:vc,why:r.visit.why,pl:p.id})}catch(e){}}

/* "let's go to the pier": offer to move the scene when the message names another place */
function placeSuggest(text){if(!chat||!text||!PL.list.length||ctl||rounding)return;const c=curPlace();
 const mv='go|goes|going|head|heading|walk|walking|run|running|travel|drive|driving|ride|sail|move|moving|return|come|take|off|leave|leaving';
 const hit=PL.list.find(p=>(!c||c.id!=p.id)&&p.name.length>2&&new RegExp(`\\b(?:${mv})\\b[^.!?\\n]{0,40}?\\b(?:to|for|toward|towards|into|inside|back to|at)\\s+(?:the\\s+)?${p.name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}\\b`,'i').test(text));
 if(!hit)return;const e=document.createElement('div');e.className='sys pl-sug';e.innerHTML=`<span>📍 Move the scene to <b>${esc(hit.name)}</b>?</span><button data-s=y>Yes</button><button class=ghost data-s=n>No</button>`;
 e.addEventListener('click',x=>{const b=x.target.closest('button');if(!b)return;if(b.dataset.s=='y')setPlace(hit.id,{silent:true});e.remove()});$('#log').append(e);$('#log').scrollTop=1e9}

/* slash commands: /places, /go Name, /leave */
function placesSlash(t){const m=/^\/(places?|go|goto|leave)\b\s*(.*)$/i.exec(t);if(!m)return false;const cmd=m[1].toLowerCase(),arg=m[2].trim();
 if(cmd=='leave'){if(chat&&curPlace()&&!ctl&&!rounding){if(sceneOn())sceneLeave();else{setPlace('');post('*We head out.*')}}return true}
 if((cmd=='go'||cmd=='goto')&&arg){const p=plByName(arg)||PL.list.find(x=>x.name.toLowerCase().includes(arg.toLowerCase()));
  if(p&&!ctl&&!rounding){placeGo(p.id,`*We make our way to ${nounPhrase(p.name)}.*`);return true}
  if(!p){placesLoad(true);typeof bodyToast=='function'&&bodyToast('📍','No such place','There is no place called “'+arg+'”. Try /places.');return true}}
 placeOpen();return true}
