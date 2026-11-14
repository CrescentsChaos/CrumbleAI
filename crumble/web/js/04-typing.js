/* ---------- typing animation (only runs once the whole reply exists) ---------- */
const KB={q:'wa',w:'qes',e:'wrd',r:'etf',t:'ryg',y:'tuh',u:'yij',i:'uok',o:'ipl',p:'ol',a:'qsz',s:'awdx',d:'sefc',f:'drgv',g:'fthb',h:'gyjn',j:'hukm',k:'jil',l:'ko',z:'asx',x:'zsc',c:'xdv',v:'cfb',b:'vgn',n:'bhm',m:'nj'};
const wrongKey=ch=>{const o=KB[ch.toLowerCase()]||'e',w=o[Math.floor(Math.random()*o.length)];return ch==ch.toUpperCase()?w.toUpperCase():w};
const autoscroll=()=>{const L=$('#log');if(L.scrollHeight-L.scrollTop-L.clientHeight<170)L.scrollTop=L.scrollHeight};
function skipTyping(){anim++;typingNow=false;$('#skip').hidden=true;if(!ctl)setStatus('online')}
async function typeEl(b,id,sf){
 const w=document.createTreeWalker(b,NodeFilter.SHOW_TEXT),ns=[];let x;while(x=w.nextNode())ns.push([x,x.data]);
 ns.forEach(([n])=>n.data='');
 const cps={fast:120,normal:55,slow:26}[U.typing]||55;let acc=0,t0=performance.now();
 for(const[n,f]of ns){let k=0;
  while(k<f.length){
   if(id!=anim||document.hidden){ns.forEach(([n,f])=>n.data=f);return}
   const t=performance.now();acc+=(t-t0)/1000*cps*(.55+Math.random()*.9);t0=t;
   let st=Math.floor(acc);if(st<1){await sleep(16);continue}
   acc-=st;let pz=0;
   while(st-->0&&k<f.length){const ch=f[k++],nx=f[k];pz=Math.max(pz,/[.!?]/.test(ch)&&(!nx||/\s/.test(nx))?260:ch=='…'?320:/[,;:]/.test(ch)?110:ch=='\n'?240:/[—–]/.test(ch)?150:0)}
   n.data=f.slice(0,k);autoscroll();
   if(U.typos&&chat?.cfg.mode=='text'&&k>1&&/\s/.test(f[k-1])&&/[a-z]/i.test(f[k]||'')&&/^\w{4}/.test(f.slice(k))&&Math.random()<.05){
    n.data=f.slice(0,k)+wrongKey(f[k]);await sleep(170+Math.random()*180);n.data=f.slice(0,k);await sleep(120);t0=performance.now();acc=0}
   if(pz){await sleep(pz*sf);t0=performance.now();acc=0}}}}
async function typeMsg(i){
 const el=$(`.m[data-i="${i}"]`),bs=$$(`.m[data-i="${i}"] .tx`);if(!el||!bs.length||U.typing=='instant'||document.hidden)return;
 const id=++anim,sf={fast:.5,normal:1,slow:1.7}[U.typing]||1;typingNow=true;$('#skip').hidden=false;setStatus('typing…');el.classList.add('fresh');
 bs.slice(1).forEach(b=>b.style.display='none');
 try{for(let j=0;j<bs.length;j++){if(id!=anim)break;
   if(j>0){const d=document.createElement('div');d.className='tx dt';d.innerHTML='<div class=dots><i></i><i></i><i></i></div>';bs[j].before(d);
    await sleep(Math.min(1800,350+bs[j].textContent.length*22)*sf);d.remove();if(id!=anim)break;bs[j].style.display='';beep(760,.06)}
   await typeEl(bs[j],id,sf)}
 }finally{bs.forEach(b=>b.style.display='');el.querySelectorAll('.tx.dt').forEach(d=>d.remove());if(id==anim){typingNow=false;$('#skip').hidden=true;setStatus('online')}}}

/* ---------- voice ---------- */
const speak=t=>{if(!('speechSynthesis' in window))return;speechSynthesis.cancel();
 const s=split(t).body.replace(/\*[^*]+\*/g,' ').replace(/\([^)]*\)/g,' ').replace(/[*_]/g,'').trim();if(!s)return;
 const u=new SpeechSynthesisUtterance(s),v=speechSynthesis.getVoices().find(v=>v.name==U.voice),g=cur?.gender||'';
 if(v)u.voice=v;u.rate=+U.rate||1;u.pitch=/\b(female|woman|girl|she)\b/i.test(g)?1.12:/\b(male|man|boy|he)\b/i.test(g)?.92:1;speechSynthesis.speak(u)};
