/* ---------- chats ---------- */
async function pick(id){const c=S.chars.find(c=>c.id==id);if(!c)return;U.last=id;persist();G=null;MEN=null;cur=c;renderChars();renderForm(cur);
 chats=(await api('/api/chats/'+id)).chats||[];chats.length?await openChat(chats[0].id):await newChat()}
async function openChat(chid){const r=await api(`/api/chat/${cur.id}/${chid}`);
 chat={id:chid,title:r.title,state:{...newState(),...(r.state||{})},cfg:{...newCfg(),...(r.cfg||{})},rp:r.rp||{}};if(G)chat.state.members=chat.state.members||{};hist=r.history||[];gi=0;lastAct=Date.now();nudges=0;
 $('#ctxm').textContent='';drawChats();draw();if(!$('#mem').hidden)renderMem()}
async function newChat(){chat={id:rid(),title:'New chat',state:{...newState(),...(G?{members:{}}:{})},cfg:newCfg(),rp:{}};gi=0;resetChat();await saveChat();draw()}
async function saveChat(){if(!cur?.id||!chat)return;const r=await api('/api/chat_save','POST',{cid:cur.id,id:chat.id,title:chat.title,history:hist,state:chat.state,cfg:chat.cfg,rp:chat.rp});
 if(r.err)return;chat.title=r.title;const m={id:chat.id,title:chat.title,n:hist.length},i=chats.findIndex(c=>c.id==chat.id);i<0?chats.unshift(m):chats[i]=m;drawChats()}
const saveSoon=()=>{clearTimeout(saveT);saveT=setTimeout(saveChat,500)};
function drawChats(){$('#chsel').innerHTML=chats.map(c=>`<option value=${c.id} ${chat&&c.id==chat.id?'selected':''}>${esc(c.title)} (${c.n})</option>`).join('')}
function resetChat(i=0){const g=greetings(cur);hist=g.length?[{role:'assistant',content:g[i%g.length],ts:Date.now()}]:[]}
function restore(m){if(m?.oid)dropNote(m.oid);const mc=m?.snapc;if(m?.snap){try{const o=JSON.parse(m.snap);if(m.snapc)Object.assign(mst(m.snapc),o);else chat.state={...chat.state,...o}}catch(e){}delete m.snap;delete m.snapc}
 if(m?.rpsnap){try{chat.rp=JSON.parse(m.rpsnap)}catch(e){}for(const[id,d]of Object.entries(m.affd||{}))addAff(id,-d);delete m.rpsnap;delete m.affd}
 if(m?.mundo){undoMem(m.mundo,mc);delete m.mundo}bondUndo(m)}
