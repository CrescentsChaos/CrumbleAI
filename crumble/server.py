"""The HTTP server: pages, JSON API, streaming replies and guest access control."""
import hmac
import json
import re
import secrets
import shutil
import time
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from .config import CHARS, CHATS, EMO, EXT_KEYS, GROUPS, KEYS, LLM, LLM_VERBOSE, LOCK, MODELS, ROOT, SCHEMA, Llama, gpu_status
from . import personality, recall
from .llm import generate_reply
from .memory import memorize, summarize, track
from .rp.director import PACE, plan_next
from .rp.narrator import NARRATOR, NARR_ID
from .rp.ooc import OOC_CHAR, clean_notes
from .rp.resolve import rp_resolve
from .sharing import FAILS, FWD, LOCAL, MAX_BODY, MAX_QUEUE, MYIPS, QL, QUEUE, SESS, SHARE, lan_urls, save_share
from .storage import chat_list, cdir, get_char, get_group, group_members, load_chars, load_groups, pub, rj, wj
from .textutil import loose_json
from . import web


def state(a):
    adm = a["role"] == "admin"
    chars = load_chars() if adm else [pub(c) for c in load_chars()]
    loaded = LLM["path"] if adm else (Path(LLM["path"]).name if LLM["path"] else None)
    return {"schema": SCHEMA, "ext": EXT_KEYS, "chars": chars, "loaded": loaded, "backend": Llama is not None, "gpu": gpu_status()[0], "emo": EMO, "groups": load_groups(),
            "models": sorted(str(m) for m in MODELS.rglob("*.gguf")) if adm else [], "role": a["role"], "name": a.get("name", "")}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200, ctype="application/json", headers=()):
        b = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_BODY:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def sse(self, o):
        self.wfile.write(b"data: " + (o if isinstance(o, str) else json.dumps(o)).encode() + b"\n\n")
        self.wfile.flush()

    def auth(self):
        """admin = the host, on this PC, directly (a tunnel/proxy hop or odd Host header never counts as the host)."""
        host = (self.headers.get("Host") or "").strip()
        host = host.split("]")[0] + "]" if host.startswith("[") else host.rsplit(":", 1)[0]
        ip = self.client_address[0]  # opening your own shared link (http://192.168.x.x) on this PC still counts as the host
        if (ip in LOCAL or ip in MYIPS) and not any(self.headers.get(h) for h in FWD) and (host in ("localhost", "127.0.0.1", "[::1]") or host in MYIPS):
            return {"role": "admin", "uid": ""}
        if not SHARE["on"]:
            return {"role": None, "why": "off"}
        ck = SimpleCookie(self.headers.get("Cookie") or "")
        sid = ck["crumble_sid"].value if "crumble_sid" in ck else ""
        s = SESS.get(sid)
        if s:
            s["seen"] = time.time()
            return {"role": "guest", "uid": s["uid"], "name": s["name"], "sid": sid}
        return {"role": None, "why": "login"}

    def key(self, a, cid):
        """Guests get their own private chat folder per character; the host uses the plain one."""
        if a["role"] == "admin":
            return cid
        return f"{cid}_{a['uid']}" if (get_char(cid) or get_group(cid)) else None

    def deny(self, a, code=403):
        return self.send({"err": "login" if a.get("why") == "login" else "Not allowed"}, 401 if a.get("why") == "login" else code)

    def do_GET(self):
        a = self.auth()
        if self.path == "/":
            if a["role"]:
                return self.send(web.page_bytes(), ctype="text/html; charset=utf-8")
            if a.get("why") == "off":
                return self.send(b"The host is not sharing Crumble right now.", 403, "text/plain; charset=utf-8")
            return self.send(web.login_bytes(), ctype="text/html; charset=utf-8")
        if not a["role"]:
            return self.deny(a)
        if self.path == "/api/state":
            return self.send(state(a))
        if self.path == "/api/share":
            if a["role"] != "admin":
                return self.deny(a)
            return self.send({"on": SHARE["on"], "listen": SHARE["listen"], "password": SHARE["password"], "max": SHARE["max"],
                              "urls": lan_urls(SHARE["port"]), "queue": QUEUE["n"],
                              "guests": [{"uid": v["uid"], "name": v["name"], "seen": v["seen"], "busy": v.get("busy", False)} for v in SESS.values()]})
        m = re.match(r"/api/chats/(\w+)$", self.path)
        if m:
            k = self.key(a, m[1])
            return self.send({"chats": chat_list(k) if k else []})
        m = re.match(r"/api/chat/(\w+)/(\w+)$", self.path)
        if m:
            k = self.key(a, m[1])
            c = rj(CHATS/k/f"{m[2]}.json", {}) if k else {}
            return self.send({"history": c.get("history", []), "title": c.get("title", "New chat"),
                              "state": c.get("state"), "cfg": c.get("cfg"), "rp": c.get("rp")})
        self.send({"err": "not found"}, 404)

    def do_DELETE(self):
        a = self.auth()
        if not a["role"]:
            return self.deny(a)
        m = re.match(r"/api/chars/(\w+)$", self.path)
        if m:
            if a["role"] != "admin":
                return self.deny(a)
            for p in (CHARS/f"{m[1]}.json", CHATS/f"{m[1]}.json"):
                p.unlink(missing_ok=True)
            for d in CHATS.glob(m[1] + "_*"):
                if re.fullmatch(re.escape(m[1]) + r"_[0-9a-f]{8}", d.name):
                    shutil.rmtree(d, ignore_errors=True)
            shutil.rmtree(CHATS/m[1], ignore_errors=True)
        m = re.match(r"/api/groups/(\w+)$", self.path)
        if m:
            if a["role"] != "admin":
                return self.deny(a)
            (GROUPS/f"{m[1]}.json").unlink(missing_ok=True)
            for d in CHATS.glob(m[1] + "_*"):
                if re.fullmatch(re.escape(m[1]) + r"_[0-9a-f]{8}", d.name):
                    shutil.rmtree(d, ignore_errors=True)
            shutil.rmtree(CHATS/m[1], ignore_errors=True)
        m = re.match(r"/api/chat/(\w+)/(\w+)$", self.path)
        if m:
            k = self.key(a, m[1])
            if k:
                (CHATS/k/f"{m[2]}.json").unlink(missing_ok=True)
        self.send({"ok": True})

    def acquire(self):
        """Wait for the model; everyone shares one, so people queue up. Tells the page how many are ahead."""
        with QL:
            if QUEUE["n"] >= MAX_QUEUE:
                raise RuntimeError("The host's AI is very busy right now. Try again in a minute.")
            QUEUE["n"] += 1
        try:
            while not LOCK.acquire(timeout=1.0):
                self.sse({"q": max(0, QUEUE["n"] - 1)})
        except BaseException:
            with QL:
                QUEUE["n"] -= 1
            raise

    def release(self):
        LOCK.release()
        with QL:
            QUEUE["n"] -= 1

    def do_POST(self):
        a = self.auth()
        try:
            b = self.body()
        except Exception as e:
            return self.send({"err": str(e)}, 413)
        if self.path == "/api/login":
            return self.login(a, b)
        if not a["role"]:
            return self.deny(a)
        if self.path not in ("/api/chat", "/api/chat_save") and isinstance(b.get("history"), list):   # out-of-character talk is not part of the story the memory systems read
            b["history"] = [m for m in b["history"] if not (isinstance(m, dict) and m.get("ooc"))]
        adm, guest = a["role"] == "admin", a["role"] == "guest"
        if self.path in ("/api/load", "/api/chars", "/api/gen_char", "/api/share", "/api/groups", "/api/personality") and not adm:
            return self.deny(a)
        if self.path == "/api/share":
            return self.share(b)
        if self.path == "/api/load":
            if Llama is None:
                return self.send({"err": "llama-cpp-python is not installed (pip install llama-cpp-python)"})
            try:
                with LOCK:
                    LLM["obj"] = None
                    n_ctx = int(b.get("n_ctx", 8192))
                    # Ensure n_gpu is forced to -1 if it comes in as 0 or empty
                    gpu_layers = int(b.get("n_gpu", -1))
                    if gpu_layers == 0:
                        gpu_layers = -1
                        
                    LLM["obj"] = Llama(model_path=b["path"], n_ctx=n_ctx, n_gpu_layers=gpu_layers, verbose=LLM_VERBOSE)
                    LLM["path"], LLM["n_ctx"] = b["path"], n_ctx
                wj(ROOT/"data"/"last_model.json", {"path": b["path"], "n_ctx": n_ctx, "n_gpu": gpu_layers})
                return self.send({"ok": True, "loaded": b["path"]})
            except Exception as e:
                return self.send({"err": str(e)})
        if self.path == "/api/chars":
            c = {k: b.get(k, "") for k in KEYS}
            c["lore"], c["avatar"] = b.get("lore", []), b.get("avatar", "")
            c["id"] = re.sub(r"\W", "", str(b.get("id") or "")) or uuid.uuid4().hex[:8]
            wj(CHARS/f"{c['id']}.json", c)
            return self.send(c)
        if self.path == "/api/chat_save":
            cid, chid = self.key(a, str(b.get("cid", ""))), str(b.get("id", ""))
            if not (cid and re.fullmatch(r"\w+", cid) and re.fullmatch(r"\w+", chid)) or (guest and len(b.get("history", [])) > 3000):
                return self.send({"err": "bad id"}, 400)
            title = b.get("title") or "New chat"
            if title == "New chat":
                first = next((m["content"] for m in b["history"] if m["role"] == "user" and not m.get("ooc")), "").strip()
                if first:
                    title = first.replace("\n", " ")[:40]
            cdir(cid)
            wj(CHATS/cid/f"{chid}.json", {"id": chid, "title": title[:80], "updated": time.time(), "history": b["history"],
                                         "state": b.get("state"), "cfg": b.get("cfg"), "rp": b.get("rp")})
            return self.send({"title": title[:80]})
        if self.path == "/api/groups":
            gid = re.sub(r"\W", "", str(b.get("id") or "")) or "grp_" + uuid.uuid4().hex[:8]
            g = {"id": gid, "name": str(b.get("name") or "Group chat")[:60], "members": [str(i) for i in (b.get("members") or [])][:8],
                 "pace": b.get("pace") if b.get("pace") in PACE else "natural", "narrator": bool(b.get("narrator")),
                 "scenario": str(b.get("scenario") or "")[:4000]}
            wj(GROUPS/f"{gid}.json", g)
            return self.send(g)
        if self.path in ("/api/group_next", "/api/rp/resolve"):
            g = get_group(str(b.get("group"))) if b.get("group") else None
            if b.get("group") and not g:
                return self.send({"err": "Unknown group."})
            mem = group_members(g) if g else [c for c in [get_char(str(b.get("cid")))] if c]
            if not mem:
                return self.send({"err": "Unknown character."})
            try:
                if self.path == "/api/rp/resolve":
                    return self.send(rp_resolve(dict(b, members=mem)))
                hist = [dict(m, content=str(m.get("content", ""))[:4000]) for m in (b.get("history") or [])[-30:]]
                return self.send(plan_next(g, mem, hist, list(b.get("spoke") or []), int(b.get("cap") or 0), int(b.get("n") or 0),
                                           str(b.get("user") or "User"), b))
            except Exception as e:
                return self.send({"err": str(e)})
        if self.path == "/api/personality":   # host only: it is derived from the private sheet
            c = get_char(str(b.get("cid"))) if b.get("cid") else {k: str(v) for k, v in (b.get("char") or {}).items() if k in KEYS}
            if not c:
                return self.send({"err": "Unknown character."})
            return self.send(personality.public(personality.profile_for(c)))
        if self.path == "/api/recall":   # preview: what would the memory search put in the prompt for this message? (no model call)
            st_ = b.get("state") if isinstance(b.get("state"), dict) else {}
            name, user_ = str(b.get("name") or "Character")[:60], str(b.get("user") or "User")[:60]
            r = recall.select(st_, [{"role": "user", "content": str(b.get("query") or "")[:2000]}], user=user_, char=name,
                              cfg=recall.settings({"on": True, "depth": b.get("depth")}), turn=int(b.get("turn") or 0) or None)
            return self.send({"short": [recall.resolve(x, user_, name) for x in r["short"]], "q": r["q"],
                              "trace": [dict(t, text=recall.resolve(t["text"], user_, name)) for t in r["trace"]]})
        if self.path == "/api/gen_char":
            if not LLM["obj"]:
                return self.send({"err": "Load a model first."})
            ask = ("Invent a detailed roleplay character from this concept. Reply with ONLY a JSON object whose "
                   f"values are all plain strings, using exactly these keys: {', '.join(KEYS)}. "
                   "Write first_mes as the character's opening line in their own voice, and mes_example as a short "
                   "sample dialogue using {{char}} and {{user}}. Give catchphrases, vocab, texting and mood_speech real, "
                   "specific detail so the character sounds distinct. For traits give numbers 0-100 like 'O 60 C 45 E 80 A 30 N 55' "
                   "(openness, conscientiousness, extraversion, agreeableness, neuroticism) plus three or four adjectives; "
                   "for consistency give two or three short always/never rules. "
                   "Leave a key empty if unsure.\n\nConcept: " + b["concept"])
            try:
                with LOCK:
                    r = LLM["obj"].create_chat_completion(messages=[{"role": "user", "content": ask}],
                                                          temperature=.8, max_tokens=min(4000, LLM["n_ctx"] // 2))
                data = loose_json(r["choices"][0]["message"]["content"])
                return self.send({k: str(v) for k, v in data.items() if k in KEYS})
            except Exception as e:
                return self.send({"err": f"Model did not return usable JSON ({e}). Try again."})
        if self.path in ("/api/track", "/api/summarize", "/api/memorize"):
            if not LLM["obj"]:
                return self.send({"err": "No model loaded."})
            try:
                if guest:  # guests can never supply their own character sheet or prompt
                    cid_ = str((b.get("char") or {}).get("id"))
                    b["char"] = get_char(cid_) or ({"name": g_["name"]} if (g_ := get_group(cid_)) else {"name": "Character"})
                    b["history"] = [dict(m, content=str(m.get("content", ""))[:8000]) for m in b.get("history", [])[-60:]]
                return self.send(track(b) if self.path == "/api/track" else memorize(b) if self.path == "/api/memorize" else {"summary": summarize(b)})
            except Exception as e:
                return self.send({"err": str(e)})
        if self.path == "/api/chat":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            sess, got = SESS.get(a.get("sid")), False
            try:
                if not LLM["obj"]:
                    raise RuntimeError("The host has not loaded a model yet." if guest else "No model is loaded. Open the Model box in the sidebar, pick your .gguf and press Load model.")
                if guest:
                    if sess and sess.get("busy"):
                        raise RuntimeError("One reply at a time, please wait for the current one.")
                    if not b.get("group"):
                        c = get_char(str((b.get("char") or {}).get("id")))
                        if not c:
                            raise RuntimeError("Unknown character.")
                        b["char"] = c
                    if isinstance(b.get("ooc"), dict):
                        b["ooc"] = {"kind": b["ooc"].get("kind"), "notes": clean_notes(b["ooc"].get("notes"))}
                    if isinstance(b.get("rp"), dict):
                        b["rp"] = dict(b["rp"], fx=str(b["rp"].get("fx", ""))[:3500])
                    b["history"] = [dict(m, content=str(m.get("content", ""))[:8000]) for m in b.get("history", [])[-300:]]
                    b["params"] = dict(b.get("params") or {}, max_tokens=min(int((b.get("params") or {}).get("max_tokens", 512)), 1024))
                    sess["busy"] = True
                if b.get("group"):  # a group reply: the server loads the group and every sheet itself, for host and guests alike
                    g = get_group(str(b["group"]))
                    if not g:
                        raise RuntimeError("Unknown group.")
                    mem = group_members(g)
                    spk = str(b.get("speaker"))
                    c = OOC_CHAR if b.get("kind") == "ooc" else NARRATOR if spk == NARR_ID else next((m for m in mem if m["id"] == spk), None)
                    if not c:
                        raise RuntimeError("That character is not in this group.")
                    b["char"], b["grp"] = c, dict(name=g["name"], scenario=g.get("scenario", ""), members=mem, narrator=bool(g.get("narrator")))
                self.acquire()
                got = True
                res = generate_reply(b, self.sse)
                self.sse({"done": res})  # the whole reply is ready: only now does the page show any text
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as e:
                try:
                    self.sse({"err": str(e)})
                except Exception:
                    return
            finally:
                if got:
                    self.release()
                if sess:
                    sess["busy"] = False
            self.sse("[DONE]")
            return
        self.send({"err": "not found"}, 404)

    def login(self, a, b):
        ip = self.client_address[0]
        if a["role"] == "admin":
            return self.send({"ok": True})
        if not SHARE["on"]:
            return self.send({"err": "The host is not sharing right now."}, 403)
        n, until = FAILS.get(ip, (0, 0))
        if n >= 5 and time.time() < until:
            return self.send({"err": "Too many wrong passwords. Wait a minute."}, 429)
        pw = SHARE["password"]
        if pw and not hmac.compare_digest(str(b.get("password", "")).encode(), pw.encode()):
            FAILS[ip] = (n + 1, time.time() + 60)
            time.sleep(1)
            return self.send({"err": "Wrong password."}, 401)
        FAILS.pop(ip, None)
        if len(SESS) >= SHARE["max"]:
            return self.send({"err": "The host's room is full."}, 503)
        sid = secrets.token_urlsafe(24)
        SESS[sid] = {"uid": uuid.uuid4().hex[:8], "name": re.sub(r"[<>]", "", str(b.get("name") or "Guest")).strip()[:24] or "Guest",
                     "seen": time.time(), "busy": False}
        save_share()
        sec = "; Secure" if (self.headers.get("X-Forwarded-Proto") or "") == "https" else ""
        return self.send({"ok": True}, headers=[("Set-Cookie", f"crumble_sid={sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000{sec}")])

    def share(self, b):
        if "on" in b:
            if b["on"] and not SHARE["listen"]:
                return self.send({"err": "Restart Crumble with --share (or run Share.bat / share.sh) first."})
            SHARE["on"] = bool(b["on"])
            if SHARE["on"] and not SHARE["password"] and not b.get("open"):
                SHARE["password"] = secrets.token_urlsafe(6)
        if b.get("regen"):
            SHARE["password"] = secrets.token_urlsafe(6)
        elif "password" in b:
            SHARE["password"] = str(b["password"]).strip()[:64]
        if "max" in b:
            SHARE["max"] = max(1, min(100, int(b["max"])))
        if b.get("kick"):
            for k in [k for k, v in SESS.items() if b["kick"] == "all" or v["uid"] == b["kick"]]:
                del SESS[k]
        save_share()
        return self.send({"ok": True})
