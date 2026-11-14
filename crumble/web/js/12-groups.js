/* ---------- group chats + roleplay engine ---------- */
const NARR={id:'__narrator__',name:'Narrator',avatar:'',tags:'',gender:''};
const memberById=id=>id=='__narrator__'?NARR:S.chars.find(c=>c.id==id);
const mst=id=>{const m=chat.state.members||(chat.state.members={});return m[id]||(m[id]=newState())};
const gmem=()=>G?G.members.map(memberById).filter(Boolean):[];
const first=c=>c.name.split(/\s+/)[0];
const uniqueTag=c=>gmem().filter(x=>first(x).toLowerCase()==first(c).toLowerCase()).length>1?c.name:first(c);
const rpCfg=()=>({mode:U.rp,diff:U.diff,romance:U.romance,tone:U.tone});
const ROMST=[[10,'No spark'],[25,'Curious'],[45,'Flirty'],[65,'Smitten'],[85,'In love'],[101,'Devoted']],romStage=v=>ROMST.find(s=>v<s[0])[1];
const TIERC={crit:'#58d68d',win:'#7fd48a',part:'#f0b26b',fail:'#ef7676',bust:'#e0484f'};
const addAff=(id,d)=>{const s=G?mst(id):chat.state;s.affection=Math.max(0,Math.min(100,(s.affection??50)+d))};

function buildMen(){if(!G){MEN=null;return}const ns=[];gmem().forEach(c=>{ns.push(c.name);if(first(c)!=c.name)ns.push(first(c))});
 ns.sort((a,b)=>b.length-a.length);MEN=new RegExp('@(?:everyone|everybody|all|'+ns.map(n=>n.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')+')(?![\\w])','gi')}
function grpIntro(){return(G.scenario?`<div class=sep>📍 ${esc(G.scenario.slice(0,240))}</div>`:'')+(hist.length?'':'<div class=sep>Say something, or press “Let them talk” to open the scene. Type @ to speak to one person.</div>')}
async function pickGroup(id){const g=(S.groups||[]).find(x=>x.id==id);if(!g)return;G=g;cur={id:g.id,name:g.name,avatar:'',gender:'',first_mes:'',alts:'',tags:'',group:1};buildMen();renderChars();
 chats=(await api('/api/chats/'+id)).chats||[];chats.length?await openChat(chats[0].id):await newChat()}
function renderGroups(){const q=($('#csearch').value||'').toLowerCase();
 $('#glist').innerHTML=(S.groups||[]).filter(g=>!q||g.name.toLowerCase().includes(q)).map(g=>`<div class="ch ${G&&G.id==g.id?'on':''}" data-gid=${g.id}><div class="av sm" style="background:${grad(g.name)}">👥</div><span>${esc(g.name)}<small>${esc(g.members.map(i=>memberById(i)?.name||'?').slice(0,4).join(', '))}</small></span></div>`).join('')||'<div class=small style="margin:4px 6px">No groups yet.</div>'}
$('#glist').onclick=e=>{const d=e.target.closest('.ch');if(d){pickGroup(d.dataset.gid);closeDrawer();tab('chat')}};
let GE={};
function openGroupEditor(g){GE=g?{...g}:{id:''};const e=g||{name:'',members:[],pace:'natural',narrator:false,scenario:''};
 $('#gname').value=e.name;$('#gpace').value=e.pace||'natural';$('#gnar').checked=!!e.narrator;$('#gscen').value=e.scenario||'';
 $('#gmem').innerHTML=S.chars.map(c=>`<label class=chk><input type=checkbox data-gm=${c.id} ${e.members.includes(c.id)?'checked':''}><span>${esc(c.name||'(unnamed)')}</span></label>`).join('');
 $('#gdel').hidden=!GE.id;tab('gedit')}
$('#newg').onclick=()=>openGroupEditor(null);
$('#gsave').onclick=async()=>{const members=$$('[data-gm]').filter(x=>x.checked).map(x=>x.dataset.gm);if(members.length<2){alert('Pick at least two characters.');return}
 const g=await api('/api/groups','POST',{id:GE.id,name:$('#gname').value.trim()||'Group chat',members,pace:$('#gpace').value,narrator:$('#gnar').checked,scenario:$('#gscen').value});
 if(g.err){alert(g.err);return}S.groups=S.groups||[];const i=S.groups.findIndex(x=>x.id==g.id);i<0?S.groups.push(g):S.groups[i]=g;await pickGroup(g.id);tab('chat')};
$('#gdel').onclick=async()=>{if(!GE.id||!confirm('Delete this group and all its chats?'))return;await api('/api/groups/'+GE.id,'DELETE');S.groups=S.groups.filter(x=>x.id!=GE.id);G=null;MEN=null;cur=null;chat=null;hist=[];renderChars();S.chars[0]?await pick(S.chars[0].id):openNew();tab('chat')};
$('#gstrip').onclick=e=>{if(e.target.id=='gedit2'){openGroupEditor(G);return}const a=e.target.closest('[data-mid]');if(!a)return;const c=memberById(a.dataset.mid),i=$('#inp');i.value+=(i.value&&!/\s$/.test(i.value)?' ':'')+'@'+uniqueTag(c)+' ';i.focus()};

/* @mention menu */
let mnuI=0,mnuL=[];
const hideMnu=()=>{$('#mnu').hidden=true;mnuL=[]};
function mnuUpdate(){if(!G)return hideMnu();const i=$('#inp'),pre=i.value.slice(0,i.selectionStart),m=/(?:^|\s)@([\w'-]*)$/.exec(pre);if(!m)return hideMnu();
 const q=m[1].toLowerCase(),opts=[...gmem(),...(G.narrator?[NARR]:[])].filter(c=>c.name.toLowerCase().split(/\s+/).some(w=>w.startsWith(q))||c.name.toLowerCase().startsWith(q)).map(c=>({n:c.name,c}));
 if('everyone'.startsWith(q))opts.push({n:'everyone'});if(!opts.length)return hideMnu();
 mnuL=opts;mnuI=Math.min(mnuI,opts.length-1);const r=$('.comp').getBoundingClientRect(),e=$('#mnu');
 e.innerHTML=opts.map((o,k)=>`<div class="mi ${k==mnuI?'on':''}" data-k=${k}>${o.c?avatar(o.c,'sm'):'<div class="av sm" style="background:var(--pn3)">@</div>'}<span>${esc(o.n)}</span></div>`).join('');
 e.style.left=r.left+'px';e.style.bottom=(innerHeight-r.top+6)+'px';e.hidden=false}
function mnuPick(k){const o=mnuL[k];if(!o)return;const i=$('#inp'),p=i.selectionStart,pre=i.value.slice(0,p).replace(/@[\w'-]*$/,''),t='@'+(o.c?uniqueTag(o.c):'everyone')+' ';
 i.value=pre+t+i.value.slice(p);i.setSelectionRange(pre.length+t.length,pre.length+t.length);i.focus();hideMnu()}
$('#mnu').onmousedown=e=>{e.preventDefault();const d=e.target.closest('.mi');if(d)mnuPick(+d.dataset.k)};
