"""The HTTP server: pages, JSON API, streaming replies and guest access control."""
import hmac
import json
import os
import re
import secrets
import shutil
import time
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from .config import CHARS, CHATS, EMO, EXT_KEYS, GROUPS, KEYS, LLM, LLM_VERBOSE, LOCK, MODELS, load_llama, ROOT, SCHEMA, Llama, gpu_status
from . import keeper, personality, places, presence, profile, recall
from .feel import peek as feel_peek
from .llm import generate_reply
from .memory import keep_update, memorize, summarize, summary_details, track
from .rp import circle
from .rp.director import PACE, plan_next
from .rp.narrator import NARRATOR, NARR_ID
from .rp.ooc import OOC_CHAR, clean_notes
from .rp.relations import public as rel_paths
from . import story
from .rp.resolve import rp_observe, rp_resolve
from .sharing import FAILS, FWD, LOCAL, MAX_BODY, MAX_QUEUE, MYIPS, QL, QUEUE, SESS, SHARE, lan_urls, save_share
from .storage import chat_list, cdir, get_char, get_group, group_members, load_chars, load_groups, pub, rj, wj
from .textutil import loose_json
from . import vault, web


def state(a):
    adm = a["role"] == "admin"
    chars = load_chars() if adm else [pub(c) for c in load_chars()]
    loaded = LLM["path"] if adm else (Path(LLM["path"]).name if LLM["path"] else None)
    return {"schema": SCHEMA, "ext": EXT_KEYS, "chars": chars, "loaded": loaded, "backend": Llama is not None, "gpu": gpu_status()[0], "emo": EMO, "rels": rel_paths(), "groups": load_groups(),
            "models": sorted(str(m) for m in MODELS.rglob("*.gguf")) if adm else [], "role": a["role"], "name": a.get("name", "")}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200, ctype="application/json", headers=()):
        b = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # The client may navigate away or time out while the request is being
            # processed. There is no useful error response to send on that socket.
            return

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
        m = re.fullmatch(r"/fonts/([\w.-]+\.woff2)", self.path.split("?")[0])
        if m:   # the bundled typefaces: plain static files, nothing private, cached by the browser for a year
            f = web.WEB / "fonts" / m.group(1)
            if f.is_file():
                return self.send(f.read_bytes(), ctype="font/woff2", headers=[("Cache-Control", "public, max-age=31536000, immutable")])
            return self.send({"err": "not found"}, 404)
        m = re.fullmatch(r"/animals/sprites/([a-z0-9_]+\.(?:png|webp|jpg|gif))", self.path.split("?")[0])
        if m:   # animal sprites (data/animals/sprites/american_black_bear.png ...): public pictures, nothing private
            f = ROOT / "data" / "animals" / "sprites" / m.group(1)
            if f.is_file():
                ext = f.suffix.lower()[1:]
                return self.send(f.read_bytes(), ctype="image/" + ("jpeg" if ext == "jpg" else ext), headers=[("Cache-Control", "public, max-age=3600")])
            return self.send({"err": "not found"}, 404)
        m = re.fullmatch(r"/(logo|favicon-32|icon-192|icon-512|apple-touch-icon)\.png|/(favicon)\.ico", self.path.split("?")[0])
        if m:   # the web icon: public static files from <project>/assets, also needed by the sign-in page
            name = m.group(1) + ".png" if m.group(1) else "favicon.ico"
            f = ROOT / "assets" / name
            if f.is_file():
                return self.send(f.read_bytes(), ctype="image/x-icon" if name.endswith(".ico") else "image/png", headers=[("Cache-Control", "public, max-age=86400")])
            return self.send({"err": "not found"}, 404)
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
        if self.path == "/api/profile":     # who you are (name, about you, stats, skills, gear): kept on the host so it follows you to any browser
            return self.send({"profile": profile.load(a)})
        if self.path == "/api/settings":    # the page's options (Settings tab and sampling): kept on the host so they follow you to any browser
            return self.send(profile.load_settings(a))
        if self.path == "/api/places":   # location cards: guests get the public view (no secrets, events or history)
            return self.send({"places": [places.view(p, a["role"] == "admin") for p in places.load_all()], "biomes": places.BIOMES})
        m = re.fullmatch(r"/places/img/([\w]+\.(?:png|jpg|webp|gif))", self.path.split("?")[0])
        if m:   # a place's background picture (only for people who are signed in)
            f = places.image_file(m.group(1))
            if f:
                ext = f.suffix.lower()[1:]
                return self.send(f.read_bytes(), ctype="image/" + ("jpeg" if ext == "jpg" else ext), headers=[("Cache-Control", "private, max-age=3600")])
            return self.send({"err": "not found"}, 404)
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
        m = re.match(r"/api/places/(\w+)$", self.path)
        if m:
            if a["role"] != "admin":
                return self.deny(a)
            places.remove(m[1])
            sid = places.scene_id(m[1])
            for d in CHATS.glob(sid + "_*"):
                if re.fullmatch(re.escape(sid) + r"_[0-9a-f]{8}", d.name):
                    shutil.rmtree(d, ignore_errors=True)
            shutil.rmtree(CHATS/sid, ignore_errors=True)
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
                f_ = CHATS/k/f"{m[2]}.json"
                if f_.exists():      # deleting a chat moves it (and its memory) to data/trash; nothing is destroyed
                    vault.TRASH.mkdir(parents=True, exist_ok=True)
                    os.replace(f_, vault.TRASH / f"{int(time.time())}-{k}-{m[2]}.json")
                    vault.retire(a.get("uid") or "host", m[2])
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
        if self.path in ("/api/load", "/api/chars", "/api/gen_char", "/api/share", "/api/groups", "/api/personality", "/api/places", "/api/gen_place") and not adm:
            return self.deny(a)
        if self.path == "/api/profile":
            return self.send({"profile": profile.save(a, b)})
        if self.path == "/api/settings":
            return self.send(profile.save_settings(a, b))
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
                        
                    LLM["obj"] = load_llama(b["path"], n_ctx, gpu_layers, LLM_VERBOSE)
                    LLM["path"], LLM["n_ctx"] = b["path"], n_ctx
                wj(ROOT/"data"/"last_model.json", {"path": b["path"], "n_ctx": n_ctx, "n_gpu": gpu_layers})
                return self.send({"ok": True, "loaded": b["path"]})
            except Exception as e:
                return self.send({"err": str(e)})
        if self.path == "/api/places":   # host only: create or change a location card (a picture comes as bg_data, bg_clear removes it)
            try:
                old = places.get(b.get("id")) if b.get("id") else None
                p = places.clean(b, old)
                if b.get("bg_data"):
                    p = places.save_image(p, b["bg_data"])
                elif b.get("bg_clear"):
                    p = places.clear_image(p)
                places.save(p)
                return self.send(places.view(p))
            except ValueError as e:
                return self.send({"err": str(e)})
        if self.path == "/api/places/visit":   # in a one-to-one chat: does someone from this place join in? (no model call, nothing saved)
            card = places.get((b.get("place") or {}).get("id")) if isinstance(b.get("place"), dict) else None
            main = get_char(str(b.get("cid"))) if b.get("cid") else None
            if not card or not main:
                return self.send({"visit": None})
            try:
                from . import simtime
                chars = {i: c for i in card["characters"] if (c := get_char(i))}
                hist = [dict(m, content=str(m.get("content", ""))[:4000]) for m in (b.get("history") or [])[-300:] if isinstance(m, dict) and not m.get("ooc")]
                full = (main.get("scenario") or "") + (" " + str(b.get("story_start") or "")[:80] if b.get("story_start") else "")
                sim = simtime.derive(hist, full, [{"kind": "setting", "text": str(b["scene"])}] if b.get("scene") else []) or simtime.from_clock(str(b.get("clock") or ""))
                scfg = story.settings(b.get("story"))
                v = places.visit(card, main["id"], chars, hist, int(b.get("turn") or len(hist)), str(b.get("text") or "")[:2000], str(b.get("setting") or "normal"),
                                 str(b.get("seed") or main["id"]), [str(x) for x in (b.get("dead") or [])], sim, str(b.get("force") or ""), scfg["routines"] and scfg["on"],
                                 int((b["place"] or {}).get("since") or 0))
                return self.send({"visit": v})
            except Exception as e:
                return self.send({"err": str(e)})
        if self.path == "/api/doing":   # who is here and what is everybody doing right now: one model call per stretch of story time (the page keeps the answer)
            try:
                if guest:
                    b["history"] = [dict(m, content=str(m.get("content", ""))[:4000]) for m in (b.get("history") or [])[-60:] if isinstance(m, dict)]
                return self.send(presence.run(b))
            except Exception as e:
                return self.send({"err": str(e)})
        if self.path == "/api/gen_place":   # host only: the loaded model drafts a whole card from a sentence
            if not LLM["obj"]:
                return self.send({"err": "Load a model first."})
            keys = list(places.TEXTS) + list(places.LISTS)
            ask = ("Invent a detailed roleplay location from this concept. Reply with ONLY a JSON object using exactly these keys: " + ", ".join(keys) +
                   ". name, biome (one or two words), description, atmosphere (sound, smell, light, temperature, mood) and history are plain strings; "
                   "objects, activities, exits, events and secrets are arrays of short strings (objects: things like 'the brass telescope'; activities: short verb phrases like 'fish off the pier'; "
                   "exits: names of nearby places; events: things that can happen here; secrets: hidden truths about the place). Be specific and vivid. Leave a key empty if unsure.\n\nConcept: " + str(b.get("concept") or "")[:1000])
            try:
                with LOCK:
                    r = LLM["obj"].create_chat_completion(messages=[{"role": "user", "content": ask}], temperature=.85, max_tokens=min(3000, LLM["n_ctx"] // 2))
                data = loose_json(r["choices"][0]["message"]["content"])
                d = places.clean({k: v for k, v in data.items() if k in keys and k != "id"})
                return self.send({k: d[k] for k in keys})
            except Exception as e:
                return self.send({"err": f"Model did not return usable JSON ({e}). Try again."})
        if self.path == "/api/chars":
            c = {k: b.get(k, "") for k in KEYS}
            c["lore"], c["avatar"] = b.get("lore", []), b.get("avatar", "")
            c["start_place"] = places.start_id(b.get("start_place"))      # the place card a new chat with this character begins in ("" = none)
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
            raw_cid = re.sub(r"\W", "", str(b.get("cid", "")))
            st_ = vault.protect_state(a.get("uid") or "host", chid, raw_cid, b.get("state"), len([m for m in b["history"] if not m.get("ooc")]))   # a stale or empty page cannot wipe the memory
            wj(CHATS/cid/f"{chid}.json", {"id": chid, "title": title[:80], "updated": time.time(), "history": b["history"],
                                         "state": st_, "cfg": b.get("cfg"), "rp": b.get("rp")})
            return self.send({"title": title[:80]})
        if self.path == "/api/groups":
            gid = re.sub(r"\W", "", str(b.get("id") or "")) or "grp_" + uuid.uuid4().hex[:8]
            if places.is_scene(gid):      # pl_<id> is a visit to a place, not a saved group
                gid = "grp_" + uuid.uuid4().hex[:8]
            g = {"id": gid, "name": str(b.get("name") or "Group chat")[:60], "members": [str(i) for i in (b.get("members") or [])][:8],
                 "pace": b.get("pace") if b.get("pace") in PACE else "natural", "narrator": bool(b.get("narrator")),
                 "scenario": str(b.get("scenario") or "")[:4000],
                 "auto": bool(b.get("auto")), "auto_max": max(2, min(20, int(b.get("auto_max") or 6))) if str(b.get("auto_max") or "6").lstrip("-").isdigit() else 6}
            wj(GROUPS/f"{gid}.json", g)
            return self.send(g)
        if self.path in ("/api/group_next", "/api/rp/resolve", "/api/rp/observe"):
            g = get_group(str(b.get("group"))) if b.get("group") else None
            if b.get("group") and not g:
                return self.send({"err": "Unknown group."})
            mem = group_members(g) if g else [c for c in [get_char(str(b.get("cid")))] if c]
            if g and places.is_scene(g["id"]):      # a visit: only the people who are in the place right now count
                mem = places.only_present(mem, b.get("present") if isinstance(b.get("present"), list) else None)
            if not mem:
                return self.send({"err": "Unknown character."})
            try:
                if self.path == "/api/rp/resolve":
                    return self.send(rp_resolve(dict(b, members=mem)))
                if self.path == "/api/rp/observe":
                    return self.send(rp_observe(dict(b, members=mem)))
                gone = {str(i) for i in (b.get("dead") or [])}      # the dead never speak: they are not even considered
                mem = [c for c in mem if c["id"] not in gone]
                if not mem:
                    return self.send({"next": None, "why": "dead", "by": str(b.get("user") or "User"), "cap": 0, "pass": False})
                hist = [dict(m, content=str(m.get("content", ""))[:4000]) for m in (b.get("history") or [])[-30:]]
                return self.send(plan_next(g, mem, hist, list(b.get("spoke") or []), int(b.get("cap") or 0), int(b.get("n") or 0),
                                           str(b.get("user") or "User"), b))
            except Exception as e:
                return self.send({"err": str(e)})
        if self.path in ("/api/circle", "/api/circle/observe"):    # how the characters of a group feel about each other (no model call, nothing saved here)
            g = get_group(str(b.get("group"))) if b.get("group") else None
            mem = [m for m in (group_members(g) if g else []) if m]
            if g and places.is_scene(g["id"]):
                mem = places.only_present(mem, b.get("present") if isinstance(b.get("present"), list) else None)
            if not mem:
                return self.send({"err": "Unknown group."})
            try:
                user = str(b.get("user") or "User")[:60]
                aff = {str(k): v for k, v in (b.get("aff") or {}).items()} if isinstance(b.get("aff"), dict) else {}
                rom = {str(k): v for k, v in (b.get("rom") or {}).items()} if isinstance(b.get("rom"), dict) else {}
                notes = []
                cir = circle.seed(mem, b.get("circle"))
                if self.path == "/api/circle/observe":
                    text = str(b.get("text") or "")[:4000]
                    if b.get("from") == "user":
                        cir, notes = circle.observe_user(cir, mem, text, user, aff, rom)
                    else:
                        cir, notes = circle.observe(cir, mem, str(b.get("speaker") or ""), text, user, str(b.get("prev") or "") or None, aff, rom)
                return self.send(dict(circle.view(mem, cir, user, aff), notes=notes))
            except Exception as e:
                return self.send({"err": str(e)})
        if self.path == "/api/world":   # the story clock, weather and everyone's place in their day (no model call, nothing saved)
            g = get_group(str(b.get("group"))) if b.get("group") else None
            mem = [m for m in (group_members(g) if g else [get_char(str(b.get("cid")))]) if m]
            if not mem:
                return self.send({"err": "Unknown character."})
            try:
                hist = [dict(m, content=str(m.get("content", ""))[:4000]) for m in (b.get("history") or [])[-300:] if isinstance(m, dict) and not m.get("ooc")]
                return self.send({"world": story.overview(mem, hist, str((g or mem[0]).get("scenario") or ""), b.get("story"), str(b.get("clock") or ""),
                                                          str(b.get("story_start") or "")[:80], notes=([{"kind": "setting", "text": str(b["scene"])}] if b.get("scene") else []),
                                                          seed=((g or {}).get("name") or mem[0].get("name") or ""),
                                                          loc=places.context(b.get("place"), len(hist)), doing=story.doing_mod.clean_map(b.get("doing")))})
            except Exception as e:
                return self.send({"err": str(e)})
        if self.path == "/api/feel":   # instant, provisional reaction to the message just sent (no model call, nothing saved)
            out = {}
            for cid in [str(x) for x in (b.get("cids") or [])][:8]:
                c = get_char(cid)
                if c:
                    out[cid] = feel_peek(c, (b.get("states") or {}).get(cid) or {}, str(b.get("text") or "")[:2000])
            return self.send({"feel": out})
        if self.path == "/api/personality":   # host only: it is derived from the private sheet
            c = get_char(str(b.get("cid"))) if b.get("cid") else {k: str(v) for k, v in (b.get("char") or {}).items() if k in KEYS}
            if not c:
                return self.send({"err": "Unknown character."})
            return self.send(personality.public(personality.profile_for(c)))
        if self.path == "/api/vault":     # status / roll back this chat's memory: {chat_id, char_id, restore?: backup number}
            vk = vault.key(a.get("uid") or "host", b.get("chat_id"), b.get("char_id"))
            if b.get("restore"):
                return self.send({"restored": vault.restore_backup(vk, int(b["restore"])), "backups": vault.backups(vk)})
            v_ = vault.load(vk) or {}
            return self.send({"items": len(((v_.get("mem") or {}).get("items") or [])), "rev": (v_.get("mem") or {}).get("rev"), "backups": vault.backups(vk)})
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
                if self.path == "/api/summarize" and isinstance(b.get("place"), dict):     # the summary remembers which place the story stands in
                    card_ = places.get(b["place"].get("id"))
                    b["place_name"] = card_["name"] if card_ else ""
                if self.path == "/api/track":
                    res_ = track(b)
                    cid_v, chat_v = str((b.get("char") or {}).get("id") or ""), str(b.get("chat_id") or "")
                    if chat_v and cid_v and isinstance(res_.get("state"), dict):
                        vk = vault.key(a.get("uid") or "host", chat_v, cid_v)
                        vault.restore_into(vk, res_["state"], int(b.get("turn") or 0) or None)
                        sv = res_["state"]
                        vault.save(vk, mem=sv.get("mem"), chron=sv.get("chron"), keep=(b.get("state") or {}).get("keep"))
                    return self.send(res_)
                return self.send(memorize(b) if self.path == "/api/memorize" else {"summary": summarize(b), "chron_add": summary_details(b), "keep": keep_update(b)})
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
                b["past"] = self.past_chats(a, b) if (b.get("params") or {}).get("past") and not b.get("group") and b.get("kind") != "ooc" else []
                if not b.get("group"):      # a one-to-one chat with visitors from a place becomes a small group for the prompt (everyone labelled)
                    places.stage(b, get_char)
                if b.get("group"):  # a group reply: the server loads the group and every sheet itself, for host and guests alike
                    g = get_group(str(b["group"]))
                    if not g:
                        raise RuntimeError("Unknown group.")
                    mem = group_members(g)
                    if places.is_scene(g["id"]):
                        mem = places.only_present(mem, b.get("present") if isinstance(b.get("present"), list) else None)
                    spk = str(b.get("speaker"))
                    c = OOC_CHAR if b.get("kind") == "ooc" else NARRATOR if spk == NARR_ID else next((m for m in mem if m["id"] == spk), None)
                    if not c:
                        raise RuntimeError("That character is not in this group.")
                    b["char"], b["grp"] = c, dict(name=g["name"], scenario=g.get("scenario", ""), members=mem, narrator=bool(g.get("narrator")))
                if b.get("chat_id") and (b.get("char") or {}).get("id"):
                    b["_vault"] = vault.key(a.get("uid") or "host", b["chat_id"], b["char"]["id"])
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

    def past_chats(self, a, b):
        """Earlier conversations with this character, boiled down (the page can switch this off, or mark one chat as a fresh start)."""
        try:
            cid = str((b.get("char") or {}).get("id") or "")
            chid = str(b.get("chat_id") or "")
            k = self.key(a, cid) if cid else None
            if not k or not re.fullmatch(r"\w+", k):
                return []
            out = []
            for f in sorted((CHATS/k).glob("*.json"), key=lambda f: -f.stat().st_mtime)[:8]:
                if f.stem == chid:
                    continue
                ch = rj(f)
                if not isinstance(ch, dict) or (ch.get("cfg") or {}).get("fresh"):
                    continue
                d = keeper.digest(ch, str(b.get("user") or "User"), (b.get("char") or {}).get("name") or "Character")
                if d:
                    out.append(d)
            return out[:4]
        except Exception:
            return []

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
