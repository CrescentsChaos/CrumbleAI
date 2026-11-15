/* ---------- IC / OOC: step out of the story to talk to the storyteller ----------
   IC  = what your character says and does. The characters answer it.
   OOC = you, the author, talking to the storyteller. The characters never hear it. Four kinds:
     discuss  talk about the story
     correct  a character is acting wrong: becomes a standing rule for them
     setting  change the place, time or situation: stays true from now on
     direct   steer what happens next without the characters hearing it: used once, or always if you say "from now on"
   Corrections, settings and directions are kept as "author's notes" in chat.cfg.notes and injected into the prompts of the characters. */
const OK={discuss:['💬','Discuss','Talk about the story. Nothing in the scene changes.'],
 correct:['🛠','Correct','A character is acting wrong. This becomes a standing rule for them.'],
 setting:['🌍','Setting','Change the place, time or situation. It stays true from now on.'],
 direct:['🎬','Direct','Steer what happens next without the characters hearing it. Used once, unless you say "from now on".']};
const OKS=Object.keys(OK),OOCSP={id:'__ooc__',name:'Storyteller',avatar:'',tags:'',gender:''};
const icLast=()=>hist.map(m=>!m.ooc).lastIndexOf(true);

/* what does a message mean? ((text)) · //text · ooc: text · /ooc /discuss /correct /setting /direct /ic */
function oocParse(t){let m;
 if(m=/^\(\(\s*([\s\S]*?)\s*(?:\)\))?$/.exec(t))return{text:m[1]};
 if(m=/^\/\/\s*([\s\S]+)$/.exec(t))return{text:m[1]};
 if(m=/^[\[(]?\s*ooc\s*[:\]\-]\s*([\s\S]*?)\s*[\])]?$/i.exec(t))return{text:m[1]};
 return null}
const OCMD={ooc:'auto',discuss:'discuss',talk:'discuss',correct:'correct',fix:'correct',setting:'setting',scene:'setting',direct:'direct',direction:'direct'};
function oocCmd(t){const m=/^\/(\w+)\s*([\s\S]*)$/.exec(t);if(!m)return null;const c=m[1].toLowerCase(),a=m[2].trim();
 if(c=='ic')return a?{ic:a}:{mode:false};
 if(c in OCMD){const k=OCMD[c]=='auto'?null:OCMD[c];return a?{text:a,kind:k}:{mode:true,kind:k}}
 return null}
const oocKindSel=()=>oocKind=='auto'?null:oocKind;
function oocRoute(t){const c=oocCmd(t);
 if(c){if(c.ic)return{ic:c.ic};if(c.mode!=null)return{mode:c.mode,kind:c.kind};return{ooc:c.text,kind:c.kind}}
 const p=oocParse(t);if(p)return{ooc:p.text,kind:oocKindSel()};
 return oocOn?{ooc:t,kind:oocKindSel()}:null}

/* "Auto" reads what the message is for: correction > setting > direction > plain discussion */
const RX_COR=/\b(?:out of character|(?:is|are|was|were)(?:n'?t| not) (?:acting|behaving|supposed|in character|like (?:her|him|them|themselves|herself|himself))|would(?:n'?t| never| not)|should(?:n'?t| not) (?:be|act|say|do|react|talk|speak|behave|sound|have)|supposed to be|too (?:nice|polite|agreeable|forgiving|soft|aggressive|passive|clingy|formal|casual|emotional|cold|friendly|talkative|quiet|submissive|dramatic|clever|perfect)|stop (?:making|having|letting|being|acting|talking|writing)|doesn'?t (?:sound|act|talk|behave|react|do that|say that)|acting (?:wrong|off|weird|strange)|(?:her|his|their) personality|(?:in|out of) character)\b/i;
const RX_SET=/\b(?:(?:change|switch|move|shift|set|swap)\b[^.?!]{0,40}\b(?:scene|setting|location|place|scenario|story)\b|(?:let'?s|can we|could we|we should|i want to|how about we) (?:move|go|jump|skip|cut|time[- ]?skip|fast[- ]?forward|switch|head)\b|scene (?:change|is now|takes place)|(?:it(?:'s| is) now|the (?:scene|setting|story) (?:is|takes place|moves)|meanwhile|time[- ]?skip|next (?:morning|day|week|month|year)|later that|set in|set it in)\b|new (?:scene|setting|location)|setting:)/i;
const RX_DIR=/\b(?:from now on|going forward|in the next (?:reply|message|scene|few)|next,? (?:have|make|let|i want|can|let's)|i want (?:you|her|him|them|it|the|there)|(?:have|let|make|get) (?:her|him|them|someone|something|a|an|the|it) |introduce|add (?:a|an|some)|bring in|include|slow(?:er)? (?:down|pacing)|speed (?:up|things)|pacing|don'?t (?:rush|resolve|end|skip)|(?:more|less) (?:description|detail|dialogue|action|narration|tension|conflict|humou?r|banter)|shorter|longer|focus on)\b/i;
const oocNames=()=>(G?gmem():[cur]).filter(Boolean).flatMap(c=>[c.name,first(c)]).filter(n=>n&&n.length>1).map(n=>n.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
function oocDetect(t){const q=/\?\s*$/.test(t),ask=/^(?:can|could|would|will|please)\b/i.test(t),who=`(?:her|him|them|${oocNames().join('|')||'\\b\\B'})`.replace('|)',')');
 if(RX_COR.test(t)||new RegExp(`\\b(?:(?:keep|make) ${who}|${who} (?:should |needs? to |has to )?be) (?:a bit |much |way |even |a little )?(?:more|less) \\w+`,'i').test(t))return'correct';
 if(RX_SET.test(t))return'setting';if(RX_DIR.test(t)&&(!q||ask))return'direct';return'discuss'}

/* author's notes */
const LIFE=/\b(?:from now on|going forward|always|every (?:reply|message|scene|time)|for the rest of|permanently|whenever|keep (?:doing it|it up)|stay that way)\b/i;
function oocWho(t){if(!G)return[];return gmem().filter(c=>[c.name,first(c)].filter(n=>n&&n.length>1).some(n=>new RegExp('(?:^|[^\\w])'+n.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?!\\w)','i').test(t))).map(c=>c.id)}
const mkNote=(kind,text,oid)=>({id:rid(),oid,ts:Date.now(),kind,text:text.trim(),who:oocWho(text),always:kind!='direct'||LIFE.test(text)});
const notesOf=()=>chat.cfg.notes||(chat.cfg.notes=[]);
const dropNote=oid=>{if(oid&&chat?.cfg?.notes)chat.cfg.notes=chat.cfg.notes.filter(n=>n.oid!=oid)};
function noteSync(m){const n=notesOf().find(x=>x.oid==m.oid);if(n){n.text=m.content.trim();n.who=oocWho(n.text);if(n.kind=='direct')n.always=LIFE.test(n.text)}}
const noteAnchor=(base,n)=>{const p=base.findIndex(m=>m.oid==n.oid);if(p>=0)return p;const q=base.findIndex(m=>(m.ts||0)>(n.ts||0));return q<0?base.length-1:q-1};
/* the notes in force for a reply written after `base` (the whole chat so far, out-of-character messages included).
   Corrections and settings always apply. A direction is used by the first round of in-character replies after it
   (the replies to your next in-character message, or the ones made by "Continue the scene"), so swiping, regenerating
   and every speaker in a group round still carry it, and it is spent once a later round begins. */
function oocActive(base,kind){return notesOf().filter(n=>{
 if(n.always)return true;if(kind=='nudge')return false;
 const p=noteAnchor(base,n),trig=j=>{for(let k=j-1;k>p;k--)if(base[k].role=='user'&&!base[k].ooc)return k;return-1},
  j0=base.findIndex((m,k)=>k>p&&m.role=='assistant'&&!m.ooc);
 return j0<0||trig(j0)==trig(base.length)})}

/* sending */
function oocSet(on,kind){oocOn=!!on;if(kind)oocKind=kind;oocUI();rpbarDraw();$('#inp').focus()}
async function postOoc(text,kind){const t=(text||'').trim();if(!t||!chat)return;
 const k=OK[kind]?kind:oocDetect(t),m={role:'user',content:t,ts:Date.now(),ooc:k,oid:rid()};
 if(k!='discuss')notesOf().push(mkNote(k,t,m.oid));
 hist.push(m);beep(520,.05);nudges=0;lastAct=Date.now();draw();saveChat();
 if(k=='discuss'||U.oocReply!='discuss')await gen('ooc')}
function oocGo(){if(ctl||rounding)return;const li=icLast(),openU=li>=0&&hist[li].role=='user';G?(openU?round():round({keep:true})):gen(openU?'reply':'resume')}
function oocRedo(){if(ctl||rounding)return;let u=-1;hist.forEach((m,k)=>{if(m.role=='user'&&!m.ooc)u=k});if(u<0)return;
 for(let k=hist.length-1;k>u;k--){const m=hist[k];if(m.role=='assistant'&&!m.ooc){restore(m);hist.splice(k,1)}}
 saveChat();draw();G?round():gen('reply')}
function oocCycle(i){const m=hist[i];if(!m||ctl||rounding)return;const k=OKS[(OKS.indexOf(m.ooc)+1)%OKS.length];
 dropNote(m.oid);m.ooc=k;if(k!='discuss')notesOf().push(mkNote(k,m.content,m.oid));saveChat();draw()}

/* composer */
function oocUI(){const c=$('.comp');if(!c)return;c.classList.toggle('ooc',oocOn);const b=$('#oocbtn');b.textContent=oocOn?'OOC':'IC';b.classList.toggle('on',oocOn);
 b.title=oocOn?'Out of character: talking to the storyteller. Click (or Alt+O) to go back in character.':'In character. Click (or Alt+O) to talk to the storyteller out of character. Or start one message with ((';
 const k=$('#oockinds');k.hidden=!oocOn;
 if(oocOn)k.innerHTML='<span class=lb>Out of character</span>'+[['auto','✨','Auto','The storyteller reads what you mean.']].concat(OKS.map(id=>[id,...OK[id]])).map(([id,ic,l,h])=>
  `<button class="pill ${oocKind==id?'arm':''}" data-ok=${id} title="${at(h)}">${ic} ${l}</button>`).join('')+`<span class=small>${esc(oocKind=='auto'?'Auto: the storyteller reads what you mean.':OK[oocKind][2])}</span>`;
 const n=chat?.cfg?.notes?.length||0,t=$('#tnotes');t.hidden=!n;t.textContent='📝 '+n;armUI()}
$('#oocbtn').onclick=()=>oocSet(!oocOn);
$('#oockinds').onclick=e=>{const b=e.target.closest('[data-ok]');if(b){oocKind=b.dataset.ok;oocUI();$('#inp').focus()}};
$('#tnotes').onclick=()=>tab('mem');
document.addEventListener('keydown',e=>{if(e.altKey&&e.code=='KeyO'&&!e.ctrlKey&&!e.metaKey){e.preventDefault();oocSet(!oocOn)}});

/* messages */
const oocFmt=t=>esc(t).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*\n]+)\*/g,'<em>$1</em>');
const oocUsed=i=>hist.slice(i+1).some(x=>x.role=='assistant'&&!x.ooc);
function oocEffect(m,i){const k=m.ooc;if(k=='discuss'||!OK[k])return'';const n=notesOf().find(x=>x.oid==m.oid);
 if(!n)return'<div class=oeff>Note removed</div>';
 const who=n.who.length?' for '+n.who.map(id=>memberById(id)?.name||'?').join(', '):'';
 return`<div class=oeff>${k=='correct'?'🛠 Rule added'+esc(who):k=='setting'?'🌍 Scene updated from here':n.always?'🎬 Standing direction':oocUsed(i)?'🎬 Direction used':'🎬 Applies to the next reply'}</div>`}
function oocChips(m,k){if(k=='discuss'||ctl||rounding)return'';
 let u=-1;hist.forEach((x,j)=>{if(x.role=='user'&&!x.ooc)u=j});const redo=u>=0&&hist.some((x,j)=>j>u&&x.role=='assistant'&&!x.ooc);
 return`<div class=ochips>${k=='correct'&&redo?'<button class=pill data-a=oredo title="Throw away the last in-character reply and write it again with this rule">↻ Redo the last reply</button>':''}<button class=pill data-a=ogo title="Go back in character: the story carries on with your note applied">▶ Continue the scene</button></div>`}
function oocHTML(m,i){const u=m.role=='user',k=OK[m.ooc]?m.ooc:'discuss',last=i==hist.length-1,
 acts=`<div class=acts><button data-a=copy title=Copy>⧉</button><button data-a=edit title=Edit>✎</button><button data-a=rewind title="Delete this and everything after">⏪</button><button data-a=del title="Delete message">🗑</button></div>`,
 th=!u&&U.think&&m.think?`<details class=think><summary>Thought process</summary><div>${esc(m.think)}</div></details>`:'',
 tag=u?`<button class=otag data-a=okind title="${at(OK[k][2])} Click to change what this message does.">${OK[k][0]} ${OK[k][1]}</button>`:'';
 return`<div class="m ${m.role} ooc" data-i=${i}>${u?'':'<div class="av ooc-av" title="Storyteller (out of character)">🎬</div>'}<div class=bub><div class=nm>${esc(u?uname():'Storyteller')}<span class=ooctag>OOC</span>${U.stamps&&m.ts?`<span class=ts>${hm(m.ts)}</span>`:''}</div>${acts}${th}<div class=tx>${oocFmt(m.content)}</div>${tag}${u?oocEffect(m,i):''}${last?oocChips(m,k):''}</div></div>`}

/* memory tab: the notes in force */
function notesMem(){const ns=chat?.cfg?.notes||[];
 const row=n=>`<div class=onote data-nid=${n.id}><span class=oi title="${at(OK[n.kind][1])}">${OK[n.kind][0]}</span><input data-on=text value="${at(n.text)}">${n.who.length?`<span class=small>${esc(n.who.map(id=>memberById(id)?.name||'?').join(', '))}</span>`:''}`+
  `${n.kind=='direct'?`<button data-on=life title="${n.always?'Standing: used in every reply':'Used once, in the next reply'}">${n.always?'♾':'1×'}</button>`:''}<button class=x data-on=del title="Remove this note">✕</button></div>`;
 return`<details open class=onotes><summary>📝 Author's notes (out of character)</summary><p class=small>Set by your OOC messages. The characters never hear them; they change how everyone behaves and what happens. Remove one and it stops applying.</p>`+
  (ns.map(row).join('')||'<p class=small>None yet. Switch the composer to OOC, or start a message with (( to add one.</p>')+(ns.length>12?'<p class=small>Only the newest 12 are used.</p>':'')+
  `<div class=row><select id=nnk>${['correct','setting','direct'].map(k=>`<option value=${k}>${OK[k][0]} ${OK[k][1]}</option>`).join('')}</select><input id=nntx placeholder="Add a note…"><button data-on=add>Add</button></div></details>`}
const oocNote=t=>{const r=t.closest('.onote');return r&&notesOf().find(n=>n.id==r.dataset.nid)};
$('#memf').addEventListener('input',e=>{const t=e.target;if(t.dataset.on!='text'||!chat)return;const n=oocNote(t);if(n){n.text=t.value;n.who=oocWho(t.value);saveSoon()}});
$('#memf').addEventListener('click',e=>{const b=e.target.closest('button'),k=b?.dataset.on;if(!k||!chat)return;const n=oocNote(b);
 if(k=='del'&&n)chat.cfg.notes=chat.cfg.notes.filter(x=>x!==n);
 else if(k=='life'&&n)n.always=!n.always;
 else if(k=='add'){const v=$('#nntx').value.trim();if(!v)return;notesOf().push(mkNote($('#nnk').value,v,rid()))}
 else return;saveSoon();draw();renderMem()});
