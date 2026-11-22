/* ---------- themes: every chat can have its own look ----------
   A theme is a small object ({p: preset, ac: accent, hue, mode, wall, bub, font, fs, rad, dens, img}). It is saved with the chat
   (chat.cfg.theme); chats without one use the app default (U.theme2). applyTheme() turns it into CSS variables and data attributes. */
const hex2=n=>Math.round(n).toString(16).padStart(2,'0');
function hsl2hex(h,s,l){s/=100;l/=100;const a=s*Math.min(l,1-l),f=n=>{const k=(n+h/30)%12;return l-a*Math.max(-1,Math.min(k-3,9-k,1))};return'#'+[f(0),f(8),f(4)].map(x=>hex2(x*255)).join('')}
function hex2hsl(x){const n=parseInt(x.slice(1),16),r=(n>>16&255)/255,g=(n>>8&255)/255,b=(n&255)/255,mx=Math.max(r,g,b),mn=Math.min(r,g,b),l=(mx+mn)/2,d=mx-mn;let h=0,s=0;
 if(d){s=d/(1-Math.abs(2*l-1));h=mx==r?((g-b)/d+(g<b?6:0)):mx==g?(b-r)/d+2:(r-g)/d+4;h*=60}return[h,s*100,l*100]}
const lum=x=>{const n=parseInt(x.slice(1),16),c=[n>>16&255,n>>8&255,n&255].map(v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)});return .2126*c[0]+.7152*c[1]+.0722*c[2]};
const contrast=(a,b)=>{const x=lum(a),y=lum(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
function readable(ac,bg,dark){let[h,s,l]=hex2hsl(ac),c=ac,n=0;while(contrast(c,bg)<4.3&&n++<24){l+=dark?3:-3;l=Math.max(4,Math.min(96,l));c=hsl2hex(h,s,l)}return c}
const inkOn=ac=>contrast('#15110d',ac)>=contrast('#ffffff',ac)?'#15110d':'#ffffff';
const surf=(mode,h,s)=>mode=='dark'
 ?{bg:hsl2hex(h,s,6.5),pn:hsl2hex(h,s,9.5),pn2:hsl2hex(h,s,13),pn3:hsl2hex(h,s,17.5),tx:hsl2hex(h,Math.min(s,30),94),mu:hsl2hex(h,Math.min(s,16),66)}
 :{bg:hsl2hex(h,Math.min(s,45),94.5),pn:hsl2hex(h,Math.min(s,40),98.5),pn2:hsl2hex(h,Math.min(s,40),91.5),pn3:hsl2hex(h,Math.min(s,40),85.5),tx:hsl2hex(h,Math.min(s,40),13),mu:hsl2hex(h,Math.min(s,22),42)};
const PRESETS=[
 {id:'cocoa',n:'Cocoa',mode:'dark',h:12,s:14,bg:'#141010',pn:'#1b1514',pn2:'#251d1b',pn3:'#322826',tx:'#f4ede7',mu:'#a3958d',ac:'#bfdc90',ac2:'#f2a9b9',wall:'grain',bub:'soft',font:'auto'},
 {id:'milk',n:'Milk',mode:'light',h:20,s:20,bg:'#f5f1ee',pn:'#fffdfb',pn2:'#efe8e3',pn3:'#e2d8d0',tx:'#2b201c',mu:'#76675f',ac:'#5d8a2c',ac2:'#d65a7b',wall:'none',bub:'soft',font:'auto'},
 {id:'midnight',n:'Midnight',mode:'dark',h:228,s:48,bg:'#0b1021',pn:'#111936',pn2:'#18224a',pn3:'#223060',tx:'#e9eeff',mu:'#8f9bc4',ac:'#7ea6ff',ac2:'#8ae6ff',wall:'stars',bub:'glass',font:'clean'},
 {id:'rose',n:'Rosé',mode:'light',h:345,s:60,bg:'#fbeef0',pn:'#fff9fa',pn2:'#f8e1e6',pn3:'#f0cdd6',tx:'#3a1f27',mu:'#87606e',ac:'#cf3f78',ac2:'#ff8a6b',wall:'glow',bub:'soft',font:'story'},
 {id:'moss',n:'Moss',mode:'dark',h:140,s:22,bg:'#0c130f',pn:'#121c16',pn2:'#1a271f',pn3:'#253629',tx:'#e8f1ea',mu:'#8da596',ac:'#8fd694',ac2:'#e6d690',wall:'dots',bub:'soft',font:'story'},
 {id:'arcade',n:'Arcade',mode:'dark',h:268,s:52,bg:'#110a1f',pn:'#190f2e',pn2:'#231642',pn3:'#321f5c',tx:'#f3ecff',mu:'#a594cf',ac:'#ff5fa8',ac2:'#47e1ff',wall:'grid',bub:'outline',font:'mono'},
 {id:'parchment',n:'Parchment',mode:'light',h:38,s:48,bg:'#efe3cc',pn:'#f8efdc',pn2:'#ecdcbf',pn3:'#dfcba6',tx:'#3a2a1b',mu:'#7a6245',ac:'#8d4a24',ac2:'#b0752f',wall:'grain',bub:'open',font:'story'},
 {id:'noir',n:'Noir',mode:'dark',h:0,s:0,bg:'#0b0b0c',pn:'#131314',pn2:'#1c1c1e',pn3:'#29292c',tx:'#f2f2f2',mu:'#9a9a9f',ac:'#f2f2f2',ac2:'#9a9a9f',wall:'none',bub:'outline',font:'clean'},
 {id:'ember',n:'Ember',mode:'dark',h:20,s:30,bg:'#130d0b',pn:'#1b1311',pn2:'#261b17',pn3:'#36261f',tx:'#f6ece6',mu:'#a8958b',ac:'#f0a35c',ac2:'#e5806a',wall:'glow',bub:'soft',font:'auto'},
 {id:'frost',n:'Frost',mode:'light',h:214,s:42,bg:'#edf2f8',pn:'#fbfdff',pn2:'#e4ecf6',pn3:'#d3dfee',tx:'#172234',mu:'#5b6f8a',ac:'#2f6fed',ac2:'#19b6c9',wall:'aurora',bub:'glass',font:'clean'},
  {id:'forest',n:'Forest',env:1,mode:'dark',h:150,s:28,bg:'#0c1511',pn:'#111f18',pn2:'#182a21',pn3:'#20392d',tx:'#ebf4f0',mu:'#9ab6a8',ac:'#9be28a',ac2:'#e8d58a',wall:'forest',bub:'soft',font:'story'},
  {id:'ocean',n:'Ocean',env:1,mode:'dark',h:200,s:50,bg:'#081319',pn:'#0c1c24',pn2:'#112732',pn3:'#163443',tx:'#ebf1f4',mu:'#9aadb6',ac:'#5fd0e6',ac2:'#7ea6ff',wall:'waves',bub:'glass',font:'clean'},
  {id:'rain',n:'Rainy night',env:1,mode:'dark',h:215,s:24,bg:'#0d1015',pn:'#12171e',pn2:'#192029',pn3:'#222b37',tx:'#eceff3',mu:'#9aa6b6',ac:'#8fb3d9',ac2:'#c3a6ff',wall:'rain',bub:'glass',font:'auto'},
  {id:'snow',n:'Snowfall',env:1,mode:'dark',h:212,s:34,bg:'#0b1016',pn:'#101820',pn2:'#16202c',pn3:'#1d2c3c',tx:'#ebeff4',mu:'#9aa7b6',ac:'#9cc7ff',ac2:'#d6e6ff',wall:'snow',bub:'glass',font:'clean'},
  {id:'dunes',n:'Dunes',env:1,mode:'light',h:30,s:60,bg:'#f7f1eb',pn:'#fdfbfa',pn2:'#f2e9e1',pn3:'#e9dacb',tx:'#2e2114',mu:'#836b54',ac:'#b8501c',ac2:'#d98a2b',wall:'dunes',bub:'soft',font:'story'},
  {id:'sakura',n:'Sakura',env:1,mode:'light',h:345,s:55,bg:'#f7ebee',pn:'#fdfafa',pn2:'#f2e1e5',pn3:'#e9cbd3',tx:'#2e141b',mu:'#83545f',ac:'#d6457c',ac2:'#f08aa8',wall:'petals',bub:'soft',font:'story'},
  {id:'volcano',n:'Volcano',env:1,mode:'dark',h:8,s:45,bg:'#180b09',pn:'#23100d',pn2:'#301612',pn3:'#411e19',tx:'#f4eceb',mu:'#b69e9a',ac:'#ff7a3d',ac2:'#ffc14d',wall:'embers',bub:'soft',font:'auto'},
  {id:'space',n:'Deep space',env:1,mode:'dark',h:262,s:55,bg:'#0e071a',pn:'#150b26',pn2:'#1c0f33',pn3:'#261445',tx:'#eeebf4',mu:'#a59ab6',ac:'#b69cff',ac2:'#6fe3ff',wall:'nebula',bub:'glass',font:'clean'},
  {id:'city',n:'Neon city',env:1,mode:'dark',h:285,s:45,bg:'#140918',pn:'#1e0d23',pn2:'#291230',pn3:'#371941',tx:'#f2ebf4',mu:'#af9ab6',ac:'#ff4fb0',ac2:'#3de1ff',wall:'skyline',bub:'outline',font:'clean'},
  {id:'tavern',n:'Tavern',env:1,mode:'dark',h:28,s:38,bg:'#17100a',pn:'#21180f',pn2:'#2e2015',pn3:'#3e2b1c',tx:'#f4efeb',mu:'#b6a79a',ac:'#f2b25c',ac2:'#d98a5c',wall:'candle',bub:'soft',font:'story'},
  {id:'meadow',n:'Meadow',env:1,mode:'light',h:95,s:45,bg:'#f0f7eb',pn:'#fbfdfa',pn2:'#e8f2e1',pn3:'#d8e9cb',tx:'#1f2e14',mu:'#678354',ac:'#4f8a2b',ac2:'#e2a93a',wall:'sun',bub:'soft',font:'auto'}];
const PRE=Object.fromEntries(PRESETS.map(p=>[p.id,p]));
const WALLS=[['none','None'],['glow','Glow'],['aurora','Aurora'],['dots','Dots'],['grid','Grid'],['lines','Lines'],['grain','Grain'],['stars','Stars'],['forest','Forest'],['waves','Ocean'],['rain','Rain'],['snow','Snow'],['dunes','Dunes'],['petals','Blossom'],['embers','Embers'],['nebula','Space'],['skyline','City'],['candle','Candlelight'],['sun','Sunlight'],['avatar','Portrait'],['image','Your image']];
const BUBS=[['soft','Soft'],['glass','Glass'],['outline','Outline'],['open','Open page']];
const FONTS=[['auto','Auto','Story in roleplay, clean in texting','var(--f-auto)'],['story','Story','Literata','var(--f-story)'],['clean','Clean','Figtree','var(--f-clean)'],['display','Display','Bricolage','var(--f-disp)'],['mono','Mono','JetBrains Mono','var(--f-mono)'],['sys','System','Your device font','var(--f-sys)']];
const RADS={sharp:['8px','8px','6px'],soft:['16px','20px','11px'],round:['22px','27px','15px']};
const ACCS=['#bfdc90','#f2a9b9','#7ea6ff','#ffb454','#ff6fa5','#5ad1c0','#c3a6ff','#ff7a59','#ece6df','#9bd16b'];
/* "Match the story": the look follows the place the story is in (rain, forest, tavern, space...), read from the latest messages and the scene note */
const ENVK={rain:/\b(?:rain\w*|storm\w*|thunder\w*|drizzl\w*|downpour|umbrella|puddles?|lightning)\b/gi,snow:/\b(?:snow\w*|blizzard|frost\w*|frozen|winter|icy|sleigh)\b/gi,
 ocean:/\b(?:ocean|sea|beach|shore|waves?|ship|harbou?r|boat|sail\w*|swim\w*|dock|island|tide)\b/gi,forest:/\b(?:forest|woods?|trees?|grove|jungle|campfire|moss|thicket|trail)\b/gi,
 dunes:/\b(?:desert|dunes?|sand|oasis|canyon|caravan|scorching)\b/gi,sakura:/\b(?:cherry blossoms?|sakura|petals|blossoms?|shrine)\b/gi,volcano:/\b(?:lava|volcan\w*|inferno|forge|molten|ember\w*|burning|ashes)\b/gi,
 space:/\b(?:space|starship|spaceship|galaxy|nebula|orbit|planet|asteroid|cosmos|astronaut|airlock)\b/gi,city:/\b(?:neon|cyberpunk|skyscrapers?|downtown|alley|nightclub|arcade|subway|rooftops?)\b/gi,
 tavern:/\b(?:tavern|inn|pub|candles?|fireplace|hearth|cabin|lantern|bar counter|ale|mead)\b/gi,meadow:/\b(?:meadow|fields?|sunny|garden|picnic|farm|sunshine|orchard|hillside)\b/gi};
let lastEnv=null;
function sceneEnv(){if(!chat)return lastEnv;const ms=(typeof hist!='undefined'?hist:[]).filter(m=>!m.ooc&&m.content).slice(-8),sc={};
 const add=(txt,w)=>{for(const[k,rx]of Object.entries(ENVK)){const n=(txt.match(rx)||[]).length;if(n)sc[k]=(sc[k]||0)+n*w}};
 ms.forEach((m,i)=>add(m.content,1+i*.4));add(chat.cfg?.scene||'',3);
 const best=Object.entries(sc).sort((a,b)=>b[1]-a[1])[0];if(best&&best[1]>=1.5)lastEnv=best[0];return lastEnv}
const envOf=t=>{if(!t.auto)return t;const e=sceneEnv();return e&&PRE[e]?{...t,p:e,ac:null,hue:null,mode:null,wall:PRE[e].wall,bub:t.bub||PRE[e].bub,font:t.font||PRE[e].font}:t};
const legacyT=()=>({p:U.theme=='light'?'milk':'cocoa'});
const themeOf=()=>chat?.cfg?.theme||U.theme2||legacyT();
function themeVars(t){const b=PRE[t.p]||PRE.cocoa,mode=t.mode||b.mode;let v={...b};
 if(mode!=b.mode||t.hue!=null)Object.assign(v,surf(mode,t.hue??b.h,t.hue!=null?Math.max(b.s,34):b.s));
 if(t.ac){v.ac=t.ac;v.ac2=hsl2hex((hex2hsl(t.ac)[0]+38)%360,Math.max(40,hex2hsl(t.ac)[1]),Math.max(55,Math.min(72,hex2hsl(t.ac)[2])))}
 return{...v,mode,wall:t.wall||b.wall,bub:t.bub||b.bub,font:t.font||b.font,rad:RADS[t.rad||'soft'],dens:t.dens||'cozy'}}
let themeSig='';
function applyTheme(t,force){t=envOf(t||themeOf());const sig=JSON.stringify([t,cur?.id||'',cur?.avatar?cur.avatar.length:0,U.fs]);if(sig==themeSig&&!force)return;themeSig=sig;
 const v=themeVars(t),r=document.documentElement,st=r.style,dark=v.mode=='dark';
 const vars={'--bg':v.bg,'--pn':v.pn,'--pn2':v.pn2,'--pn3':v.pn3,'--tx':v.tx,'--mu':v.mu,'--ac':v.ac,'--ac2':v.ac2,'--act':readable(v.ac,v.pn2,dark),'--ink':inkOn(v.ac),
  '--ln':dark?'rgba(255,240,230,.09)':'rgba(40,25,15,.11)','--shc':dark?'rgba(0,0,0,.55)':'rgba(70,45,30,.22)','--bad':dark?'#f28b82':'#c8372d','--ok':dark?'#8fd6a0':'#2f8f4a',
  '--r':v.rad[0],'--rb':v.rad[1],'--rs':v.rad[2],'--fs':(t.fs||U.fs)+'px','--lh':v.font=='mono'?'1.6':'1.68',
  '--f-msg':(FONTS.find(f=>f[0]==v.font)||FONTS[0])[3],'--oc':dark?'#8ab4ff':'#3b6fd4'};
 for(const[k,x]of Object.entries(vars))st.setProperty(k,x);
 r.dataset.mode=r.dataset.theme=v.mode;r.dataset.wall=v.wall=='image'&&!t.img?'none':v.wall;r.dataset.bub=v.bub;r.dataset.dens=v.dens;
 if(cur?.avatar)st.setProperty('--avimg',`url('${cur.avatar}')`);else st.removeProperty('--avimg');
 if(t.img)st.setProperty('--wallimg',`url('${t.img}')`);else st.removeProperty('--wallimg');
 let m=document.querySelector('meta[name=theme-color]');if(!m){m=document.createElement('meta');m.name='theme-color';document.head.append(m)}m.content=v.bg}
const themeSw=t=>{const v=themeVars(t||themeOf());return`<span class=tsw><i style="background:${v.bg}"></i><i style="background:${v.pn3}"></i><i style="background:${v.ac}"></i><i style="background:${v.ac2}"></i></span>`};
/* ---------- the style panel ---------- */
let stScope='chat';
const stT=()=>stScope=='chat'&&chat?(chat.cfg.theme||themeOf()):(U.theme2||legacyT());
function stSet(patch,rerender=true){const t={...stT(),...patch};for(const k of Object.keys(patch))if(patch[k]===null||patch[k]==='')delete t[k];
 if(stScope=='chat'&&chat){chat.cfg.theme=t;saveSoon()}else{U.theme2=t;persist()}
 applyTheme(null);if(rerender)stRender()}
function stRender(){const el=$('#studio');if(!el)return;const sc=el.querySelector('.stb')?.scrollTop||0,t=stT(),v=themeVars(t),inChat=!!chat&&!!cur?.id,own=stScope=='chat'&&!!chat?.cfg.theme;
 const on=(a,b)=>a==b?' on':'',pn=cur?.name||'Character';
 el.innerHTML=`<div class=sth><h3>Style</h3><button class=ib data-st=close title=Close>${ico('close')}</button></div>
 ${inChat?`<div class="seg stscope"><button data-st=scope data-v=chat class="${on(stScope,'chat').trim()}">This chat</button><button data-st=scope data-v=app class="${on(stScope,'app').trim()}">App default</button></div>`:''}
 <div class=stb>
 <div class=stprev><div class="m assistant" style="margin:0"><div class=bub><div class=nm>${esc(pn)}</div><div class=tx><em class=act>glances up from her book.</em> <span class=q>“There you are. Sit, you look cold.”</span></div></div></div><div class="m user" style="margin:0"><div class=bub><div class=tx>Thanks. It was a long walk.</div></div></div></div>
 ${stScope=='chat'&&inChat?`<div class=small style="margin:8px 2px 0">${own?'This chat has its own style, saved with it.':'This chat follows the app default. Change anything to give it its own style.'}</div>`:''}
 <h4>Theme</h4><div class=chips style="margin-bottom:8px"><button class="${t.auto?'on':''}" data-st=auto title="The look follows the place your story is in">🌦 Match the story</button></div>${t.auto?`<div class=small style="margin:-2px 2px 8px">The look follows the story: ${lastEnv?'now '+esc(PRE[lastEnv].n)+'.':'it shows your chosen theme until the story names a place (rain, forest, tavern, space, beach...).'}</div>`:''}<div class=pgrid>${PRESETS.filter(p=>!p.env).map(p=>`<button class="pset${on(p.id,t.p||'cocoa')}" data-st=preset data-v=${p.id} style="--b:${p.bg};--p:${p.pn2};--a:${p.ac};--a2:${p.ac2};--t:${p.tx}"><span class=pb></span><span class=pu></span><b>${p.n}</b><span class=pd></span></button>`).join('')}</div>
  <h4>Environments <small>places that move</small></h4><div class=pgrid>${PRESETS.filter(p=>p.env).map(p=>`<button class="pset${on(p.id,t.p||'cocoa')}" data-st=preset data-v=${p.id} style="--b:${p.bg};--p:${p.pn2};--a:${p.ac};--a2:${p.ac2};--t:${p.tx}"><span class=pb></span><span class=pu></span><b>${p.n}</b><span class=pd></span></button>`).join('')}</div>
 <h4>Accent</h4><div class=swr>${ACCS.map(c=>`<button class="sw1${on(c,t.ac)}" data-st=ac data-v=${c} style="--c:${c}" title=${c}></button>`).join('')}<input type=color data-st=acin value="${t.ac||v.ac}" title="Pick any colour"></div>
 <h4>Surface <small>tint and brightness</small></h4><div class="seg" style="margin-bottom:4px"><button data-st=mode data-v=dark class="${on(v.mode,'dark').trim()}">Dark</button><button data-st=mode data-v=light class="${on(v.mode,'light').trim()}">Light</button></div>
 <input type=range class=hue min=0 max=360 value="${t.hue??(PRE[t.p||'cocoa'].h)}" data-st=hue aria-label="Surface tint">
 <h4>Backdrop</h4><div class=chips>${WALLS.map(([k,l])=>`<button class="${on(k,v.wall).trim()}" data-st=wall data-v=${k}>${l}</button>`).join('')}</div>
 ${v.wall=='image'?`<div class=upl style="margin-top:9px"><button data-st=img>${ico('upload')}${t.img?'Replace image':'Choose an image'}</button>${t.img?`<button class=x data-st=imgrm>${ico('trash')}</button>`:''}</div>`:''}
 ${v.wall=='avatar'&&!cur?.avatar?'<div class=small style="margin-top:7px">This character has no portrait yet. Add one in the Character tab.</div>':''}
 <h4>Messages</h4><div class=chips>${BUBS.map(([k,l])=>`<button class="${on(k,v.bub).trim()}" data-st=bub data-v=${k}>${l}</button>`).join('')}</div>
 <h4>Font</h4><div class=fchips>${FONTS.map(([k,l,n,f])=>`<button class="${on(k,v.font).trim()}" data-st=font data-v=${k}><b style="font-family:${f}">${l==='Auto'?'Aa':l}</b><small>${n}</small></button>`).join('')}</div>
 <h4>Text size <small id=fsl>${t.fs||U.fs}px</small></h4><input type=range min=12 max=22 step=1 value="${t.fs||U.fs}" data-st=fs>
 <h4>Corners</h4><div class=chips>${[['sharp','Sharp'],['soft','Soft'],['round','Round']].map(([k,l])=>`<button class="${on(k,t.rad||'soft').trim()}" data-st=rad data-v=${k}>${l}</button>`).join('')}</div>
 <h4>Spacing</h4><div class=chips>${[['compact','Compact'],['cozy','Cozy'],['airy','Airy']].map(([k,l])=>`<button class="${on(k,v.dens).trim()}" data-st=dens data-v=${k}>${l}</button>`).join('')}</div>
 </div>
 <div class=stf>${stScope=='chat'&&inChat?`<button data-st=reset title="Go back to the app default">Reset this chat</button><button data-st=defnew title="Every new chat starts with this style">Use for new chats</button>`:`<button data-st=resetapp>Reset app default</button>`}</div>`;
 el.querySelector('.stb').scrollTop=sc}
function openStudio(scope){stScope=scope=='app'||!chat||!cur?.id?'app':'chat';stRender();$('#studio').classList.add('open');document.body.classList.add('stopen');$('#themebtn').classList.add('on')}
const closeStudio=()=>{$('#studio').classList.remove('open');document.body.classList.remove('stopen');$('#themebtn')?.classList.remove('on')};
$('#themebtn').onclick=()=>$('#studio').classList.contains('open')?closeStudio():openStudio('chat');
$('#studio').onclick=async e=>{const b=e.target.closest('[data-st]');if(!b||b.type=='range'||b.type=='color')return;const a=b.dataset.st,v=b.dataset.v;
 if(a=='close')closeStudio();
 else if(a=='scope'){stScope=v;stRender()}
 else if(a=='preset'){const p=PRE[v];stSet({p:v,ac:null,hue:null,mode:null,wall:p.wall,bub:p.bub,font:p.font})}
 else if(a=='auto'){const cur_=stT();stSet({auto:cur_.auto?null:true})}
  else if(a=='ac')stSet({ac:v});
 else if(a=='mode')stSet({mode:v});
 else if(['wall','bub','font','rad','dens'].includes(a))stSet({[a]:v});
 else if(a=='img'){const f=document.createElement('input');f.type='file';f.accept='image/*';f.onchange=async()=>{const x=f.files[0];if(!x)return;try{stSet({wall:'image',img:await shrinkTo(x,1100,.6)})}catch(e){alert('Could not read that image')}};f.click()}
 else if(a=='imgrm')stSet({img:null,wall:'none'});
 else if(a=='reset'){if(chat){chat.cfg.theme=null;saveSoon();applyTheme(null);stRender()}}
 else if(a=='resetapp'){U.theme2=null;persist();applyTheme(null);stRender();renderSettings()}
 else if(a=='defnew'){U.defTheme={...stT()};persist();b.textContent='Saved';setTimeout(stRender,900)}};
$('#studio').oninput=e=>{const b=e.target,a=b.dataset.st;if(!a)return;
 if(a=='hue')stSet({hue:+b.value},false);else if(a=='acin')stSet({ac:b.value},false);
 else if(a=='fs'){stSet({fs:+b.value},false);$('#fsl').textContent=b.value+'px'}};
$('#studio').onchange=e=>{if(e.target.dataset.st=='hue'||e.target.dataset.st=='acin'||e.target.dataset.st=='fs')stRender()};
async function shrinkTo(f,max=1100,q=.6){const bm=await createImageBitmap(f),k=Math.min(1,max/Math.max(bm.width,bm.height)),cv=document.createElement('canvas');cv.width=Math.round(bm.width*k);cv.height=Math.round(bm.height*k);
 cv.getContext('2d').drawImage(bm,0,0,cv.width,cv.height);return cv.toDataURL('image/jpeg',q)}
document.addEventListener('keydown',e=>{if(e.key=='Escape'&&$('#studio').classList.contains('open')&&!ctl)closeStudio()});
