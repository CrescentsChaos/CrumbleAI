#!/usr/bin/env python3
"""
Hearth - a local character-chat helper for .gguf models (SillyTavern-style).

Setup:   pip install llama-cpp-python
         (GPU: CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir)
Run:     python hearth.py            then open http://127.0.0.1:8000
Models:  drop .gguf files in ./models, or paste a full path in the UI.
Data:    ./data/characters/*.json, ./data/chats/*.json
"""
import argparse, json, re, shutil, threading, time, uuid, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

ROOT = Path(__file__).resolve().parent
CHARS, CHATS, MODELS = ROOT/"data"/"characters", ROOT/"data"/"chats", ROOT/"models"
for d in (CHARS, CHATS, MODELS):
    d.mkdir(parents=True, exist_ok=True)
LLM = {"obj": None, "path": None}
LOCK = threading.Lock()

# (section, [(key, label, rows)]) - the editor and the prompt builder both read this.
SCHEMA = [
    ("Core", [("name", "Name", 1), ("description", "Description", 5),
              ("personality", "Personality", 3), ("scenario", "Scenario", 3)]),
    ("Identity", [("age", "Age", 1), ("gender", "Gender / pronouns", 1), ("species", "Species / race", 1),
                  ("occupation", "Occupation", 1), ("skills", "Skills & abilities", 2)]),
    ("Look and voice", [("appearance", "Appearance", 3), ("speech", "Speech style", 3), ("quirks", "Habits & quirks", 2)]),
    ("Mind and history", [("backstory", "Backstory", 5), ("likes", "Likes", 2), ("dislikes", "Dislikes", 2),
                          ("goals", "Goals", 2), ("fears", "Fears", 2),
                          ("relationships", "Relationships", 3), ("secrets", "Secrets", 3)]),
    ("Chat setup", [("first_mes", "First message", 4), ("alts", "Alternate greetings (separate with a line of ---)", 4),
                    ("mes_example", "Example dialogue", 6), ("system_prompt", "System prompt override", 3),
                    ("post_history", "Reminder placed after the chat history", 2),
                    ("tags", "Tags (comma separated)", 1), ("notes", "Creator notes", 2)]),
]
KEYS = [k for _, fs in SCHEMA for k, _, _ in fs]


def rj(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def wj(p, obj):
    Path(p).write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def cdir(cid):
    d = CHATS/cid
    d.mkdir(parents=True, exist_ok=True)
    old = CHATS/f"{cid}.json"
    if old.exists():  # migrate the single-chat file from the first version
        wj(d/"main.json", {"id": "main", "title": "Chat 1", "updated": old.stat().st_mtime, "history": rj(old, [])})
        old.unlink()
    return d


def chat_list(cid):
    out = []
    for f in cdir(cid).glob("*.json"):
        c = rj(f)
        if c:
            out.append({"id": c["id"], "title": c.get("title") or "New chat",
                        "updated": c.get("updated", 0), "n": len(c.get("history", []))})
    return sorted(out, key=lambda x: -x["updated"])


def state():
    chars = [c for c in (rj(f) for f in sorted(CHARS.glob("*.json"))) if c]
    models = sorted(str(m) for m in MODELS.rglob("*.gguf"))
    return {"schema": SCHEMA, "chars": chars, "models": models, "loaded": LLM["path"], "backend": Llama is not None}


def sub(t, c, u):
    return (t or "").replace("{{char}}", c.get("name") or "Character").replace("{{user}}", u)


def build_messages(c, user, hist, fold=False):
    n = c.get("name") or "Character"
    out = [c.get("system_prompt") or
           "Write {{char}}'s next reply in a roleplay chat with {{user}}. Stay in character and never speak or act for {{user}}."]
    for sec, fs in SCHEMA[:4]:
        lines = [f"{l}: {c[k].strip()}" for k, l, _ in fs if (c.get(k) or "").strip()]
        if lines:
            out.append(f"[{n} - {sec}]\n" + "\n".join(lines))
    if (c.get("mes_example") or "").strip():
        out.append("[Example dialogue]\n" + c["mes_example"].strip())
    recent = " ".join(m["content"] for m in hist[-6:]).lower()
    lore = []
    for e in c.get("lore", []):
        keys = [k.strip().lower() for k in (e.get("keys") or "").split(",") if k.strip()]
        if (e.get("content") or "").strip() and (not keys or any(k in recent for k in keys)):
            lore.append(e["content"].strip())
    if lore:
        out.append("[World info]\n" + "\n".join(lore))
    msgs = [dict(m) for m in hist]
    if fold and msgs and msgs[0]["role"] == "assistant":
        out.append(f"[{n}'s opening message]\n{msgs.pop(0)['content']}")
    if (c.get("post_history") or "").strip():
        out.append(c["post_history"].strip())
    return [{"role": "system", "content": sub("\n\n".join(out), c, user)}] + \
           [{"role": m["role"], "content": sub(m["content"], c, user)} for m in msgs]


def sampler(p):
    return dict(temperature=float(p.get("temperature", .8)), top_p=float(p.get("top_p", .95)),
                top_k=int(p.get("top_k", 40)), min_p=float(p.get("min_p", .05)),
                repeat_penalty=float(p.get("repeat_penalty", 1.1)), max_tokens=int(p.get("max_tokens", 512)))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200, ctype="application/json"):
        b = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

    def sse(self, o):
        self.wfile.write(b"data: " + (o if isinstance(o, str) else json.dumps(o)).encode() + b"\n\n")
        self.wfile.flush()

    def do_GET(self):
        if self.path == "/":
            return self.send(PAGE.encode(), ctype="text/html; charset=utf-8")
        if self.path == "/api/state":
            return self.send(state())
        m = re.match(r"/api/chats/(\w+)$", self.path)
        if m:
            return self.send({"chats": chat_list(m[1])})
        m = re.match(r"/api/chat/(\w+)/(\w+)$", self.path)
        if m:
            c = rj(cdir(m[1])/f"{m[2]}.json", {})
            return self.send({"history": c.get("history", []), "title": c.get("title", "New chat")})
        self.send({"err": "not found"}, 404)

    def do_DELETE(self):
        m = re.match(r"/api/chars/(\w+)$", self.path)
        if m:
            for p in (CHARS/f"{m[1]}.json", CHATS/f"{m[1]}.json"):
                p.unlink(missing_ok=True)
            shutil.rmtree(CHATS/m[1], ignore_errors=True)
        m = re.match(r"/api/chat/(\w+)/(\w+)$", self.path)
        if m:
            (CHATS/m[1]/f"{m[2]}.json").unlink(missing_ok=True)
        self.send({"ok": True})

    def do_POST(self):
        b = self.body()
        if self.path == "/api/load":
            if Llama is None:
                return self.send({"err": "llama-cpp-python is not installed (pip install llama-cpp-python)"})
            try:
                with LOCK:
                    LLM["obj"] = None
                    LLM["obj"] = Llama(model_path=b["path"], n_ctx=int(b.get("n_ctx", 8192)),
                                       n_gpu_layers=int(b.get("n_gpu", -1)), verbose=False)
                    LLM["path"] = b["path"]
                return self.send({"ok": True, "loaded": b["path"]})
            except Exception as e:
                return self.send({"err": str(e)})
        if self.path == "/api/chars":
            c = {k: b.get(k, "") for k in KEYS}
            c["lore"] = b.get("lore", [])
            c["id"] = b.get("id") or uuid.uuid4().hex[:8]
            wj(CHARS/f"{c['id']}.json", c)
            return self.send(c)
        if self.path == "/api/chat_save":
            cid, chid = str(b.get("cid", "")), str(b.get("id", ""))
            if not (re.fullmatch(r"\w+", cid) and re.fullmatch(r"\w+", chid)):
                return self.send({"err": "bad id"}, 400)
            title = b.get("title") or "New chat"
            if title == "New chat":
                first = next((m["content"] for m in b["history"] if m["role"] == "user"), "").strip()
                if first:
                    title = first.replace("\n", " ")[:40]
            wj(cdir(cid)/f"{chid}.json", {"id": chid, "title": title, "updated": time.time(), "history": b["history"]})
            return self.send({"title": title})
        if self.path == "/api/gen_char":
            if not LLM["obj"]:
                return self.send({"err": "Load a model first."})
            ask = ("Invent a detailed roleplay character from this concept. Reply with ONLY a JSON object whose "
                   f"values are all plain strings, using exactly these keys: {', '.join(KEYS)}. "
                   "Write first_mes as the character's opening line in their own voice, and mes_example as a short "
                   "sample dialogue using {{char}} and {{user}}. Leave a key empty if unsure.\n\nConcept: " + b["concept"])
            try:
                with LOCK:
                    r = LLM["obj"].create_chat_completion(messages=[{"role": "user", "content": ask}],
                                                          temperature=.8, max_tokens=2000)
                txt = r["choices"][0]["message"]["content"]
                data = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
                return self.send({k: str(v) for k, v in data.items() if k in KEYS})
            except Exception as e:
                return self.send({"err": f"Model did not return valid JSON ({e}). Try again."})
        if self.path == "/api/chat":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                if not LLM["obj"]:
                    raise RuntimeError("No model loaded.")
                msgs = build_messages(b["char"], b["user"], b["history"], b["params"].get("fold", False))
                with LOCK:
                    for ch in LLM["obj"].create_chat_completion(messages=msgs, stream=True, **sampler(b["params"])):
                        t = ch["choices"][0]["delta"].get("content")
                        if t:
                            self.sse({"t": t})
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as e:
                self.sse({"err": str(e)})
            self.sse("[DONE]")
            return
        self.send({"err": "not found"}, 404)


PAGE = r"""<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Hearth</title><style>
:root{--bg:#18222c;--pn:#223140;--pn2:#2b3d4f;--tx:#e9e5d8;--mu:#93a1ad;--ac:#6cc0ad;--bad:#d97070;--ln:#36495b}
*{box-sizing:border-box}body{margin:0;height:100vh;display:grid;grid-template-columns:290px 1fr;background:var(--bg);color:var(--tx);font:14px/1.45 system-ui,sans-serif}
aside{background:var(--pn);padding:14px;overflow:auto;border-right:1px solid var(--ln)}
main{display:flex;flex-direction:column;min-width:0;height:100vh}
h2{font:600 13px system-ui;color:var(--mu);margin:16px 0 6px}h1{font:700 22px Georgia,serif;margin:0}
input,select,textarea,button{font:inherit;color:var(--tx);background:var(--bg);border:1px solid var(--ln);border-radius:6px;padding:6px 8px;width:100%}
textarea{resize:vertical}button{width:auto;cursor:pointer;background:var(--pn2)}button:hover{border-color:var(--ac)}button.go{background:var(--ac);color:#10201b;border-color:var(--ac);font-weight:600}
button.x{color:var(--bad)}:focus-visible{outline:2px solid var(--ac);outline-offset:1px}
.row{display:flex;gap:6px;margin:4px 0;align-items:center}.row>*{flex:1}.row>button{flex:none}
.ch{padding:7px 9px;border-radius:6px;cursor:pointer}.ch:hover{background:var(--pn2)}.ch.on{background:var(--pn2);border-left:3px solid var(--ac)}
.small{color:var(--mu);font-size:12px}nav{display:flex;gap:4px;padding:10px 16px 0;border-bottom:1px solid var(--ln)}
nav button{border:0;border-radius:6px 6px 0 0;background:none;color:var(--mu)}nav button.on{background:var(--pn);color:var(--tx);border-bottom:2px solid var(--ac)}
section{flex:1;overflow:auto;padding:16px;min-height:0}#chat{display:flex;flex-direction:column;padding:0}#log{flex:1;overflow:auto;padding:16px}
.m{max-width:760px;margin:0 auto 14px;font:16px/1.6 Georgia,serif}.m b{font:600 12px system-ui;color:var(--ac);display:block}.m.user b{color:var(--mu)}.m span{white-space:pre-wrap}
.bar{border-top:1px solid var(--ln);padding:10px 16px;background:var(--pn)}.bar .row{max-width:760px;margin:4px auto}
details{background:var(--pn);border:1px solid var(--ln);border-radius:8px;margin:0 0 10px;padding:8px 12px;max-width:820px}summary{cursor:pointer;font-weight:600}
label{display:block;margin:8px 0 3px;color:var(--mu);font-size:12px}.lore{background:var(--bg);padding:8px;border-radius:6px;margin:6px 0}
.sampler{max-width:420px}[hidden]{display:none!important}
@media(max-width:700px){body{grid-template-columns:1fr;height:auto}main{height:90vh}}
</style>
<aside><h1>Hearth</h1>
<h2>Model (.gguf)</h2><select id=msel></select>
<input id=mpath placeholder="or paste a full path to a .gguf" style="margin-top:6px">
<div class=row><input id=nctx type=number value=8192 title="Context length"><input id=ngl type=number value=-1 title="GPU layers (-1 = all)"></div>
<div class=small>context length / GPU layers</div>
<div class=row><button class=go id=load>Load model</button></div><div id=mstat class=small></div>
<h2>Characters</h2><div class=row><button id=new>New</button><button id=imp>Import</button></div>
<input type=file id=file accept=".json,.png" hidden><div id=clist></div>
<h2>Your name</h2><input id=uname value=User></aside>
<main><nav><button data-t=chat class=on>Chat</button><button data-t=editor>Character editor</button><button data-t=samp>Sampler</button></nav>
<section id=chat><div class=row id=chatbar style="padding:8px 16px;margin:0;border-bottom:1px solid var(--ln)"><select id=chsel></select><button id=newchat>New chat</button><button id=rename>Rename</button><button id=delchat class=x>Delete chat</button></div><div id=log></div><div class=bar>
<div class=row><textarea id=inp rows=2 placeholder="Write a message. Enter sends, Shift+Enter adds a line."></textarea><button class=go id=send>Send</button><button id=stop hidden>Stop</button></div>
<div class=row style="flex-wrap:wrap"><button id=regen>Regenerate</button><button id=undo>Undo</button><button id=greet>Next greeting</button></div></div></section>
<section id=editor hidden><details open><summary>AI draft</summary><label>Describe the character in a sentence or two. Only empty fields get filled.</label>
<textarea id=concept rows=2></textarea><div class=row><button id=gen>Draft with loaded model</button><span class=small id=gstat></span></div></details>
<div id=form></div>
<div class=row style="max-width:820px"><button class=go id=save>Save character</button><button id=exp>Export card (JSON)</button><button class=x id=del>Delete</button></div></section>
<section id=samp hidden><div class=sampler id=sform></div></section></main>
<script>
const $=s=>document.querySelector(s),esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const P={temperature:.8,top_p:.95,top_k:40,min_p:.05,repeat_penalty:1.1,max_tokens:512,fold:false};
let S,cur=null,hist=[],ctl=null;
const api=(u,m='GET',b)=>fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined}).then(r=>r.json());
const blank=()=>({id:'',lore:[],...Object.fromEntries(S.schema.flatMap(([,f])=>f.map(x=>[x[0],''])))});
const greetings=c=>[c.first_mes,...(c.alts||'').split(/\n-{3,}\n/)].map(s=>s.trim()).filter(Boolean);

async function init(){S=await api('/api/state');
 $('#msel').innerHTML='<option value="">(choose from ./models)</option>'+S.models.map(m=>`<option>${esc(m)}</option>`).join('');
 $('#mstat').textContent=S.backend?(S.loaded?'Loaded: '+S.loaded:'No model loaded'):'llama-cpp-python missing: pip install llama-cpp-python';
 renderChars();renderSampler();if(!cur)S.chars[0]?await pick(S.chars[0].id):openNew();}
function renderChars(){$('#clist').innerHTML=S.chars.map(c=>`<div class="ch ${cur&&cur.id==c.id?'on':''}" data-id=${c.id}>${esc(c.name||'(unnamed)')}</div>`).join('')}
$('#clist').onclick=e=>{const d=e.target.closest('.ch');if(d)pick(d.dataset.id)};
let chat=null,chats=[];const rid=()=>Math.random().toString(36).slice(2,10);
async function pick(id){cur=S.chars.find(c=>c.id==id);renderChars();renderForm(cur);
 chats=(await api('/api/chats/'+id)).chats||[];chats.length?await openChat(chats[0].id):await newChat()}
async function openChat(chid){const r=await api(`/api/chat/${cur.id}/${chid}`);chat={id:chid,title:r.title};hist=r.history;gi=0;drawChats();draw()}
async function newChat(){chat={id:rid(),title:'New chat'};gi=0;resetChat();await saveChat();draw()}
async function saveChat(){if(!cur?.id||!chat)return;const r=await api('/api/chat_save','POST',{cid:cur.id,id:chat.id,title:chat.title,history:hist});
 if(r.err)return;chat.title=r.title;const m={id:chat.id,title:chat.title,n:hist.length},i=chats.findIndex(c=>c.id==chat.id);i<0?chats.unshift(m):chats[i]=m;drawChats()}
function drawChats(){$('#chsel').innerHTML=chats.map(c=>`<option value=${c.id} ${chat&&c.id==chat.id?'selected':''}>${esc(c.title)} (${c.n})</option>`).join('')}
function resetChat(i=0){const g=greetings(cur);hist=g.length?[{role:'assistant',content:g[i%g.length]}]:[]}
function draw(){const u=$('#uname').value||'User';$('#log').innerHTML=hist.map(m=>`<div class="m ${m.role}"><b>${esc(m.role=='user'?u:(cur?.name||'Character'))}</b><span>${esc(m.content)}</span></div>`).join('');
 $('#log').scrollTop=1e9}
const busy=b=>{$('#send').hidden=b;$('#stop').hidden=!b};
async function gen(){if(!cur||!cur.id||!chat)return;const out=hist.push({role:'assistant',content:''})-1;draw();
 ctl=new AbortController();busy(true);const el=()=>$('#log').lastElementChild.querySelector('span');
 try{const r=await fetch('/api/chat',{method:'POST',signal:ctl.signal,headers:{'Content-Type':'application/json'},
  body:JSON.stringify({char:cur,user:$('#uname').value||'User',history:hist.slice(0,out),params:P})});
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  for(;;){const{done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
   while((i=buf.indexOf('\n\n'))>=0){const l=buf.slice(0,i);buf=buf.slice(i+2);if(!l.startsWith('data: ')||l.slice(6)=='[DONE]')continue;
    const j=JSON.parse(l.slice(6));hist[out].content+=j.t??('\n[error: '+j.err+']');el().textContent=hist[out].content;$('#log').scrollTop=1e9}}
 }catch(e){}
 busy(false);ctl=null;saveChat()}
async function send(){const t=$('#inp').value.trim();if(!t||ctl)return;$('#inp').value='';hist.push({role:'user',content:t});await gen()}
$('#send').onclick=send;$('#stop').onclick=()=>ctl&&ctl.abort();
$('#inp').onkeydown=e=>{if(e.key=='Enter'&&!e.shiftKey){e.preventDefault();send()}};
$('#regen').onclick=()=>{if(ctl||!hist.length)return;if(hist.length>1&&hist.at(-1).role=='assistant')hist.pop();gen()};
$('#undo').onclick=()=>{if(ctl)return;hist.pop();draw();saveChat()};
let gi=0;$('#greet').onclick=()=>{if(ctl||hist.length>1)return;resetChat(++gi);draw();saveChat()};
$('#chsel').onchange=e=>{if(!ctl)openChat(e.target.value)};
$('#newchat').onclick=()=>{if(!ctl&&cur?.id)newChat()};
$('#rename').onclick=()=>{if(!chat)return;const t=prompt('Chat name',chat.title);if(t&&t.trim()){chat.title=t.trim();saveChat()}};
$('#delchat').onclick=async()=>{if(ctl||!chat||!confirm('Delete this chat?'))return;await api(`/api/chat/${cur.id}/${chat.id}`,'DELETE');
 chats=chats.filter(c=>c.id!=chat.id);chats.length?await openChat(chats[0].id):await newChat()};
$('#uname').oninput=()=>cur&&draw();

function renderForm(c){let h='';for(const[sec,fs]of S.schema){h+=`<details ${sec=='Core'?'open':''}><summary>${sec}</summary>`;
 for(const[k,l,r]of fs)h+=`<label>${l}</label><textarea data-k=${k} rows=${r}>${esc(c[k]||'')}</textarea>`;h+='</details>'}
 h+=`<details><summary>Lorebook (inserted when a key appears in the last few messages; no keys = always)</summary><div id=lore></div><button id=addlore>Add entry</button></details>`;
 $('#form').innerHTML=h;$('#lore').innerHTML='';(c.lore||[]).forEach(loreRow);$('#addlore').onclick=()=>loreRow({keys:'',content:''})}
function loreRow(e){const d=document.createElement('div');d.className='lore';
 d.innerHTML=`<input placeholder="keys, comma separated" value="${esc(e.keys||'').replace(/"/g,'&quot;')}"><textarea rows=3 placeholder="Entry text">${esc(e.content||'')}</textarea><button class=x>Remove</button>`;
 d.querySelector('button').onclick=()=>d.remove();$('#lore').append(d)}
function collect(){const c={id:cur?.id||''};document.querySelectorAll('[data-k]').forEach(e=>c[e.dataset.k]=e.value);
 c.lore=[...document.querySelectorAll('.lore')].map(d=>({keys:d.children[0].value,content:d.children[1].value}));return c}
function openNew(){cur=blank();hist=[];chat=null;chats=[];drawChats();draw();renderForm(cur);renderChars();tab('editor')}
$('#new').onclick=openNew;
$('#save').onclick=async()=>{const c=await api('/api/chars','POST',collect());const i=S.chars.findIndex(x=>x.id==c.id);
 i<0?S.chars.push(c):S.chars[i]=c;const was=cur.id;cur=c;renderChars();if(!was){chats=[];await newChat()}else draw();tab('chat')};
$('#del').onclick=async()=>{if(!cur?.id||!confirm('Delete '+cur.name+' and its chat?'))return;await api('/api/chars/'+cur.id,'DELETE');
 S.chars=S.chars.filter(c=>c.id!=cur.id);cur=null;S.chars[0]?pick(S.chars[0].id):openNew()};
$('#gen').onclick=async()=>{const concept=$('#concept').value.trim();if(!concept)return;$('#gstat').textContent='Drafting...';
 const r=await api('/api/gen_char','POST',{concept});if(r.err){$('#gstat').textContent=r.err;return}
 document.querySelectorAll('[data-k]').forEach(e=>{if(!e.value.trim()&&r[e.dataset.k])e.value=r[e.dataset.k]});$('#gstat').textContent='Done. Review the fields, then save.'};

// Character card import/export (Tavern card V2: JSON, or PNG with a 'chara' text chunk)
const unb64=s=>new TextDecoder().decode(Uint8Array.from(atob(s),c=>c.charCodeAt(0)));
async function pngCard(buf){const v=new DataView(buf);let o=8;while(o<buf.byteLength){const n=v.getUint32(o),t=String.fromCharCode(...new Uint8Array(buf,o+4,4));
 if(t=='tEXt'){const d=new Uint8Array(buf,o+8,n),z=d.indexOf(0);if(new TextDecoder().decode(d.slice(0,z))=='chara')return JSON.parse(unb64(new TextDecoder().decode(d.slice(z+1))))}o+=12+n}throw Error('No character data in this PNG')}
$('#imp').onclick=()=>$('#file').click();
$('#file').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;
 try{const j=f.name.toLowerCase().endsWith('.png')?await pngCard(await f.arrayBuffer()):JSON.parse(await f.text());const d=j.data||j,x=d.extensions?.hearth||{},c=blank();
  Object.assign(c,x);c.name=d.name||'';c.description=d.description||'';c.personality=d.personality||'';c.scenario=d.scenario||'';c.first_mes=d.first_mes||'';
  c.mes_example=d.mes_example||'';c.system_prompt=d.system_prompt||'';c.post_history=d.post_history_instructions||'';c.notes=d.creator_notes||'';
  c.alts=(d.alternate_greetings||[]).join('\n---\n');c.tags=(d.tags||[]).join(', ');
  c.lore=(d.character_book?.entries||[]).map(e=>({keys:(e.keys||[]).join(', '),content:e.content||''}));
  cur=c;hist=[];chat=null;chats=[];drawChats();renderForm(c);tab('editor')}catch(err){alert('Import failed: '+err.message)}};
$('#exp').onclick=()=>{const c=collect(),ex={};['age','gender','species','occupation','skills','appearance','speech','quirks','backstory','likes','dislikes','goals','fears','relationships','secrets'].forEach(k=>ex[k]=c[k]);
 const card={spec:'chara_card_v2',spec_version:'2.0',data:{name:c.name,description:c.description,personality:c.personality,scenario:c.scenario,first_mes:c.first_mes,
  mes_example:c.mes_example,system_prompt:c.system_prompt,post_history_instructions:c.post_history,creator_notes:c.notes,
  alternate_greetings:(c.alts||'').split(/\n-{3,}\n/).map(s=>s.trim()).filter(Boolean),tags:(c.tags||'').split(',').map(s=>s.trim()).filter(Boolean),
  character_book:{entries:c.lore.map((e,i)=>({id:i,keys:e.keys.split(',').map(s=>s.trim()).filter(Boolean),content:e.content,enabled:true,insertion_order:i}))},
  extensions:{hearth:ex}}};
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(card,null,1)],{type:'application/json'}));a.download=(c.name||'character')+'.json';a.click()};

function renderSampler(){$('#sform').innerHTML=Object.entries(P).map(([k,v])=>typeof v=='boolean'?
 `<label><input type=checkbox data-p=${k} style="width:auto" ${v?'checked':''}> Fold the greeting into the system prompt (for models whose template rejects an assistant-first chat)</label>`:
 `<label>${k}</label><input type=number step=any data-p=${k} value=${v}>`).join('');
 $('#sform').oninput=e=>{const k=e.target.dataset.p;if(k)P[k]=e.target.type=='checkbox'?e.target.checked:+e.target.value}}
$('#load').onclick=async()=>{const path=$('#mpath').value.trim()||$('#msel').value;if(!path)return;$('#mstat').textContent='Loading (this can take a while)...';
 const r=await api('/api/load','POST',{path,n_ctx:$('#nctx').value,n_gpu:$('#ngl').value});$('#mstat').textContent=r.err?'Error: '+r.err:'Loaded: '+r.loaded};
function tab(t){document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.t==t));
 for(const id of['chat','editor','samp'])$('#'+id).hidden=id!=t}
document.querySelector('nav').onclick=e=>e.target.dataset.t&&tab(e.target.dataset.t);
init();
</script></html>"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    url = f"http://{a.host}:{a.port}"
    print(f"Hearth running at {url}  (models in {MODELS})")
    threading.Timer(.8, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()
