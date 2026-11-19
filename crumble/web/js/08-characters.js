/* ---------- characters ---------- */
function renderChars(){if(!$('#cards').hidden)renderCards();const q=($('#csearch').value||'').toLowerCase();
 $('#clist').innerHTML=S.chars.filter(c=>!q||[c.name,c.tags,c.description].join(' ').toLowerCase().includes(q)).map(c=>
  `<div class="ch ${cur&&cur.id==c.id?'on':''}" data-id=${c.id}>${avatar(c,'sm')}<span>${esc(c.name||'(unnamed)')}<small>${esc((c.tags||'').split(',').slice(0,3).join(' · '))}</small></span></div>`).join('');renderGroups()}
$('#clist').onclick=e=>{const d=e.target.closest('.ch');if(d){pick(d.dataset.id);closeDrawer();tab('chat')}};$('#csearch').oninput=renderChars;
function renderForm(c){let h='';for(const[sec,fs]of S.schema){h+=`<details ${sec=='Core'?'open':''}><summary>${sec}</summary>`;
 for(const[k,l,r]of fs)h+=`<label>${l}</label><textarea data-k=${k} rows=${r}>${esc(c[k]||'')}</textarea>`;h+='</details>'}
 h+=persForm();h+=`<details><summary>Lorebook (inserted when a key appears in the last few messages; no keys = always)</summary><div id=lore></div><button id=addlore>Add entry</button></details>`;
 $('#form').innerHTML=h;$('#lore').innerHTML='';(c.lore||[]).forEach(loreRow);$('#addlore').onclick=()=>loreRow({keys:'',content:''});avPrev(c);persPreview()}
function avPrev(c){$('#eav').style.cssText=avs(c);$('#eav').textContent=c.avatar?'':ini(c.name);edLive()}
function edLive(){const n=($('[data-k=name]')?.value||'').trim(),t=($('[data-k=tags]')?.value||'').split(',').map(s=>s.trim()).filter(Boolean);$('#epn').textContent=n||'New character';$('#ept').innerHTML=t.slice(0,6).map(x=>`<i>${esc(x)}</i>`).join('');if(cur&&!cur.avatar){$('#eav').style.cssText=`background:${grad(n||'?')}`;$('#eav').textContent=ini(n||'?')}}
$('#form').addEventListener('input',e=>{if(e.target.dataset.k=='name'||e.target.dataset.k=='tags')edLive()});
function loreRow(e){const d=document.createElement('div');d.className='lore';
 d.innerHTML=`<input placeholder="keys, comma separated" value="${at(e.keys||'')}"><textarea rows=3 placeholder="Entry text">${esc(e.content||'')}</textarea><button class=x>Remove</button>`;
 d.querySelector('button').onclick=()=>d.remove();$('#lore').append(d)}
function collect(){const c={id:cur?.id||'',avatar:cur?.avatar||''};$$('[data-k]').forEach(e=>c[e.dataset.k]=e.value);
 c.lore=[...$$('.lore')].map(d=>({keys:d.children[0].value,content:d.children[1].value}));return c}
function openNew(){G=null;MEN=null;cur=blank();hist=[];chat=null;chats=[];drawChats();draw();renderForm(cur);renderChars();tab('editor')}
$('#new').onclick=openNew;
$('#save').onclick=async()=>{const c=await api('/api/chars','POST',collect());const i=S.chars.findIndex(x=>x.id==c.id);
 i<0?S.chars.push(c):S.chars[i]=c;const was=cur.id;cur=c;renderChars();if(!was){chats=[];await newChat()}else draw();tab('chat')};
$('#dup').onclick=async()=>{const c={...collect(),id:''};c.name=(c.name||'Character')+' (copy)';const r=await api('/api/chars','POST',c);
 S.chars.push(r);cur=r;chats=[];renderChars();renderForm(r);await newChat();tab('chat')};
$('#del').onclick=async()=>{if(!cur?.id||!confirm('Delete '+cur.name+' and its chats?'))return;await api('/api/chars/'+cur.id,'DELETE');
 S.chars=S.chars.filter(c=>c.id!=cur.id);cur=null;chat=null;S.chars[0]?pick(S.chars[0].id):openNew()};
$('#gen').onclick=async()=>{const concept=$('#concept').value.trim();if(!concept)return;$('#gstat').textContent='Drafting... (can take a minute)';
 const r=await api('/api/gen_char','POST',{concept});if(r.err){$('#gstat').textContent=r.err;return}
 $$('[data-k]').forEach(e=>{if(!e.value.trim()&&r[e.dataset.k])e.value=r[e.dataset.k]});$('#gstat').textContent='Done. Review the fields, then save.'};
async function shrink(f,s=256){const bm=await createImageBitmap(f),side=Math.min(bm.width,bm.height),cv=document.createElement('canvas');cv.width=cv.height=s;
 cv.getContext('2d').drawImage(bm,(bm.width-side)/2,(bm.height-side)/2,side,side,0,0,s,s);return cv.toDataURL('image/jpeg',.86)}
$('#avup').onclick=()=>$('#avfile').click();
$('#avfile').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f||!cur)return;try{cur.avatar=await shrink(f);avPrev(cur)}catch(x){alert('Could not read that image')}};
$('#avrm').onclick=()=>{if(cur){cur.avatar='';avPrev(cur)}};

// Character card import/export (Tavern card V2: JSON, or PNG with a 'chara' text chunk)
const unb64=s=>new TextDecoder().decode(Uint8Array.from(atob(s),c=>c.charCodeAt(0)));
async function pngCard(buf){const v=new DataView(buf);let o=8;while(o<buf.byteLength){const n=v.getUint32(o),t=String.fromCharCode(...new Uint8Array(buf,o+4,4));
 if(t=='tEXt'){const d=new Uint8Array(buf,o+8,n),z=d.indexOf(0);if(new TextDecoder().decode(d.slice(0,z))=='chara')return JSON.parse(unb64(new TextDecoder().decode(d.slice(z+1))))}o+=12+n}throw Error('No character data in this PNG')}
$('#imp').onclick=()=>$('#file').click();
$('#file').onchange=e=>{const f=e.target.files[0];e.target.value='';if(f)importCard(f)};
async function importCard(f){
 try{const png=f.name.toLowerCase().endsWith('.png'),j=png?await pngCard(await f.arrayBuffer()):JSON.parse(await f.text());const d=j.data||j,x=d.extensions?.hearth||{},c=blank();
  Object.assign(c,x);c.name=d.name||'';c.description=d.description||'';c.personality=d.personality||'';c.scenario=d.scenario||'';c.first_mes=d.first_mes||'';
  c.mes_example=d.mes_example||'';c.system_prompt=d.system_prompt||'';c.post_history=d.post_history_instructions||'';c.notes=d.creator_notes||'';
  c.alts=(d.alternate_greetings||[]).join('\n---\n');c.tags=(d.tags||[]).join(', ');
  c.lore=(d.character_book?.entries||[]).map(e=>({keys:(e.keys||[]).join(', '),content:e.content||''}));
  if(png&&!c.avatar)try{c.avatar=await shrink(f)}catch(x){}
  c.id='';cur=c;G=null;MEN=null;hist=[];chat=null;chats=[];drawChats();renderForm(c);tab('editor')}catch(err){alert('Import failed: '+err.message)}}
const cardJSON=c=>{const ex={};S.ext.forEach(k=>ex[k]=c[k]);if(c.avatar)ex.avatar=c.avatar;const lore=c.lore||[];
 return{spec:'chara_card_v2',spec_version:'2.0',data:{name:c.name,description:c.description,personality:c.personality,scenario:c.scenario,first_mes:c.first_mes,
  mes_example:c.mes_example,system_prompt:c.system_prompt,post_history_instructions:c.post_history,creator_notes:c.notes,
  alternate_greetings:(c.alts||'').split(/\n-{3,}\n/).map(s=>s.trim()).filter(Boolean),tags:(c.tags||'').split(',').map(s=>s.trim()).filter(Boolean),
  character_book:{entries:lore.map((e,i)=>({id:i,keys:(e.keys||'').split(',').map(s=>s.trim()).filter(Boolean),content:e.content,enabled:true,insertion_order:i}))},
  extensions:{hearth:ex}}}};
$('#exp').onclick=()=>{const c=collect();dl(JSON.stringify(cardJSON(c),null,1),(c.name||'character')+'.json','application/json')};
$('#exppng').onclick=()=>exportPNG(collect());
