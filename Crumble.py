#!/usr/bin/env python3
"""
Crumble - a local character-chat helper for .gguf models (SillyTavern-style).

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


THINK = re.compile(r"^.*?</think>|<think>.*?(?:</think>|$)", re.S)


def build_messages(c, user, hist, fold=False, think=True, actions=True):
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
    msgs = [dict(m, content=THINK.sub("", m["content"]).strip()) if m["role"] == "assistant" else dict(m) for m in hist]
    if fold and msgs and msgs[0]["role"] == "assistant":
        out.append(f"[{n}'s opening message]\n{msgs.pop(0)['content']}")
    out.append("[Style]\n" + ("Write actions, gestures and narration between *asterisks*. Spoken words are plain text."
               if actions else "Reply with spoken dialogue only. No narration, no actions, no asterisks."))
    if (c.get("post_history") or "").strip():
        out.append(c["post_history"].strip())
    if not think:
        out.append("/no_think")
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
                msgs = build_messages(b["char"], b["user"], b["history"], b["params"].get("fold", False),
                                      b["params"].get("think", True), b["params"].get("actions", True))
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
<title>Crumble</title><style>
:root{--bg:#0a0c10;--pn:#10131a;--pn2:#171b24;--pn3:#1f2430;--tx:#eceef4;--mu:#8b93a7;--ac:#f0b26b;--ac2:#e5806a;--bad:#ef7676;--ln:rgba(255,255,255,.08)}
*{box-sizing:border-box}
body{margin:0;height:100vh;display:grid;grid-template-columns:292px 1fr;color:var(--tx);font:14px/1.5 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased;
background:radial-gradient(900px 520px at 88% -10%,rgba(240,178,107,.10),transparent 60%),radial-gradient(700px 500px at -10% 110%,rgba(229,128,106,.08),transparent 60%),var(--bg)}
::-webkit-scrollbar{width:10px}::-webkit-scrollbar-thumb{background:var(--pn3);border-radius:10px;border:3px solid transparent;background-clip:content-box}
aside{background:rgba(16,19,26,.85);backdrop-filter:blur(14px);padding:18px 14px;overflow:auto;border-right:1px solid var(--ln)}
main{display:flex;flex-direction:column;min-width:0;height:100vh}
.brand{display:flex;align-items:center;gap:10px;margin:0 4px 18px}.logo{width:34px;height:34px;border-radius:11px;background:linear-gradient(135deg,var(--ac),var(--ac2));display:grid;place-items:center;font-size:18px;box-shadow:0 6px 20px -6px var(--ac2)}
h1{font:700 20px Inter,system-ui;letter-spacing:-.02em;margin:0}
h2{font:600 11px Inter,system-ui;letter-spacing:.09em;text-transform:uppercase;color:var(--mu);margin:20px 4px 8px}
input,select,textarea,button{font:inherit;color:var(--tx);background:var(--pn2);border:1px solid var(--ln);border-radius:12px;padding:8px 11px;width:100%;transition:border-color .15s,background .15s,transform .1s}
textarea{resize:vertical}button{width:auto;cursor:pointer}button:hover{border-color:rgba(240,178,107,.5);background:var(--pn3)}button:active{transform:scale(.97)}
button.go{background:linear-gradient(135deg,var(--ac),var(--ac2));color:#1b1209;border:0;font-weight:650}button.go:hover{filter:brightness(1.08)}
button.x{color:var(--bad)}:focus-visible{outline:2px solid var(--ac);outline-offset:1px}
.row{display:flex;gap:6px;margin:4px 0;align-items:center}.row>*{flex:1}.row>button{flex:none}.sp{flex:1}
.small{color:var(--mu);font-size:12px}
.ch{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:12px;cursor:pointer;border:1px solid transparent;transition:background .15s}.ch:hover{background:var(--pn2)}.ch.on{background:var(--pn2);border-color:var(--ln)}
.av{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font-weight:700;color:#17110a;flex:none}.av.sm{width:30px;height:30px;font-size:13px}
details.mdl{background:var(--pn2);border:1px solid var(--ln);border-radius:12px;padding:8px 12px}details.mdl summary{cursor:pointer;font-weight:600}
nav{display:flex;gap:4px;padding:6px;margin:14px auto 0;background:var(--pn);border:1px solid var(--ln);border-radius:14px}
nav button{border:0;border-radius:10px;background:none;color:var(--mu);padding:6px 16px}nav button.on{background:var(--pn3);color:var(--tx)}
section{flex:1;overflow:auto;padding:20px;min-height:0}#chat{display:flex;flex-direction:column;padding:0}
.chead{display:flex;align-items:center;gap:12px;padding:14px 22px;border-bottom:1px solid var(--ln)}.chead select{width:auto;max-width:200px}
.who b{display:block;font-size:15px}.who small{color:var(--mu);font-size:12px}.who small.on{color:var(--ac)}.who small:before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:#58d68d;margin-right:6px}.who small.on:before{background:var(--ac);animation:pl 1s infinite}
.ib{padding:7px 10px;line-height:1}
#log{flex:1;overflow:auto;padding:28px 20px 10px;overflow-anchor:none}
.m{display:flex;gap:12px;max-width:800px;margin:0 auto 20px}.m.fresh{animation:in .35s cubic-bezier(.2,.8,.2,1)}.m.user{flex-direction:row-reverse}
.bub{max-width:82%;min-width:0}.nm{font:600 12px Inter,system-ui;color:var(--mu);margin:0 6px 5px}.m.user .nm{text-align:right}
.tx{padding:12px 16px;border-radius:4px 20px 20px 20px;background:var(--pn2);border:1px solid var(--ln);font-size:15px;line-height:1.65;white-space:pre-wrap;overflow-wrap:anywhere;box-shadow:0 8px 28px -14px #000}
.m.user .tx{border-radius:20px 4px 20px 20px;background:linear-gradient(135deg,rgba(240,178,107,.22),rgba(229,128,106,.15));border-color:rgba(240,178,107,.3)}
.act{color:var(--ac);font-style:italic}.q{color:#fff}.tx strong{font-weight:650}
.dots{display:flex;gap:5px;align-items:center;color:var(--mu);font-size:13px}.dots i{width:7px;height:7px;border-radius:50%;background:var(--ac);animation:bn 1.2s infinite}.dots i:nth-child(2){animation-delay:.15s}.dots i:nth-child(3){animation-delay:.3s}.dots span{margin-left:6px}
.think{margin:0 0 8px;background:rgba(255,255,255,.03);border:1px solid var(--ln);border-radius:14px;padding:7px 13px;font-size:13px;color:var(--mu)}
.think summary{cursor:pointer;font-weight:600;list-style:none}.think summary:before{content:"✦ ";color:var(--ac)}.think.live summary{animation:pl 1.4s infinite}
.think div{white-space:pre-wrap;margin-top:8px;max-height:240px;overflow:auto;line-height:1.55}
.bar{padding:10px 20px 18px}.comp{max-width:800px;margin:0 auto;display:flex;gap:8px;align-items:flex-end;background:var(--pn2);border:1px solid var(--ln);border-radius:24px;padding:8px 8px 8px 20px;box-shadow:0 14px 44px -18px #000;transition:border-color .2s}
.comp:focus-within{border-color:rgba(240,178,107,.55)}.comp textarea{border:0;background:none;resize:none;max-height:170px;padding:9px 0;outline:0}
#send,#stop{width:42px;height:42px;border-radius:50%;padding:0;font-size:18px;flex:none}
.tools{max-width:800px;margin:10px auto 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.pill{border-radius:99px;padding:5px 13px;font-size:12.5px;color:var(--mu);background:var(--pn)}.pill.on{color:#1b1209;background:linear-gradient(135deg,var(--ac),var(--ac2));border-color:transparent;font-weight:600}
.ghost{border:0;background:none;color:var(--mu);font-size:12.5px;padding:5px 8px}
details:not(.think):not(.mdl){background:var(--pn);border:1px solid var(--ln);border-radius:16px;margin:0 0 12px;padding:10px 16px;max-width:840px}summary{cursor:pointer;font-weight:600}
label{display:block;margin:10px 0 4px;color:var(--mu);font-size:12px}.lore{background:var(--bg);padding:10px;border-radius:12px;margin:8px 0}
.sampler{max-width:440px}[hidden]{display:none!important}
@keyframes in{from{opacity:0;transform:translateY(8px)}}@keyframes bn{0%,60%,100%{transform:translateY(0);opacity:.4}30%{transform:translateY(-5px);opacity:1}}@keyframes pl{50%{opacity:.45}}
@media(max-width:700px){body{grid-template-columns:1fr;height:auto}main{height:90vh}.bub{max-width:90%}}
</style>
<aside><div class=brand><div class=logo>🍪</div><h1>Crumble</h1></div>
<h2>Characters</h2><div class=row><button id=new>＋ New</button><button id=imp>Import</button></div>
<input type=file id=file accept=".json,.png" hidden><div id=clist></div>
<h2>Model</h2><details class=mdl><summary>Load a .gguf</summary><select id=msel style="margin-top:8px"></select>
<input id=mpath placeholder="or paste a full path" style="margin-top:6px">
<div class=row><input id=nctx type=number value=8192 title="Context length"><input id=ngl type=number value=-1 title="GPU layers (-1 = all)"></div>
<div class=small>context length / GPU layers</div><div class=row><button class=go id=load>Load model</button></div></details><div id=mstat class=small style="margin:8px 4px"></div>
<h2>Your name</h2><input id=uname value=User></aside>
<main><nav><button data-t=chat class=on>Chat</button><button data-t=editor>Character</button><button data-t=samp>Sampler</button></nav>
<section id=chat><div class=chead><div class=av id=hav></div><div class=who><b id=hname>Character</b><small id=hstat>online</small></div><div class=sp></div>
<select id=chsel></select><button id=newchat class=ib title="New chat">＋</button><button id=rename class=ib title=Rename>✎</button><button id=delchat class="ib x" title="Delete chat">🗑</button></div>
<div id=log></div><div class=bar><div class=comp><textarea id=inp rows=1 placeholder="Message… (Enter sends, Shift+Enter adds a line)"></textarea>
<button class=go id=send title=Send>↑</button><button id=stop hidden title=Stop>■</button></div>
<div class=tools><button class=pill id=tthink title="Let the model think before replying (shows a collapsible panel)">✦ Thinking</button><button class=pill id=tact title="Actions in *stars*: styled when on, hidden when off">✱ Actions</button><span class=sp></span>
<button class=ghost id=regen>↻ Regenerate</button><button class=ghost id=undo>↶ Undo</button><button class=ghost id=greet>Next greeting</button></div></div></section>
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
function renderChars(){$('#clist').innerHTML=S.chars.map(c=>`<div class="ch ${cur&&cur.id==c.id?'on':''}" data-id=${c.id}><div class="av sm" style="${avs(c.name)}">${ini(c.name)}</div><span>${esc(c.name||'(unnamed)')}</span></div>`).join('')}
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
const U={think:true,actions:true};try{Object.assign(U,JSON.parse(localStorage.crumbleUI||'{}'))}catch(e){}
const hue=n=>[...(n||'?')].reduce((a,c)=>a*31+c.charCodeAt(0)>>>0,7)%360,
 avs=n=>`background:linear-gradient(135deg,hsl(${hue(n)} 75% 68%),hsl(${(hue(n)+40)%360} 70% 58%))`,ini=n=>esc((n||'?').trim()[0]||'?').toUpperCase();
function pills(){$('#tthink').classList.toggle('on',U.think);$('#tact').classList.toggle('on',U.actions);try{localStorage.crumbleUI=JSON.stringify(U)}catch(e){}}
$('#tthink').onclick=()=>{U.think=!U.think;pills();draw()};$('#tact').onclick=()=>{U.actions=!U.actions;pills();draw()};pills();
function split(t){if(!t.includes('<think>')&&t.includes('</think>'))t='<think>'+t;let th='',open=false;
 const body=t.replace(/<think>([\s\S]*?)(<\/think>|$)/g,(m,x,c)=>{th+=x;if(!c)open=true;return''});return{th:th.trim(),open,body:body.trim()}}
function fmt(t){t=esc(t).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>');
 const act=x=>U.actions?`<em class=act>${x}</em>`:'';
 t=t.replace(/\*([^*\n]+)\*/g,(m,x)=>act(x)).replace(/\(([^()\n]{3,})\)/g,(m,x)=>act('('+x+')'));
 return t.replace(/(&quot;|"|“)([^"“”\n]+)(&quot;|"|”)/g,'<span class=q>$1$2$3</span>').replace(/[ \t]{2,}/g,' ').trim()}
function msgHTML(m,live){const u=m.role=='user',n=u?($('#uname').value||'User'):(cur?.name||'Character');
 if(u)return`<div class="m user"><div class=bub><div class=nm>${esc(n)}</div><div class=tx>${esc(m.content)}</div></div></div>`;
 const s=split(m.content),think=U.think&&s.th?`<details class="think ${live&&s.open?'live':''}"><summary>${live&&s.open?'Thinking…':'Thought process'}</summary><div>${esc(s.th)}</div></details>`:'',
 body=fmt(s.body);
 return`<div class="m assistant"><div class=av style="${avs(n)}">${ini(n)}</div><div class=bub><div class=nm>${esc(n)}</div>${think}${body?`<div class=tx>${body}</div>`:live?'<div class=tx><div class=dots><i></i><i></i><i></i><span>typing…</span></div></div>':''}</div></div>`}
function head(){const n=cur?.name||'Character';$('#hname').textContent=n;$('#hav').style.cssText=avs(n);$('#hav').textContent=ini(n);
 $('#hstat').textContent=ctl?'typing…':'online';$('#hstat').classList.toggle('on',!!ctl)}
function draw(anim=0){head();$('#log').innerHTML=hist.map((m,i)=>msgHTML(m,!!ctl&&i==hist.length-1).replace('class="m ',i>=hist.length-anim?'class="m fresh ':'class="m ')).join('');$('#log').scrollTop=1e9}
function paint(){const L=$('#log'),near=L.scrollHeight-L.scrollTop-L.clientHeight<140,last=L.lastElementChild,
 old=last.querySelector('.think div'),ot=old?old.scrollTop:0,pin=old?old.scrollHeight-old.scrollTop-old.clientHeight<30:false,was=last.querySelector('details')?.open,
 t=document.createElement('div');t.innerHTML=msgHTML(hist.at(-1),true);const n=t.firstElementChild;
 if(was)n.querySelector('details')?.setAttribute('open','');
 last.innerHTML=n.innerHTML;  // patch in place: no new node, so no animation restart / flicker
 const nd=last.querySelector('.think div');if(nd)nd.scrollTop=pin?1e9:ot;
 if(near)L.scrollTop=L.scrollHeight}
const busy=b=>{$('#send').hidden=b;$('#stop').hidden=!b;head()};
async function gen(){if(!cur||!cur.id||!chat)return;const out=hist.push({role:'assistant',content:''})-1;ctl=new AbortController();busy(true);draw(2);
 try{const r=await fetch('/api/chat',{method:'POST',signal:ctl.signal,headers:{'Content-Type':'application/json'},
  body:JSON.stringify({char:cur,user:$('#uname').value||'User',history:hist.slice(0,out),params:{...P,think:U.think,actions:U.actions}})});
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  for(;;){const{done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
   while((i=buf.indexOf('\n\n'))>=0){const l=buf.slice(0,i);buf=buf.slice(i+2);if(!l.startsWith('data: ')||l.slice(6)=='[DONE]')continue;
    const j=JSON.parse(l.slice(6));hist[out].content+=j.t??('\n[error: '+j.err+']');paint()}}
 }catch(e){}
 ctl=null;busy(false);draw();saveChat()}
$('#inp').oninput=e=>{e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,170)+'px'};
async function send(){const t=$('#inp').value.trim();if(!t||ctl)return;$('#inp').value='';$('#inp').style.height='';hist.push({role:'user',content:t});await gen()}
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
    print(f"Crumble running at {url}  (models in {MODELS})")
    threading.Timer(.8, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()
