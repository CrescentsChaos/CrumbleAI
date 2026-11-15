/* ---------- generation: the whole reply is made first, then typed out ---------- */
const apiChar=(c=cur)=>{const{avatar,...x}=c;return x};
const apiHist=a=>a.filter(m=>m.content&&m.content.trim()).map(m=>({role:m.role,content:m.content,ts:m.ts,react:m.react,name:m.name,cid:m.cid}));
async function gen(kind='reply',spk,cue){
 if(!cur?.id||!chat||ctl)return null;skipTyping();
 const last=hist.at(-1),sp=G?memberById(spk||last?.cid):cur;if(!sp)return null;
 const base=kind=='swipe'?hist.slice(0,-1):hist,lastU=[...base].reverse().find(m=>m.role=='user'),started=Date.now();
 pendWho=G?sp:null;ctl=new AbortController();busy(true);phase('reading…');
 const rt=setTimeout(()=>{if(pendLabel=='reading…')phase(S.role=='guest'?'waiting for the AI…':'typing…')},Math.min(1000,350+(lastU?lastU.content.split(' ').length*45:0)));
 const a=base.at(-1)?.ts,b=base.at(-2)?.ts;
 const gap=!U.timeaware?0:kind=='nudge'||kind=='continue'?(Date.now()-(a||Date.now()))/1000:(a&&b?(a-b)/1000:0);
 const s=chat.state,ms=G?{...mst(sp.id),summary:s.summary,log:undefined}:{...s,log:undefined},
  body={user:uname(),persona:U.persona,history:apiHist(base),turn:base.length,kind:kind=='swipe'?'reply':kind,
  from:U.track&&s.summary?Math.max(0,Math.min(s.sumUpto,base.length-2)):0,state:U.track?ms:{},scene:chat.cfg.scene,
  clock:U.timeaware?clock():'',gap_s:gap,rp:{on:U.rp!='off',state:chat.rp||{},fx:lastU?.fx||'',cfg:rpCfg()},
  params:{...P,think:U.think,actions:U.actions,mode:chat.cfg.mode,length:chat.cfg.length,realism:U.realism,natural:U.natural,pers:persCfg(),mem:memCfg()}};
 if(G){body.group=G.id;body.speaker=sp.id;body.cue=cue||{}}else body.char=apiChar();
 let res=null,err='';
 try{const r=await fetch('/api/chat',{method:'POST',signal:ctl.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r.status==401){location.reload();return null}
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  for(;;){const{done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
   while((i=buf.indexOf('\n\n'))>=0){const l=buf.slice(0,i);buf=buf.slice(i+2);if(!l.startsWith('data: ')||l.slice(6)=='[DONE]')continue;
    const j=JSON.parse(l.slice(6));if(j.q!=null)phase(j.q?`waiting in line (${j.q} ahead)…`:'waiting for the AI…');else if(j.p)phase(j.p=='think'?'thinking…':'typing…');else if(j.done)res=j.done;else if(j.err)err=j.err}}
 }catch(e){err=e.name=='AbortError'?'aborted':(e.message||'Connection lost')}
 clearTimeout(rt);const ab=ctl.signal.aborted;ctl=null;hidePending();pendWho=null;if(!rounding)busy(false);setStatus('online');
 if(ab){draw();return null}
 if(res&&res.pass)return 'pass';
 if(!res||!res.text){draw();errBox(err||'The model returned nothing.',G?'round':kind);return null}
 let idx;const v={content:res.text,think:res.think,ts:Date.now(),stat:{tok:res.tok,ms:res.ms},pers:res.pers,recalled:res.recalled};
 if(kind=='swipe'){restore(last);if(!last.sw)last.sw=[{content:last.content,think:last.think,ts:last.ts,stat:last.stat,thought:last.thought,pers:last.pers}];
  last.sw.push(v);last.si=last.sw.length-1;Object.assign(last,v,{thought:'',react:''});idx=hist.length-1}
 else if(kind=='continue'){last.content=last.content.trimEnd()+(chat.cfg.mode=='text'?'\n':'\n\n')+res.text;if(last.sw)last.sw[last.si].content=last.content;idx=hist.length-1}
 else{hist.push({role:'assistant',...v,seen:started,nudge:kind=='nudge'?1:undefined,...(G?{cid:sp.id,name:sp.name}:{})});idx=hist.length-1}
 $('#ctxm').textContent=(res.cut?'Reply hit the length cap and was trimmed to a full sentence. Use Continue for more. · ':'')+`prompt ${res.ctx_used.toLocaleString()} / ${res.ctx.toLocaleString()} tokens`+(res.recalled?.length?` · recalled ${res.recalled.length} ${res.recalled.length==1?'memory':'memories'}`:'')+(res.dropped?` · ${res.dropped} oldest messages left out`:'');
 saveChat();draw();beep();lastAct=Date.now();
 if(U.tts)speak(hist[idx].content);
 await typeMsg(idx);lastAct=Date.now();
 trackState(idx);return true}
async function post(t,forced,nofx){const m={role:'user',content:t,ts:Date.now()};hist.push(m);beep(520,.05);nudges=0;lastAct=Date.now();draw();
 if(U.rp!='off'&&!nofx){await resolveFx(m,forced);draw()}saveChat();G?await round():await gen('reply')}
async function send(){const t=$('#inp').value.trim();if(!t||ctl||rounding||!cur?.id||!chat)return;skipTyping();window.speechSynthesis?.cancel();
 $('#inp').value='';$('#inp').style.height='';hideMnu();
 if(t[0]=='/'){const r=slash(t);if(r)return post(r.text,r.forced,r.nofx)}
 const f=armed;armed=null;armUI();return post(t,f)}

/* ---------- inner state + long-term memory (runs after the reply, never delays it) ---------- */
async function trackState(i){
 if(!U.track||!S.loaded||!chat)return;const ch=chat,m=hist[i];if(!m)return;
 const sp=G?memberById(m.cid):cur;if(!sp||sp.id=='__narrator__')return;
 const stt=G?mst(sp.id):ch.state,{log,mem:memPrev,...rest}=stt,snap=JSON.stringify(rest);
 try{const r=await api('/api/track','POST',{char:apiChar(sp),user:uname(),history:apiHist(hist.slice(Math.max(0,i-5),i+1)),state:stt,group:G?G.id:undefined,pers:persCfg(),mem:memCfg(),turn:i+1,used:m.recalled||[]});
  if(r.err||!r.state||chat!==ch||hist[i]!==m)return;
  if(U.mem)m.mundo={add:r.mem_added||[],scene:memPrev?.scene||'',recent:memPrev?.recent||[]};
  m.snap=snap;if(G)m.snapc=sp.id;m.thought=r.thought||'';hist.forEach((x,k)=>{if(k<i-6){delete x.snap;delete x.snapc}});
  if(G)ch.state.members[sp.id]={...stt,...r.state};else ch.state={...ch.state,...r.state};
  head();redrawMsg(i);saveChat();if(!$('#mem').hidden)renderMem();maybeSummarize()}catch(e){}}
const SUM_EVERY=10,SUM_KEEP=4;   // auto-summarize every 10 new messages; the newest 4 stay word-for-word in the prompt
let sumBusy=false;
async function maybeSummarize(force){
 if((!force&&!U.track)||!S.loaded||!chat||sumBusy)return;const ch=chat,s=ch.state,upto=force?hist.length:hist.length-SUM_KEEP;
 if((!force&&upto-s.sumUpto<SUM_EVERY)||upto<=s.sumUpto)return;
 sumBusy=true;try{
 const r=await api('/api/summarize','POST',{char:apiChar(),user:uname(),group:G?G.id:undefined,history:apiHist(hist.slice(s.sumUpto,upto)),summary:s.summary});
 if(r.summary&&chat===ch){s.summary=r.summary;s.sumUpto=upto;saveChat();if(!$('#mem').hidden)renderMem()}return r}finally{sumBusy=false}}
