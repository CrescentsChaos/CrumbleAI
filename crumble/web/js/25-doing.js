/* ---------- what everyone is doing right now, and visiting a place as a scene of its own ----------
   The model decides (once per stretch of story time) who is at the place and what each person is doing and how they meet you; the answer is kept in the
   chat (chat.cfg.doing) so swipes and rewinds stay stable. Nothing here is a timetable. A visit is a narrator-led chat that belongs to the place: pl_<id>. */
const doingLog=()=>(chat?.cfg.doing||[]).filter(x=>x.since<=hist.length);
const doingNow=()=>{const l=doingLog(),e=l.length?l[l.length-1]:null;return e&&(e.pid===undefined||e.pid===(curPlace()?.id||''))?e:null};   // what was worked out for another place is not what they are doing here
const doingMap=()=>{const e=doingNow();return e?e.people:undefined};
const sceneOn=()=>!!(G&&G.place);
const presentIds=()=>{const e=doingNow();return e?Object.keys(e.people).filter(i=>e.people[i].here&&memberById(i)):[]};
function syncScene(){if(!sceneOn())return;G.members=presentIds();buildMen();draw()}
let doingLater=false;   // refresh the activities after the reply instead of before it
async function doingEnsure(o={}){
 if(!chat||!cur?.id||U.story===false||U.storyRoutines===false||ctl)return;
 const scene=sceneOn(),p=curPlace(),have=doingNow();
 if(!scene&&!p&&!U.doingAnywhere)return;   // outside a place this is one more model call before every reply for a line nobody sees: off unless asked (Settings)
 if(!o.quiet)setStatus('looking around…');
 try{
  const r=await api('/api/doing','POST',{...(scene?{}:G?{group:G.id}:{cids:[cur.id]}),place:p?{id:p.id,since:p.since}:undefined,history:apiHist(hist.filter(m=>!m.ooc)),turn:hist.length,
   scene:chat.cfg.scene||'',clock:U.timeaware?clock():'',story_start:chat.cfg.start||'',story:storyCfg(),user:uname(),prev:have?have.people:{},
   have:have?{key:have.key,turn:have.turn,ids:have.ids}:undefined,force:!!o.force,arriving:!!o.arriving,seed:chat.id});
  if(r&&r.people){const l=(chat.cfg.doing||[]).filter(x=>x.since!==hist.length);l.push({since:hist.length,pid:p?p.id:'',key:r.key,turn:r.turn,ids:r.ids,people:r.people,clock:r.clock||''});chat.cfg.doing=l.slice(-40);saveChat()}
 }catch(e){}
 if(!o.quiet)setStatus('online');syncScene()}
async function sceneOpen(pid,o={}){
 const p=plById(pid);if(!p||ctl||rounding)return;
 G={id:'pl_'+pid,name:p.name,members:[],narrator:true,place:pid,pace:'natural',scenario:p.description||''};
 cur={id:G.id,name:p.name,avatar:'',gender:'',first_mes:'',alts:'',tags:'',group:1};buildMen();renderChars();
 chats=(await api('/api/chats/'+G.id)).chats||[];
 if(o.last&&chats.length){await openChat(chats[0].id);if(!curPlace()){setPlace(pid,{silent:true})}placeHead();placeBg();tab('chat');await doingEnsure();return}
 await newChat();setPlace(pid,{silent:true});placeHead();placeBg();tab('chat');
 hist.push({role:'user',content:`*I walk into ${p.name}.*`,ts:Date.now()});saveChat();draw();
 await doingEnsure({arriving:true,force:true});
 if(await gen('reply','__narrator__',{why:'enter'})===true&&!ctl)await round({keep:true})}
async function sceneLeave(){const id=U.last&&S.chars.find(c=>c.id==U.last)?U.last:S.chars[0]?.id;if(id){await pick(id);tab('chat')}}
