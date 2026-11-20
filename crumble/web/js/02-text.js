/* ---------- look ---------- */
const hue=n=>[...(n||'?')].reduce((a,c)=>a*31+c.charCodeAt(0)>>>0,7)%360,
 grad=n=>`linear-gradient(135deg,hsl(${hue(n)} 75% 68%),hsl(${(hue(n)+40)%360} 70% 58%))`,
 ini=n=>esc((n||'?').trim()[0]||'?').toUpperCase(),
 avs=c=>c.avatar?`background:center/cover url('${c.avatar}')`:`background:${grad(c.name)}`,
 avin=c=>c.avatar?'':ini(c.name),
 avatar=(c,cls='')=>`<div class="av ${cls}" style="${avs(c)}">${avin(c)}</div>`;
const hm=t=>new Date(t).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
function dayLabel(t){const d=new Date(t),same=(a,b)=>a.toDateString()==b.toDateString();
 return(same(d,new Date())?'Today':same(d,new Date(Date.now()-864e5))?'Yesterday':d.toLocaleDateString([],{weekday:'short',day:'numeric',month:'short'}))+' '+hm(t)}
const period=h=>h<5?'late at night':h<12?'morning':h<17?'afternoon':h<21?'evening':'night';
const clock=()=>{const d=new Date();return d.toLocaleString('en-US',{weekday:'long',year:'numeric',month:'long',day:'numeric',hour:'numeric',minute:'2-digit'})+` (${period(d.getHours())})`};
let AC;function beep(f=640,d=.09,v=.04){if(!U.sound)return;try{AC=AC||new AudioContext();const o=AC.createOscillator(),g=AC.createGain();o.frequency.value=f;g.gain.value=v;o.connect(g);g.connect(AC.destination);o.start();g.gain.exponentialRampToValueAtTime(.0001,AC.currentTime+d);o.stop(AC.currentTime+d)}catch(e){}}
const dl=(txt,name,type)=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([txt],{type}));a.download=name;a.click()};

/* ---------- text formatting ---------- */
function split(t){if(!t.includes('<think>')&&t.includes('</think>'))t='<think>'+t;let th='';
 const body=t.replace(/<think>([\s\S]*?)(<\/think>|$)/g,(m,x)=>{th+=x;return''});return{th:th.trim(),body:body.trim()}}
/* a model may write &quot; &amp; &#39; &lt;; esc() then showed them literally (or double-escaped them). Decode complete entities once, before escaping. The user's own text is shown as typed. */
const ENT=/&(?:#\d{1,6}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,8});/g,_ta=document.createElement('textarea'),dec=s=>{for(let i=0;i<3&&s.includes('&');i++){const n=s.replace(ENT,m=>{_ta.innerHTML=m;return _ta.value});if(n==s)break;s=n}return s};
function fmt(t,narr=true,mine=false){t=esc(mine?t:dec(t)).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>');
 const act=x=>(U.actions||mine)?`<em class=act>${x}</em>`:'';
 t=t.replace(/\*([^*\n]+)\*/g,(m,x)=>act(x));if(narr)t=t.replace(/\(([^()\n]{3,})\)/g,(m,x)=>act('('+x+')'));
 const h=t.replace(/(&quot;|"|“)([^"“”\n]+)(&quot;|"|”)/g,'<span class=q>$1$2$3</span>').replace(/[ \t]{2,}/g,' ').trim();return MEN?h.replace(MEN,x=>'<span class=mn>'+x+'</span>'):h}
const plain=m=>split(m.content).body;
