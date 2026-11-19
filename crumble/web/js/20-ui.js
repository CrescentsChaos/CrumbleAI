/* ---------- in-app dropdowns: every <select> (now and any added later) gets a themed list instead of the browser's own ---------- */
(()=>{
 const pop=document.createElement('div'),scrim=document.createElement('div');
 pop.id='ddpop';pop.hidden=true;pop.setAttribute('role','listbox');scrim.id='ddscrim';scrim.hidden=true;document.body.append(scrim,pop);
 let cs=null,ix=0,items=[];
 const vd=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value');   // code that sets select.value must refresh the visible label too
 Object.defineProperty(HTMLSelectElement.prototype,'value',{configurable:true,get(){return vd.get.call(this)},set(v){vd.set.call(this,v);this._ref&&this._ref()}});
 const lab=s=>{const o=s.options[s.selectedIndex];return o?o.textContent:''};
 function enhance(s){
  if(s._dd||s.multiple||s.size>1)return;
  const b=document.createElement('button');b.type='button';b.className='dd';b.setAttribute('aria-haspopup','listbox');b.innerHTML='<span class=ddl></span>';
  const st=s.getAttribute('style');if(st)b.style.cssText=st;
  s.classList.add('ddn');s.after(b);s._dd=b;
  const ref=()=>{b.firstChild.textContent=lab(s)||'Select…';b.disabled=s.disabled;if(s.title)b.title=s.title};
  s._ref=ref;ref();
  b.onclick=e=>{e.preventDefault();e.stopPropagation();cs===s?close():show(s)};
  b.onkeydown=e=>{if(e.key=='ArrowDown'||e.key=='ArrowUp'){e.preventDefault();show(s)}};
  s.addEventListener('change',ref);
  new MutationObserver(ref).observe(s,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['disabled','selected']});
 }
 function show(s){
  close();cs=s;items=[];pop.innerHTML='';
  const sheet=matchMedia('(max-width:760px)').matches,t=s.closest('div')?.querySelector('.hl,label')?.textContent?.trim();
  if(sheet&&t&&t.length<48)pop.insertAdjacentHTML('beforeend',`<div class=ddt>${esc(t)}</div>`);
  const add=o=>{const d=document.createElement('div');d.className='ddo'+(o.selected?' on':'')+(o.disabled?' off':'');d.setAttribute('role','option');d.dataset.i=items.length;
   d.innerHTML=`<span>${esc(o.textContent)}</span>${o.selected?'<i>✓</i>':''}`;items.push({o,d});pop.append(d)};
  [...s.children].forEach(n=>{if(n.tagName=='OPTGROUP'){const g=document.createElement('div');g.className='ddg';g.textContent=n.label;pop.append(g);[...n.children].forEach(add)}else add(n)});
  ix=Math.max(0,s.selectedIndex);pop.classList.toggle('sheet',sheet);pop.hidden=false;scrim.hidden=!sheet;s._dd.classList.add('open');
  if(!sheet){const r=s._dd.getBoundingClientRect(),below=innerHeight-r.bottom-12,above=r.top-12,up=below<220&&above>below,room=Math.min(340,up?above:below);
   pop.style.cssText=`min-width:${r.width}px;max-width:min(92vw,420px);left:${Math.max(8,Math.min(r.left,innerWidth-r.width-8))}px;max-height:${room}px;${up?`bottom:${innerHeight-r.top+6}px;top:auto`:`top:${r.bottom+6}px;bottom:auto`}`}
  else pop.style.cssText='';
  mark(true)}
 function mark(scroll){items.forEach((it,k)=>it.d.classList.toggle('hot',k==ix));if(scroll)items[ix]?.d.scrollIntoView({block:'nearest'})}
 function close(){if(!cs)return;cs._dd?.classList.remove('open');cs=null;pop.hidden=true;scrim.hidden=true}
 function pick(k){const it=items[k],s=cs;if(!it||it.o.disabled||!s)return;close();
  if(s.selectedIndex!=it.o.index){s.selectedIndex=it.o.index;s._ref();s.dispatchEvent(new Event('input',{bubbles:true}));s.dispatchEvent(new Event('change',{bubbles:true}))}
  s._dd.focus({preventScroll:true})}
 pop.onclick=e=>{e.stopPropagation();const d=e.target.closest('.ddo');if(d)pick(+d.dataset.i)};
 pop.onmousemove=e=>{const d=e.target.closest('.ddo');if(d&&+d.dataset.i!=ix){ix=+d.dataset.i;mark()}};
 scrim.onclick=e=>{e.stopPropagation();close()};
 document.addEventListener('click',e=>{if(cs&&!e.target.closest('#ddpop'))close()});
 document.addEventListener('keydown',e=>{if(!cs)return;const k=e.key,n=items.length;
  if(k=='ArrowDown'||k=='ArrowUp'){e.preventDefault();e.stopPropagation();ix=(ix+(k=='ArrowDown'?1:n-1))%n;mark(true)}
  else if(k=='Enter'||k==' '){e.preventDefault();e.stopPropagation();pick(ix)}
  else if(k=='Escape'||k=='Tab'){if(k=='Escape'){e.preventDefault();e.stopPropagation()}close()}
  else if(k.length==1){const q=k.toLowerCase(),j=items.findIndex((it,m)=>m>ix&&it.o.textContent.trim().toLowerCase().startsWith(q));if(j>=0){ix=j;mark(true)}}},true);
 addEventListener('scroll',e=>{if(cs&&!pop.contains(e.target))close()},true);addEventListener('resize',close);
 const scan=r=>r.querySelectorAll&&r.querySelectorAll('select:not(.ddn)').forEach(enhance);
 new MutationObserver(ms=>{for(const m of ms)m.addedNodes.forEach(n=>{if(n.nodeType==1){if(n.matches('select:not(.ddn)'))enhance(n);scan(n)}})}).observe(document.documentElement,{childList:true,subtree:true});
 scan(document);
})();

/* ---------- phone layout: fewer controls on screen, the rest one tap away ---------- */
(()=>{
 const mq=matchMedia('(max-width:760px)');
 $('#menu2').onclick=e=>{e.stopPropagation();document.body.classList.toggle('drawer')};
 const tl=on=>{document.body.classList.toggle('tl',on);$('#tgl').classList.toggle('on',on);U.toolsOpen=on;persist()};
 $('#tgl').onclick=()=>tl(!document.body.classList.contains('tl'));
 $('#hstyle').onclick=()=>{$('.chead').classList.remove('open');$('#themebtn').click()};
 $('#hedit').onclick=()=>{$('.chead').classList.remove('open');tab('editor')};
 tl(!!U.toolsOpen&&mq.matches);
 mq.addEventListener('change',()=>tl(false));
})();
