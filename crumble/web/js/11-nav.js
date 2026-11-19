$('#load').onclick=async()=>{const path=$('#mpath').value.trim()||$('#msel').value;if(!path)return;$('#mstat').textContent='Loading (this can take a while)...';
 const r=await api('/api/load','POST',{path,n_ctx:$('#nctx').value,n_gpu:$('#ngl').value});if(!r.err)S.loaded=r.loaded;$('#mstat').textContent=r.err?'Error: '+r.err:'Loaded: '+r.loaded+(S.gpu?' (GPU)':' - CPU ONLY build');mchip()};
function mchip(){const e=$('#mchip');if(!e||!S)return;e.classList.toggle('on',!!S.loaded);e.querySelector('span').textContent=S.backend?(S.loaded?String(S.loaded).split(/[\\/]/).pop().replace(/\.gguf$/i,''):'No model loaded'):'llama-cpp missing';e.title=(S.loaded?'Loaded: '+S.loaded:'No model loaded')+(S.backend?(S.gpu?' (GPU)':' (CPU only)'):'')+'. Click to open the model box'}
$('#mchip').onclick=()=>{if(S.role=='guest')return;document.body.classList.add('drawer');const d=$('#side details.mdl.adm');if(d){d.open=true;$('#msel').focus()}};
$('#uname').addEventListener('input',()=>{$('#meav').textContent=ini($('#uname').value||'U')});
function tab(t){closeDrawer();if(t=='samp')renderShare(true);$$('nav button').forEach(b=>b.classList.toggle('on',b.dataset.t==t));
 for(const id of['chat','cards','editor','mem','samp','gedit'])$('#'+id).hidden=id!=t;if(t=='mem')renderMem();if(t=='cards')renderCards();if(t=='chat'){const L=$('#log');L.scrollTop=L.scrollHeight}}
document.querySelector('nav').onclick=e=>{const b=e.target.closest('[data-t]');if(b)tab(b.dataset.t)};

async function init(){S=await api('/api/state');
 $('#msel').innerHTML='<option value="">(choose from ./models)</option>'+S.models.map(m=>`<option>${esc(m)}</option>`).join('');
 $('#mstat').textContent=S.backend?((S.loaded?'Loaded: '+S.loaded:'No model loaded')+(S.gpu?' (GPU)':' - CPU ONLY build: see the console to enable the GPU')):'llama-cpp-python missing: pip install llama-cpp-python';
 document.body.classList.toggle('guest',S.role=='guest');if(S.role=='guest'&&(!U.uname||U.uname=='User'))U.uname=S.name;
 $('#uname').value=U.uname;$('#persona').value=U.persona;$('#ustats').value=U.ustats||'';$('#ugear').value=U.ugear||'';S.groups=S.groups||[];renderChars();renderSettings();applyUI();mchip();$('#meav').textContent=ini(U.uname||'U');
 const first=S.chars.find(c=>c.id==U.last)||S.chars[0];if(first){await pick(first.id);if(!S.chars.some(c=>c.id==U.last))tab('cards')}else openNew()}
