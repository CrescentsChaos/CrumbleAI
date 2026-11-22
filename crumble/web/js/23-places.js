/* ---------- places: location cards you can explore (js/23-places.js) ----------
   A place card has a name, biome, description, atmosphere, a background picture, objects, characters, activities, exits, events, history and secrets.
   The chat stands in one place at a time (chat.cfg.places is a small log, so rewinding walks you back). The server reads the card itself on every
   reply; guests only ever get the public view of a card. In a one-to-one chat, residents of the place can wander over and talk (js/06-generate.js
   asks /api/places/visit after each reply). */
const PL={list:[],loaded:false,open:false,tab:'here',view:'',force:'',biomes:[],edit:null,chip:null,bgSet:''};
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
 try{const r=await api('/api/places');if(r&&r.places){PL.list=r.places;PL.biomes=r.biomes||[];PL.loaded=true;placeHead();placeBg();if(PL.open)placeDraw()}}catch(e){}}

/* where the chat stands: the last entry of the log that is still part of the story (rewinding removes the message it came with) */
function curPlace(){if(!chat)return null;let e=null;for(const x of chat.cfg.places||[])if(x.since<hist.length||x.since===0)e=x;
 return e&&e.id?{id:e.id,since:e.since,card:plById(e.id)||null}:null}
const placeSpec=()=>{const p=curPlace();return p?{id:p.id,since:p.since}:undefined};
function setPlace(id,o={}){if(!chat)return;const lg=(chat.cfg.places||[]).filter(x=>x.since<hist.length||x.since===0);
 lg.push({id:id||'',since:o.silent?Math.max(0,hist.length-1):hist.length});chat.cfg.places=lg;saveChat();head();worldRefresh(true)}

/* header chip and background picture */
function placeHead(){if(!PL.chip){const hw=$('#hworld');if(!hw)return;const c=document.createElement('button');c.id='hplace';c.type='button';c.className=hw.className;
  c.addEventListener('click',()=>PL.open?placeClose():placeOpen());hw.after(c);PL.chip=c}
 const e=PL.chip,p=chat&&cur?curPlace():null;e.hidden=!(chat&&cur);if(e.hidden){if(PL.open)placeClose();return}
 e.innerHTML=`<span>📍</span><b>${esc(p?(p.card?p.card.name:'…'):'Places')}</b>`;e.title='Places: where this chat takes place. Click to explore, change place or manage cards';
 if(!PL.loaded)placesLoad();if(PL.open)placeDraw()}
function placeBg(){const L=$('#log');if(!L)return;const p=curPlace(),c=p&&p.card;
 if(c&&c.bg_url&&U.placeBg!==false){const v=`linear-gradient(color-mix(in srgb,var(--pn) 60%,transparent),color-mix(in srgb,var(--pn) 80%,transparent)),url("${c.bg_url}")`;
  L.style.backgroundImage=v;L.style.backgroundSize='cover';L.style.backgroundPosition='center';PL.bgSet=L.style.backgroundImage}
 else if(PL.bgSet){if(L.style.backgroundImage==PL.bgSet){L.style.backgroundImage='';L.style.backgroundSize='';L.style.backgroundPosition=''}PL.bgSet=''}}

/* the panel */
function placeOpen(tab){PL.open=true;PL.tab=tab||(curPlace()?'here':'all');PL.view='';placesLoad(true);placeDraw()}
function placeClose(){PL.open=false;const e=$('#placepop');if(e)e.hidden=true}
function plPop(){let e=$('#placepop');if(!e){e=document.createElement('div');e.id='placepop';e.hidden=true;document.body.append(e);
  e.addEventListener('click',plClick)}return e}
const plList=(a,cls='')=>a&&a.length?`<ul class="pl-list ${cls}">${a.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'';
function plDetail(p){const cur_=curPlace(),here=cur_&&cur_.id==p.id,adm=!plGuest(),can=here&&chat,
 chip=(act,v,txt,extra='')=>can?`<button class="pl-chip" data-pa=${act} data-v="${at(v)}"${extra}>${esc(txt)}</button>`:`<span class="pl-chip off">${esc(txt)}</span>`,
 ppl=(p.characters||[]).map(placeChar).filter(Boolean),
 sec=(t,h)=>h?`<div class=pl-sec><div class=lb>${t}</div>${h}</div>`:'';
 return`<div class=pl-hero style="background-image:${p.bg_url?`linear-gradient(transparent 20%,rgba(0,0,0,.72)),url('${at(p.bg_url)}')`:`linear-gradient(transparent 20%,rgba(0,0,0,.55)),${grad(p.name)}`}"><div class=pl-ht><b>${esc(p.name)}</b>${p.biome?`<span class=pl-biome>${esc(p.biome)}</span>`:''}${here?'<span class=pl-here>You are here</span>':''}</div></div>
 ${p.description?`<p class=pl-desc>${esc(p.description)}</p>`:''}${p.atmosphere?`<p class=pl-atm>${esc(p.atmosphere)}</p>`:''}
 ${sec('Objects',(p.objects||[]).length?`<div class=pl-chips>${p.objects.map(x=>chip('obj',x,x)).join('')}</div>`:'')}
 ${sec('Activities',(p.activities||[]).length?`<div class=pl-chips>${p.activities.map(x=>chip('act',x,x)).join('')}</div>`:'')}
 ${sec('People here',ppl.length?`<div class=pl-chips>${ppl.map(c=>{const mine=!G&&cur&&c.id==cur.id;return can&&!mine&&!G?`<button class="pl-chip pl-who" data-pa=call data-v="${at(c.id)}"><span class=av style="${avs(c)}">${avin(c)}</span>${esc(c.name)}</button>`:`<span class="pl-chip pl-who off"><span class=av style="${avs(c)}">${avin(c)}</span>${esc(c.name)}${mine?' (with you)':''}</span>`}).join('')}</div>${can&&!G&&!ppl.every(c=>cur&&c.id==cur.id)?'<div class=small>Tap someone to call them over, or just speak to them by name.</div>':''}`:'')}
 ${sec('Exits',(p.exits||[]).length?`<div class=pl-chips>${p.exits.map(x=>{const t=exitPlace(x);return can?`<button class="pl-chip pl-exit" data-pa=exit data-v="${at(x)}" title="${at(t?'Go to '+t.name:'Just a direction')}">➜ ${esc(x)}</button>`:`<span class="pl-chip off">➜ ${esc(x)}</span>`}).join('')}</div>`:'')}
 ${adm&&(p.history||(p.events||[]).length||(p.secrets||[]).length)?`<details class=pl-auth><summary>Author notes (guests cannot see these)</summary>${p.history?sec('History',`<p class=pl-desc>${esc(p.history)}</p>`):''}${sec('Events',plList(p.events))}${sec('Secrets',plList(p.secrets))}</details>`:''}
 <div class=pl-foot>${chat?(here?'<button class=ghost data-pa=leave>Leave this place</button>':`<button data-pa=go data-v="${at(p.id)}">Go here</button>`):''}${adm?`<button class=ghost data-pa=edit data-v="${at(p.id)}">Edit</button><button class=ghost data-pa=del data-v="${at(p.id)}">Delete</button>`:''}</div>`}
function plGallery(){const adm=!plGuest(),c=curPlace();
 return`<div class=pl-grid>${PL.list.map(p=>`<button class="pl-card${c&&c.id==p.id?' on':''}" data-pa=view data-v="${at(p.id)}" style="background-image:${p.bg_url?`linear-gradient(transparent 30%,rgba(0,0,0,.75)),url('${at(p.bg_url)}')`:`linear-gradient(transparent 30%,rgba(0,0,0,.5)),${grad(p.name)}`}"><b>${esc(p.name)}</b><span>${esc(p.biome||'')}${(p.characters||[]).length?` · ${p.characters.length} ${p.characters.length==1?'person':'people'}`:''}</span></button>`).join('')}
 ${adm?'<button class="pl-card pl-new" data-pa=new>＋<span>New place</span></button>':''}</div>${PL.list.length||adm?'':'<div class=small>The host has not made any places yet.</div>'}`}
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
 if(k=='new')return placeEditor(null);
 if(k=='edit')return placeEditor(plById(v));
 if(k=='del')return placeDelete(v);
 if(busyNow)return;
 if(k=='go'){const p=plById(v);if(p)placeGo(p.id,`*We make our way to ${nounPhrase(p.name)}.*`)}
 else if(k=='leave'){placeClose();setPlace('');post('*We head out.*')}
 else if(k=='obj')placeSay(`*I take a closer look at ${nounPhrase(v)}.*`);
 else if(k=='act')placeSay(`*I suggest we ${lowerFirst(v)}.*`);
 else if(k=='call'){const c=placeChar(v);if(c){PL.force=c.id;placeSay(`*I call ${first(c)} over.*`)}}
 else if(k=='exit'){const t=exitPlace(v);if(t)placeGo(t.id,`*We head for ${nounPhrase(exitName(v))}.*`);else placeSay(`*We head for ${nounPhrase(exitName(v))}.*`)}}
function placeSay(t){placeClose();post(t)}
function placeGo(id,line){if(!chat||ctl||rounding)return;placeClose();setPlace(id);post(line)}
document.addEventListener('click',e=>{if(PL.open&&!e.target.closest('#placepop,#hplace,#plmodal'))placeClose()});

/* the editor */
const PE_LISTS=[['objects','Objects','the brass telescope\nan old jukebox','Things that can be seen, touched or used. One per line, written like “the brass telescope”.'],
 ['activities','Activities','watch the boats\nplay a record','What people do here. One per line, as short verb phrases.'],
 ['exits','Exits','The Pier\nLighthouse Road','Where you can go from here. Use the name of another place card to make it a one-click trip.'],
 ['events','Events','A fog horn sounds far out.\nThe lights flicker.','Things that can happen here now and then (guests never see these).'],
 ['secrets','Secrets','There is a trapdoor under the jukebox.','Hidden truths. They only come out when you search, investigate or ask the right person (guests never see these).']];
function placeEditor(p){PL.edit=p?{...p}:{id:'',name:'',biome:'',description:'',atmosphere:'',history:'',objects:[],activities:[],exits:[],events:[],secrets:[],characters:[],bg:'',bg_url:''};PL.bgData='';PL.bgClear=false;
 let m=$('#plmodal');if(!m){m=document.createElement('div');m.id='plmodal';document.body.append(m);m.addEventListener('click',peClick);m.addEventListener('change',peChange)}
 const d=PL.edit,chars=plChars();
 m.hidden=false;m.innerHTML=`<div class=pe><div class=wh><b>${d.id?'Edit place':'New place'}</b><button class=ghost data-pe=x>✕</button></div>
 <div class=pe-draft><input id=pe-concept placeholder="Describe it in a sentence and let the model draft the card…"><button class=ghost data-pe=draft>✨ Draft</button></div>
 <div class=pe-row><label>Name<input id=pe-name value="${at(d.name)}" maxlength=80></label><label>Biome<input id=pe-biome list=pe-biomes value="${at(d.biome)}" maxlength=60><datalist id=pe-biomes>${PL.biomes.map(x=>`<option>${esc(x)}</option>`).join('')}</datalist></label></div>
 <label>Description<textarea id=pe-description rows=3>${esc(d.description)}</textarea></label>
 <label>Atmosphere<textarea id=pe-atmosphere rows=2 placeholder="Sounds, smells, light, temperature, mood">${esc(d.atmosphere)}</textarea></label>
 <div class=pe-bg><div id=pe-prev class=pe-prev style="${d.bg_url?`background-image:url('${at(d.bg_url)}')`:''}">${d.bg_url?'':'No picture'}</div><div><label class=pe-file>Chat background<input type=file id=pe-file accept="image/*"></label><button class=ghost data-pe=nobg>Remove picture</button><div class=small>Shows behind the messages while you are here. Large pictures are shrunk automatically.</div></div></div>
 <div class=pe-sec><div class=lb>Characters here</div><div class=pe-chars>${chars.length?chars.map(c=>`<label class=pe-ch><input type=checkbox data-pc="${at(c.id)}" ${(d.characters||[]).includes(c.id)?'checked':''}><span class=av style="${avs(c)}">${avin(c)}</span>${esc(c.name)}</label>`).join(''):'<span class=small>Make some characters first.</span>'}</div><div class=small>They belong here: they can be in the background, and in a one-to-one chat they may wander over and talk to you.</div></div>
 ${PE_LISTS.map(([k,t,ph,h])=>`<label>${t}<textarea id=pe-${k} rows=3 placeholder="${at(ph)}">${esc((d[k]||[]).join('\n'))}</textarea></label><div class="small pe-h">${h}</div>`).join('')}
 <label>History<textarea id=pe-history rows=3 placeholder="What happened here before the story began">${esc(d.history)}</textarea></label>
 <div class=pe-err id=pe-err></div><div class=pl-foot><button data-pe=save>Save place</button><button class=ghost data-pe=x>Cancel</button></div></div>`}
function plImg(file){return new Promise((ok,no)=>{const r=new FileReader();r.onerror=()=>no(new Error('Could not read that file.'));
 r.onload=()=>{const im=new Image();im.onerror=()=>no(new Error('That is not a picture.'));
  im.onload=()=>{const s=Math.min(1,1600/Math.max(im.width,im.height)),c=document.createElement('canvas');c.width=Math.round(im.width*s);c.height=Math.round(im.height*s);c.getContext('2d').drawImage(im,0,0,c.width,c.height);ok(c.toDataURL('image/jpeg',.82))};
  im.src=r.result};r.readAsDataURL(file)})}
async function peChange(e){if(e.target.id!='pe-file'||!e.target.files[0])return;try{PL.bgData=await plImg(e.target.files[0]);PL.bgClear=false;const p=$('#pe-prev');p.style.backgroundImage=`url('${PL.bgData}')`;p.textContent=''}catch(x){$('#pe-err').textContent=x.message}}
const peVal=k=>($('#pe-'+k)?.value||'').trim();
async function peClick(e){const b=e.target.closest('button[data-pe]');if(!b)return;const k=b.dataset.pe;
 if(k=='x'){$('#plmodal').hidden=true;return}
 if(k=='nobg'){PL.bgData='';PL.bgClear=true;const p=$('#pe-prev');p.style.backgroundImage='';p.textContent='No picture';return}
 if(k=='draft'){const c=peVal('concept');if(!c)return;b.disabled=true;b.textContent='Drafting…';$('#pe-err').textContent='';
  try{const r=await api('/api/gen_place','POST',{concept:c});if(r.err)throw new Error(r.err);
   for(const f of ['name','biome','description','atmosphere','history'])if(r[f]&&$('#pe-'+f))$('#pe-'+f).value=r[f];
   for(const [f] of PE_LISTS)if(r[f]&&$('#pe-'+f))$('#pe-'+f).value=r[f].join('\n')}catch(x){$('#pe-err').textContent=x.message||'The model could not draft that.'}
  b.disabled=false;b.textContent='✨ Draft';return}
 if(k=='save'){const o={id:PL.edit.id||undefined,name:peVal('name'),biome:peVal('biome'),description:peVal('description'),atmosphere:peVal('atmosphere'),history:peVal('history'),
   characters:[...document.querySelectorAll('#plmodal [data-pc]:checked')].map(x=>x.dataset.pc)};
  for(const [f] of PE_LISTS)o[f]=peVal(f);if(!o.name){$('#pe-err').textContent='Give the place a name.';return}
  if(PL.bgData)o.bg_data=PL.bgData;else if(PL.bgClear)o.bg_clear=true;b.disabled=true;
  try{const r=await api('/api/places','POST',o);if(r.err)throw new Error(r.err);const i=PL.list.findIndex(p=>p.id==r.id);if(i<0)PL.list.push(r);else PL.list[i]=r;
   PL.list.sort((a,c)=>a.name.localeCompare(c.name));$('#plmodal').hidden=true;PL.view=r.id;PL.tab='all';placeHead();placeBg();if(PL.open)placeDraw()}
  catch(x){$('#pe-err').textContent=x.message||'Could not save.';b.disabled=false}}}
async function placeDelete(id){const p=plById(id);if(!p||!confirm(`Delete “${p.name}”? Chats that were set there simply carry on without a place.`))return;
 try{await api('/api/places/'+id,'DELETE');PL.list=PL.list.filter(x=>x.id!=id);PL.view='';placeHead();placeBg();placeDraw()}catch(e){}}

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
 if(cmd=='leave'){if(chat&&curPlace()&&!ctl&&!rounding){setPlace('');post('*We head out.*')}return true}
 if((cmd=='go'||cmd=='goto')&&arg){const p=plByName(arg)||PL.list.find(x=>x.name.toLowerCase().includes(arg.toLowerCase()));
  if(p&&!ctl&&!rounding){placeGo(p.id,`*We make our way to ${nounPhrase(p.name)}.*`);return true}
  if(!p){placesLoad(true);typeof bodyToast=='function'&&bodyToast('📍','No such place','There is no place called “'+arg+'”. Try /places.');return true}}
 placeOpen();return true}
