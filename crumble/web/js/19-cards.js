/* ---------- character cards: gallery, card sheet, PNG card export ---------- */
let tagF='';const HUES=new Map(),SATS=new Map();
const tagsOf=c=>(c.tags||'').split(',').map(s=>s.trim()).filter(Boolean);
const blurb=c=>{const t=(c.description||c.personality||c.scenario||'').replace(/\s+/g,' ').trim(),m=t.match(/^.{24,170}?[.!?](\s|$)/);return m?m[0].trim():t.slice(0,150)};
const cardHue=c=>HUES.has(c.id)?HUES.get(c.id):hue(c.name),cardSat=c=>SATS.get(c.id)||44;
/* a card takes its colour from the portrait (average hue, weighted by saturation), or from the name when there is none */
function sampleHue(c){if(!c.avatar||HUES.has(c.id))return;HUES.set(c.id,hue(c.name));const im=new Image();
 im.onload=()=>{try{const cv=document.createElement('canvas');cv.width=cv.height=12;const x=cv.getContext('2d');x.drawImage(im,0,0,12,12);const d=x.getImageData(0,0,12,12).data;let r=0,g=0,b=0,w=0;
  for(let i=0;i<d.length;i+=4){const k=.15+(Math.max(d[i],d[i+1],d[i+2])-Math.min(d[i],d[i+1],d[i+2]))/40;r+=d[i]*k;g+=d[i+1]*k;b+=d[i+2]*k;w+=k}
  const[h,s]=hex2hsl('#'+hex2(r/w)+hex2(g/w)+hex2(b/w));HUES.set(c.id,Math.round(h));SATS.set(c.id,Math.round(Math.max(28,Math.min(58,s))));
  document.querySelectorAll(`[data-cid="${c.id}"]`).forEach(e=>{e.style.setProperty('--h',Math.round(h));e.style.setProperty('--s',SATS.get(c.id)+'%')})}catch(e){}};im.src=c.avatar}
const cardHTML2=c=>`<button class=card data-cid=${c.id} style="--h:${cardHue(c)};--s:${cardSat(c)}%"><div class="art${c.avatar?'':' ph'}" style="${c.avatar?`background-image:url('${at(c.avatar)}')`:''}">${c.avatar?'':ini(c.name)}</div><div class=cb><span class=cn>${esc(c.name||'(unnamed)')}</span><span class=cs>${esc(blurb(c))}</span><div class=ct>${tagsOf(c).slice(0,3).map(t=>`<i>${esc(t)}</i>`).join('')}</div></div></button>`;
function renderCards(){if(!S)return;const q=(($('#cs2').value||'')+' '+($('#csearch').value||'')).trim().toLowerCase(),all=S.chars,tc={};
 all.forEach(c=>tagsOf(c).forEach(t=>{const k=t.toLowerCase();tc[k]=(tc[k]||0)+1}));
 const top=Object.entries(tc).sort((a,b)=>b[1]-a[1]).slice(0,12).map(x=>x[0]);if(tagF&&!top.includes(tagF))tagF='';
 $('#tagrow').innerHTML=top.length?`<button class="tagc${tagF?'':' on'}" data-tag="">All</button>`+top.map(t=>`<button class="tagc${t==tagF?' on':''}" data-tag="${at(t)}">${esc(t)}</button>`).join(''):'';
 const list=all.filter(c=>(!q||[c.name,c.tags,c.description].join(' ').toLowerCase().includes(q))&&(!tagF||tagsOf(c).some(t=>t.toLowerCase()==tagF)));
 $('#cnt').textContent=all.length?`${all.length} ${all.length==1?'character':'characters'}${S.groups?.length?` and ${S.groups.length} ${S.groups.length==1?'group':'groups'}`:''}. Pick one to see their card.`:'No characters yet. Create one, or import a card.';
 $('#cgrid').innerHTML=(S.role=='guest'?'':`<div class=newpair><button class="card new" data-act=new>${ico('plus')}<b>New character</b><small>Blank sheet or AI draft</small></button><button class="card new" data-act=imp>${ico('import')}<b>Import a card</b><small>Drop a JSON or PNG here</small></button></div>`)+list.map(cardHTML2).join('');
 list.forEach(sampleHue);
 const gs=(S.groups||[]).filter(g=>!q||g.name.toLowerCase().includes(q));$('#gwrap').hidden=!gs.length&&S.role=='guest';
 $('#ggrid').innerHTML=(S.role=='guest'?'':`<button class="card new" data-act=newg>${ico('users')}<b>New group chat</b><small>Two or more characters together</small></button>`)+gs.map(g=>`<button class="card grp" data-gid=${g.id} style="--h:${hue(g.name)};--s:40%"><div class=art>${g.members.slice(0,3).map(i=>memberById(i)).filter(Boolean).map(m=>avatar(m)).join('')}</div><div class=cb><span class=cn>${esc(g.name)}</span><span class=cs>${esc(g.members.map(i=>memberById(i)?.name||'?').slice(0,5).join(', '))}</span></div></button>`).join('')}
$('#cs2').oninput=renderCards;
$('#tagrow').onclick=e=>{const b=e.target.closest('[data-tag]');if(b){tagF=b.dataset.tag;renderCards()}};
$('#cards').onclick=e=>{const b=e.target.closest('.card');if(!b)return;
 if(b.dataset.cid)return openSheet(b.dataset.cid);
 if(b.dataset.gid){pickGroup(b.dataset.gid);tab('chat');return}
 const a=b.dataset.act;if(a=='new')openNew();else if(a=='imp')$('#file').click();else if(a=='newg')$('#newg').click()};
/* a little tilt under the pointer (mouse only, off when motion is reduced) */
const calm=matchMedia('(prefers-reduced-motion:reduce)');
$('#cgrid').addEventListener('pointermove',e=>{if(e.pointerType!='mouse'||calm.matches)return;const c=e.target.closest('.card:not(.new)');if(!c)return;const r=c.getBoundingClientRect(),px=(e.clientX-r.left)/r.width-.5,py=(e.clientY-r.top)/r.height-.5;
 c.classList.add('t');c.style.setProperty('--ry',(px*7).toFixed(2)+'deg');c.style.setProperty('--rx',(-py*7).toFixed(2)+'deg')});
$('#cgrid').addEventListener('pointerout',e=>{const c=e.target.closest('.card');if(c&&!c.contains(e.relatedTarget)){c.classList.remove('t');c.style.removeProperty('--ry');c.style.removeProperty('--rx')}});
/* drop a card file anywhere on the gallery */
['dragover','dragenter'].forEach(t=>$('#cards').addEventListener(t,e=>{if(S.role=='guest')return;e.preventDefault();$('#cards').classList.add('drop')}));
['dragleave','drop'].forEach(t=>$('#cards').addEventListener(t,e=>{if(t=='dragleave'&&$('#cards').contains(e.relatedTarget))return;$('#cards').classList.remove('drop')}));
$('#cards').addEventListener('drop',e=>{if(S.role=='guest')return;e.preventDefault();const f=[...e.dataTransfer.files].find(f=>/\.(json|png)$/i.test(f.name));if(f)importCard(f)});
/* ---------- card sheet ---------- */
async function openSheet(id){const c=S.chars.find(x=>x.id==id);if(!c)return;const g=greetings(c),h=cardHue(c),adm=S.role!='guest',sec=(t,v)=>v&&v.trim()?`<div><h3>${t}</h3><p>${esc(v.trim())}</p></div>`:'';
 $('#cview').innerHTML=`<div class=mbox style="--h:${h}" role=dialog aria-modal=true aria-label="${at(c.name)}"><button class=mclose data-x=1 title=Close>${ico('close')}</button>
 <div class="mart${c.avatar?'':' ph'}" style="${c.avatar?`background-image:url('${at(c.avatar)}')`:''}">${c.avatar?'':`<div class=big>${ini(c.name)}</div>`}<div class=cap><b>${esc(c.name||'(unnamed)')}</b><span>${esc(tagsOf(c).join(', ')||'No tags yet')}</span></div></div>
 <div class=mbody>${sec('About',c.description)}${sec('Personality',c.personality)}${sec('Scenario',c.scenario)}
 ${g.length?`<div><h3>Opens with</h3><div class=mgreet>${fmt(g[0].replace(/\{\{user\}\}/gi,uname()).replace(/\{\{char\}\}/gi,c.name||'Character'),true)}</div></div>`:''}
 <div class=mfacts><span><b>${g.length}</b> ${g.length==1?'greeting':'greetings'}</span><span><b>${(c.lore||[]).length}</b> lore ${(c.lore||[]).length==1?'entry':'entries'}</span><span id=shn></span></div>
 <div class=mact><button class=go data-sa=chat>${ico('chat')}Chat</button><button data-sa=newchat>New chat</button>${adm?`<button data-sa=edit>${ico('edit')}Edit</button><button data-sa=json title="Tavern card V2 (JSON)">${ico('import')}JSON</button><button data-sa=png title="Tavern card V2 image">${ico('image')}PNG card</button>`:''}</div></div></div>`;
 $('#cview').dataset.id=id;$('#cview').hidden=false;$('#cview .go').focus();
 try{const r=await api('/api/chats/'+id),n=(r.chats||[]).length;if($('#cview').dataset.id==id&&$('#shn'))$('#shn').innerHTML=n?`<b>${n}</b> ${n==1?'chat':'chats'}, last: ${esc(r.chats[0].title)}`:'No chats yet'}catch(e){}}
const closeSheet=()=>{$('#cview').hidden=true};
$('#cview').onclick=async e=>{if(e.target==$('#cview')||e.target.closest('[data-x]'))return closeSheet();const b=e.target.closest('[data-sa]');if(!b)return;const id=$('#cview').dataset.id,a=b.dataset.sa,c=S.chars.find(x=>x.id==id);closeSheet();
 if(a=='chat'){await pick(id);tab('chat')}else if(a=='newchat'){await pick(id);await newChat();tab('chat')}else if(a=='edit'){await pick(id);tab('editor')}
 else if(a=='json')dl(JSON.stringify(cardJSON(c),null,1),(c.name||'character')+'.json','application/json');else if(a=='png')exportPNG(c)};
document.addEventListener('keydown',e=>{if(e.key=='Escape'&&!$('#cview').hidden)closeSheet()});
/* ---------- export a card as a PNG with the character data inside (Tavern card V2, readable by the importer and by other apps) ---------- */
const CRC=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xedb88320^(c>>>1):c>>>1;t[n]=c>>>0}return t})();
const crc32=b=>{let c=~0;for(const x of b)c=CRC[(c^x)&255]^(c>>>8);return~c>>>0};
const b64u=s=>{const b=new TextEncoder().encode(s);let o='';for(let i=0;i<b.length;i+=8192)o+=String.fromCharCode(...b.subarray(i,i+8192));return btoa(o)};
function addChara(png,json){const text=new TextEncoder().encode('chara\0'+b64u(JSON.stringify(json))),type=new TextEncoder().encode('tEXt'),body=new Uint8Array(4+text.length);body.set(type);body.set(text,4);
 const chunk=new Uint8Array(12+text.length),v=new DataView(chunk.buffer);v.setUint32(0,text.length);chunk.set(body,4);v.setUint32(8+text.length,crc32(body));
 const at=33,out=new Uint8Array(png.length+chunk.length);out.set(png.subarray(0,at));out.set(chunk,at);out.set(png.subarray(at),at+chunk.length);return out}   // right after the 25-byte IHDR chunk
const loadImg=src=>new Promise((ok,no)=>{const i=new Image();i.onload=()=>ok(i);i.onerror=no;i.src=src});
async function exportPNG(c){try{await document.fonts.load('700 56px Bricolage');await document.fonts.load('400 24px Figtree')}catch(e){}
 const W=640,H=880,cv=document.createElement('canvas');cv.width=W;cv.height=H;const x=cv.getContext('2d'),h=cardHue(c);
 const bg=x.createLinearGradient(0,0,W,H);bg.addColorStop(0,`hsl(${h} 62% 34%)`);bg.addColorStop(1,`hsl(${(h+50)%360} 55% 13%)`);x.fillStyle=bg;x.fillRect(0,0,W,H);
 if(c.avatar)try{const im=await loadImg(c.avatar),k=Math.max(W/im.width,H/im.height);x.drawImage(im,(W-im.width*k)/2,Math.min(0,(H-im.height*k)*.2),im.width*k,im.height*k)}catch(e){}
 else{x.fillStyle='rgba(255,255,255,.55)';x.font='700 300px Bricolage, sans-serif';x.textAlign='center';x.fillText(ini(c.name),W/2,420)}
 const ov=x.createLinearGradient(0,H*.42,0,H);ov.addColorStop(0,'rgba(10,6,6,0)');ov.addColorStop(.75,'rgba(10,6,6,.9)');x.fillStyle=ov;x.fillRect(0,0,W,H);
 x.textAlign='left';x.fillStyle='#f7efe8';x.font='700 54px Bricolage, sans-serif';
 const wrap=(t,mw,max)=>{const w=t.split(' '),o=[];let l='';for(const s of w){if(x.measureText(l+' '+s).width>mw&&l){o.push(l);l=s}else l=l?l+' '+s:s}if(l)o.push(l);return o.slice(0,max)};
 const nm=wrap(c.name||'Character',W-64,2);let y=H-70-(nm.length-1)*58;const bl=wrap(blurb(c),W-64,2);
 x.font='400 22px Figtree, sans-serif';const bh=bl.length*30;y=H-48-bh-(nm.length*58)-(tagsOf(c).length?36:0);
 x.font='700 54px Bricolage, sans-serif';x.fillStyle='#f7efe8';nm.forEach((l,i)=>x.fillText(l,32,y+54+i*58));y+=nm.length*58+4;
 x.font='400 22px Figtree, sans-serif';x.fillStyle='rgba(247,239,232,.82)';bl.forEach((l,i)=>x.fillText(l,32,y+26+i*30));y+=bh+10;
 if(tagsOf(c).length){x.font='600 17px Figtree, sans-serif';let tx=32;for(const t of tagsOf(c).slice(0,4)){const w=x.measureText(t).width+24;x.fillStyle='rgba(255,255,255,.17)';x.beginPath();x.roundRect(tx,y+8,w,28,14);x.fill();x.fillStyle='#f7efe8';x.fillText(t,tx+12,y+28);tx+=w+8}}
 x.strokeStyle='rgba(255,255,255,.2)';x.lineWidth=2;x.beginPath();x.roundRect(1,1,W-2,H-2,6);x.stroke();
 cv.toBlob(async b=>{const out=addChara(new Uint8Array(await b.arrayBuffer()),cardJSON(c)),a=document.createElement('a');a.href=URL.createObjectURL(new Blob([out],{type:'image/png'}));a.download=(c.name||'character')+'.png';a.click()},'image/png')}
