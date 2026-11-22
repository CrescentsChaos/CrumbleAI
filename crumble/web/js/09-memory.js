/* ---------- memory tab: mood, relationship, scene, summary, facts ---------- */
function renderMemOne(){const f=$('#memf'),st=chat?.state;if(!chat||!st){f.innerHTML='<p class=small>Open a chat first.</p>';return}
 const n=esc(cur?.name||'Character'),moods=[...new Set([st.mood,...Object.keys(S.emo)])];
 f.innerHTML=`<details open><summary>Mood and relationship</summary>
  <label>Current mood and energy (the character updates this itself after each reply; you can override it)</label>
  <div class=row><select data-m=mood>${moods.map(m=>`<option ${m==st.mood?'selected':''}>${esc(m)}</option>`).join('')}</select>
  <select data-m=energy>${['low','medium','high'].map(m=>`<option ${m==st.energy?'selected':''}>${m}</option>`).join('')}</select></div>
  <label>How ${n} feels about you: <b id=mstage>${stg(st.affection)} (${st.affection})</b></label><input type=range min=0 max=100 value=${st.affection} data-m=affection>
  <div class=row><button class=x data-m=reset>Reset mood and relationship</button></div></details>
  <details open><summary>Scene note</summary><label>Steer the situation. It stays in every prompt for this chat.</label>
  <textarea data-m=scene rows=3 placeholder="e.g. It is raining and ${n} just got home from a double shift.">${esc(chat.cfg.scene||'')}</textarea></details>
  <details open><summary>Memory of earlier conversation</summary><label>Long chats are summarised automatically so ${n} remembers what happened. You can edit it.</label>
  <textarea data-m=summary rows=6>${esc(st.summary||'')}</textarea><div class=row><button data-m=sumnow>Summarize now</button><span class=small id=msum></span></div></details>
  ${U.mem?memHtml(st,cur?.name||'Character',''):`  <details open><summary>What ${n} knows about you</summary><div id=mfacts>${st.facts.map((x,i)=>`<div class=fact><input data-m=fact data-i=${i} value="${at(x)}"><button class=x data-m=delfact data-i=${i}>✕</button></div>`).join('')||'<p class=small>Nothing yet. Facts are picked up from the conversation.</p>'}</div>
  <div class=row><input id=newfact placeholder="Add a fact…"><button data-m=addfact>Add</button></div></details>`}
  <details><summary>Inner thoughts and mood history</summary>${(st.log||[]).slice(-12).reverse().map(l=>`<div class=tl>${l.emoji} <b>${esc(l.mood)}</b> · ${l.aff}/100 · ${hm(l.ts)}<br>${esc(l.thought||'')}</div>`).join('')||'<p class=small>Nothing yet.</p>'}</details>`}
$('#memf').oninput=e=>{const k=e.target.dataset.m,st=chat?.state;if(!k||!st)return;const v=e.target.value;
 if(k=='affection'){st.affection=+v;$('#mstage').textContent=`${stg(st.affection)} (${v})`}
 else if(k=='scene')chat.cfg.scene=v;else if(k=='summary')st.summary=v;else if(k=='fact')st.facts[+e.target.dataset.i]=v;
  else if(k=='gaff'){mst(e.target.dataset.c).affection=+v;e.target.previousElementSibling.querySelector('b').textContent=`${stg(+v)} (${v})`}
  else if(k=='rom'){const r=(chat.rp.rom=chat.rp.rom||{});(r[e.target.dataset.c]=r[e.target.dataset.c]||{v:0,ms:[]}).v=+v;e.target.previousElementSibling.querySelector('b').textContent=`${romStage(+v)} (${v})`}
  else if(k=='intim'){const r=(chat.rp.intim=chat.rp.intim||{});(r[e.target.dataset.c]=r[e.target.dataset.c]||{iv:0,acts:[]}).iv=+v;e.target.previousElementSibling.querySelector('b').textContent=`${intimStage(+v)} (${v})`}else return;head();saveSoon()};
$('#memf').onchange=e=>{const k=e.target.dataset.m,st=chat?.state;if(!st)return;
 if(k=='mood'){st.mood=e.target.value;st.emoji=S.emo[st.mood]||'🙂'}else if(k=='energy')st.energy=e.target.value;else return;head();saveSoon()};
$('#memf').onclick=async e=>{const b=e.target.closest('button'),k=b?.dataset.m,st=chat?.state;if(!k||!st)return;
 if(k=='reset'){Object.assign(st,{mood:'neutral',emoji:'😐',energy:'medium',affection:50,log:[]});if(st.pers)Object.assign(st.pers,{va:null,grudge:0,frac:0,mood:null})}
 else if(k=='delfact')st.facts.splice(+b.dataset.i,1);
 else if(k=='addfact'){const v=$('#newfact').value.trim();if(!v)return;st.facts.push(v)}
 else if(k=='rest'){if(!ctl&&!rounding)post('*rests for 8 hours to recover*','rest');return}
 else if(k=='revive'){if(!ctl&&!rounding){const c=(G?memberById(b.dataset.c):cur);post(`*${c?.name||'the fallen'} is brought back from the dead*`,'revive')}return}
 else if(k=='heal1'){const bd=chat.rp?.body?.[b.dataset.c];if(bd){bd.ko=false;(bd.inj||[]).forEach(i=>{i.care=true;if(i.k=='bleeding'){i.k='stabilised wound';i.s=3}});(bd.ill||[]).forEach(i=>i.care=true);bd.tired=Math.max(0,(bd.tired||0)-40)}}
 else if(k=='sumnow'){b.disabled=true;$('#msum').textContent='Summarizing…';try{const r=await maybeSummarize(true);$('#msum').textContent=r?.err||(r?.summary?'Done.':'No new chat messages to summarize.')}catch(e){$('#msum').textContent=e.message||'Could not summarize chat.'}finally{b.disabled=false}if(chat?.state?.summary)return}
 else return;head();saveSoon();renderMem()};
