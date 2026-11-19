/* ---------- message actions ---------- */
function editMsg(i){const m=hist[i],el=$(`.m[data-i="${i}"] .bub`);if(!el)return;
 el.innerHTML=`<textarea class=ed>${esc(m.content)}</textarea><div class=row><button class=go data-a=esave>Save</button><button data-a=ecancel>Cancel</button></div>`;el.querySelector('textarea').focus()}
$('#log').onclick=e=>{const b=e.target.closest('button');
 if(!b){const mm=e.target.closest('.m');if(typingNow&&mm)skipTyping();else if(mm&&touch.matches&&mm.id!='pend'){const on=mm.classList.contains('sel');$$('.m.sel').forEach(x=>x.classList.remove('sel'));if(!on)mm.classList.add('sel')}return}
 const a=b.dataset.a,mEl=b.closest('.m'),i=mEl?+mEl.dataset.i:-1,m=hist[i];if(!a)return;
 if(a=='retry'){b.closest('.sys').remove();return void(b.dataset.k=='round'?round():gen(b.dataset.k))}
 if(!m)return;
 if(a=='fxre')return void fxRe(i);if(a=='fxno')return void fxNo(i);
 if(a=='copy')navigator.clipboard?.writeText(plain(m));
 else if(a=='edit')editMsg(i);
 else if(a=='ecancel')draw();
 else if(a=='esave'){const t=mEl.querySelector('textarea').value.trim();if(t){m.content=t;if(m.sw)m.sw[m.si].content=t;if(m.oid)noteSync(m)}saveChat();draw()}
 else if(a=='okind')oocCycle(i);else if(a=='oredo')oocRedo();else if(a=='ogo')oocGo();
 else if(a=='react')b.closest('.acts').classList.toggle('open');
 else if(a=='rx'){m.react=m.react==b.dataset.e?'':b.dataset.e;saveChat();draw()}
 else if(a=='speak')speak(m.content);
 else if(a=='del'){restore(m);hist.splice(i,1);saveChat();draw()}
 else if(a=='rewind'){if(!confirm('Delete this message and everything after it?'))return;const gone=hist.splice(i);[...gone].reverse().forEach(restore);saveChat();draw();head()}
 else if(a=='swp'||a=='swn'){if(!m.sw)return;m.sw[m.si].thought=m.thought;const n=m.sw.length;m.si=(m.si+(a=='swn'?1:n-1))%n;const v=m.sw[m.si];
  Object.assign(m,{content:v.content,think:v.think,ts:v.ts||m.ts,stat:v.stat,thought:v.thought||'',pers:v.pers});saveChat();draw()}};

/* ---------- composer + toolbar ---------- */
$('#inp').oninput=e=>{lastAct=Date.now();e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,170)+'px';mnuI=0;mnuUpdate()};
$('#send').onclick=send;$('#stop').onclick=()=>{roundAbort=true;ctl&&ctl.abort()};$('#skip').onclick=skipTyping;
$('#inp').onkeydown=e=>{if(!$('#mnu').hidden){if(e.key=='ArrowDown'||e.key=='ArrowUp'){e.preventDefault();mnuI=(mnuI+(e.key=='ArrowDown'?1:mnuL.length-1))%mnuL.length;mnuUpdate();return}
  if(e.key=='Enter'||e.key=='Tab'){e.preventDefault();mnuPick(mnuI);return}if(e.key=='Escape'){hideMnu();return}}
 if(e.key=='Enter'&&!e.shiftKey){e.preventDefault();send()}
 else if(e.key=='ArrowUp'&&!$('#inp').value){const i=hist.map(m=>m.role).lastIndexOf('user');if(i>=0){e.preventDefault();editMsg(i)}}};
document.addEventListener('keydown',e=>{if(e.key=='Escape'){if(ctl){roundAbort=true;ctl.abort()}else if(typingNow)skipTyping();else if(rounding)roundAbort=true}});
$('#regen').onclick=()=>{if(ctl||rounding||hist.length<2)return;const l=hist.at(-1);
 if(l.ooc){if(l.role=='assistant'){restore(l);hist.pop();saveChat();draw()}return void gen('ooc')}   // the storyteller's reply is written again
 if(G)l.role=='assistant'?gen('swipe',l.cid):round();else gen(l.role=='assistant'?'swipe':'reply')};
$('#cont').onclick=()=>{if(ctl||rounding||!hist.length)return;const l=hist.at(-1);if(l.ooc)return void oocGo();if(l.role!='assistant')return;gen('continue',l.cid)};
$('#undo').onclick=()=>{if(ctl||rounding)return;skipTyping();restore(hist.pop());draw();saveChat()};
$('#greet').onclick=()=>{if(ctl||hist.length>1)return;resetChat(++gi);draw();saveChat()};
$('#chsel').onchange=e=>{if(!ctl)openChat(e.target.value)};
$('#newchat').onclick=()=>{if(!ctl&&cur?.id)newChat()};
$('#rename').onclick=()=>{if(!chat)return;const t=prompt('Chat name',chat.title);if(t&&t.trim()){chat.title=t.trim();saveChat()}};
$('#delchat').onclick=async()=>{if(ctl||!chat||!confirm('Delete this chat?'))return;await api(`/api/chat/${cur.id}/${chat.id}`,'DELETE');
 chats=chats.filter(c=>c.id!=chat.id);chats.length?await openChat(chats[0].id):await newChat()};
$('#expchat').onclick=()=>{if(!chat)return;dl(hist.map(m=>`${m.ooc?'(OOC) ':''}${m.role=='user'?uname():m.ooc?'Storyteller':(m.name||cur.name)}: ${plain(m)}`).join('\n\n'),`${cur.name||'chat'} - ${chat.title}.txt`,'text/plain')};
$('#mode').onchange=e=>{if(!chat)return;chat.cfg.mode=U.mode=e.target.value;persist();saveChat();draw()};
$('#len').onchange=e=>{if(!chat)return;chat.cfg.length=U.length=e.target.value;persist();saveChat()};
$('#hchip').onclick=()=>tab('mem');
const closeDrawer=()=>document.body.classList.remove('drawer'),touch=matchMedia('(hover:none)');
$('#menu').onclick=()=>document.body.classList.toggle('drawer');$('#scrim').onclick=closeDrawer;$('#hmore').onclick=e=>{e.stopPropagation();$('.chead').classList.toggle('open')};document.addEventListener('click',e=>{if(!e.target.closest('.hctl,#hmore'))$('.chead').classList.remove('open')});
let kbT=0;$('#inp').addEventListener('focus',()=>{clearTimeout(kbT);document.body.classList.add('kb');setTimeout(()=>{$('#log').scrollTop=1e9},250)});
$('#inp').addEventListener('blur',()=>{kbT=setTimeout(()=>document.body.classList.remove('kb'),200)});$('#send').onmousedown=e=>e.preventDefault();if(innerWidth<=760)$('#inp').placeholder='Message…';
if(window.visualViewport)visualViewport.addEventListener('resize',()=>{document.documentElement.style.setProperty('--vh',visualViewport.height+'px');scrollTo(0,0);const L=$('#log');if(document.body.classList.contains('kb'))L.scrollTop=L.scrollHeight});
$('#uname').oninput=e=>{U.uname=e.target.value;persist();cur&&draw()};$('#persona').oninput=e=>{U.persona=e.target.value;persist()};$('#ustats').oninput=e=>{U.ustats=e.target.value;persist()};$('#ugear').oninput=e=>{U.ugear=e.target.value;persist()};
function pills(){for(const[id,k]of[['#tthink','think'],['#tact','actions'],['#tthoughts','thoughts'],['#tvoice','tts'],['#tact2','actbar']])$(id).classList.toggle('on',!!U[k]);persist()}
$('#tthink').onclick=()=>{U.think=!U.think;pills();draw()};$('#tact').onclick=()=>{U.actions=!U.actions;pills();draw()};
$('#tthoughts').onclick=()=>{U.thoughts=!U.thoughts;pills();draw();renderSettings()};$('#tvoice').onclick=()=>{U.tts=!U.tts;if(!U.tts)speechSynthesis?.cancel?.();pills();renderSettings()};
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;let rec=null;
if(SR){$('#mic').hidden=false;$('#mic').onclick=()=>{if(rec){rec.stop();return}rec=new SR();rec.lang=navigator.language;
 rec.onresult=e=>{const i=$('#inp');i.value+=(i.value?' ':'')+e.results[0][0].transcript;i.dispatchEvent(new Event('input'))};rec.onend=()=>{rec=null;$('#mic').classList.remove('on')};$('#mic').classList.add('on');rec.start()}}
/* the character may follow up on its own if you go quiet (Settings > Initiative) */
setInterval(()=>{if(!U.nudge||G||rounding||ctl||typingNow||!chat||!cur?.id||!S.loaded||document.hidden||$('#chat').hidden||nudges>=2)return;
 const l=hist.at(-1);if(!l||l.role!='assistant'||l.ooc||hist.length<2)return;
 if(Date.now()-Math.max(l.ts||0,lastAct)>U.nudge*6e4*(nudges+1)){nudges++;gen('nudge')}},10000);
