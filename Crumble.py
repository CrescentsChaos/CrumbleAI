#!/usr/bin/env python3
"""
Crumble - a local character-chat helper for .gguf models (SillyTavern-style).

Setup:   pip install llama-cpp-python
         (GPU: CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir)
Run:     python Crumble.py            then open http://127.0.0.1:8000
Models:  drop .gguf files in ./models, or paste a full path in the UI.
Data:    ./data/characters/*.json, ./data/chats/<character>/*.json

Replies are generated in full first (you see "typing..."), then typed out like a person.
Every reply is checked so it never ends mid-sentence or with a dangling *action* or "quote".
"""
import os
# Let a CUDA build of llama-cpp-python find the CUDA DLLs (any installed toolkit, or CUDA_PATH).
if hasattr(os, "add_dll_directory"):
    _cuda_dirs = []
    if os.environ.get("CUDA_PATH"):
        _cuda_dirs.append(os.path.join(os.environ["CUDA_PATH"], "bin"))
    _tk = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if os.path.isdir(_tk):
        _cuda_dirs += [os.path.join(_tk, v, "bin") for v in sorted(os.listdir(_tk), reverse=True)]
    for _d in _cuda_dirs:
        if os.path.isdir(_d):
            try:
                os.add_dll_directory(_d)
            except OSError:
                pass
import argparse, difflib, hmac, json, random, re, secrets, shutil, socket, threading, time, uuid, webbrowser
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None


def gpu_status():
    """(can this llama-cpp-python build use the GPU?, version). A pip-installed CPU build says False."""
    try:
        import llama_cpp
        fn = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        return (bool(fn()) if fn else False), getattr(llama_cpp, "__version__", "?")
    except Exception:
        return False, "?"


GPU_HELP = """
  ============================================================================
   WARNING: this llama-cpp-python is a CPU-ONLY build, so the model runs on the CPU
   (your GPU will stay idle no matter what "GPU layers" is set to).

   Reinstall it with CUDA support (Windows PowerShell, needs the CUDA Toolkit and
   Visual Studio Build Tools with "Desktop development with C++"):

       pip uninstall -y llama-cpp-python
       $env:CMAKE_ARGS = "-DGGML_CUDA=on"
       pip install llama-cpp-python --force-reinstall --no-cache-dir

   (cmd.exe:  set CMAKE_ARGS=-DGGML_CUDA=on   then the same pip install.)
   Then start Crumble again; this warning disappears when the GPU is usable.
  ============================================================================
"""

ROOT = Path(__file__).resolve().parent
CHARS, CHATS, MODELS = ROOT/"data"/"characters", ROOT/"data"/"chats", ROOT/"models"
for d in (CHARS, CHATS, MODELS):
    d.mkdir(parents=True, exist_ok=True)
LLM = {"obj": None, "path": None, "n_ctx": 8192}
LLM_VERBOSE = bool(os.environ.get("CRUMBLE_LLM_LOG"))   # set CRUMBLE_LLM_LOG=1 to see llama.cpp's own log (shows "offloaded N/N layers to GPU")
LOCK = threading.Lock()
CH, US = "{{char}}", "{{user}}"

# (section, [(key, label, rows)]) - the editor and the prompt builder both read this.
SCHEMA = [
    ("Core", [("name", "Name", 1), ("description", "Description", 5),
              ("personality", "Personality", 3), ("scenario", "Scenario", 3)]),
    ("Identity", [("age", "Age", 1), ("gender", "Gender / pronouns", 1), ("species", "Species / race", 1),
                  ("occupation", "Occupation", 1), ("skills", "Skills & abilities", 2),
                  ("knowledge", "What they know (and don't know)", 2)]),
    ("Look and voice", [("appearance", "Appearance", 3), ("speech", "Speech style", 3), ("quirks", "Habits & quirks", 2)]),
    ("Voice and manner", [("catchphrases", "Catchphrases & verbal tics", 2),
                          ("vocab", "Vocabulary, slang & swearing level", 2),
                          ("dialect", "Accent, dialect, languages mixed in", 2),
                          ("texting", "Texting habits (caps, emoji, punctuation, message length)", 2),
                          ("mood_speech", "How their speech changes when happy / angry / nervous / sad", 3),
                          ("body_language", "Body language & tells", 2), ("humor", "Sense of humour", 1)]),
    ("Mind and history", [("backstory", "Backstory", 5), ("likes", "Likes", 2), ("dislikes", "Dislikes", 2),
                          ("goals", "Goals", 2), ("fears", "Fears", 2),
                          ("relationships", "Relationships", 3), ("secrets", "Secrets", 3),
                          ("values", "Values & beliefs", 2), ("flaws", "Flaws & bad habits", 2),
                          ("triggers", "Triggers (what sets them off)", 2),
                          ("comfort", "What comforts or cheers them up", 2),
                          ("boundaries", "Boundaries & dealbreakers", 2)]),
    ("Chat setup", [("first_mes", "First message", 4), ("alts", "Alternate greetings (separate with a line of ---)", 4),
                    ("mes_example", "Example dialogue", 6), ("system_prompt", "System prompt override", 3),
                    ("post_history", "Reminder placed after the chat history", 2),
                    ("tags", "Tags (comma separated)", 1), ("notes", "Creator notes", 2)]),
]
KEYS = [k for _, fs in SCHEMA for k, _, _ in fs]
EXT_KEYS = [k for sec, fs in SCHEMA if sec not in ("Core", "Chat setup") for k, _, _ in fs]

EMO = {"neutral": "😐", "happy": "😊", "joyful": "😄", "excited": "🤩", "amused": "😄", "playful": "😏", "smug": "😏",
       "proud": "😎", "confident": "😎", "determined": "😤", "relaxed": "😌", "content": "😌", "calm": "😌",
       "affectionate": "🥰", "fond": "🥰", "grateful": "🙏", "hopeful": "🤞", "curious": "🤔", "thoughtful": "🤔",
       "skeptical": "🤨", "surprised": "😮", "confused": "😕", "flustered": "😳", "embarrassed": "😳", "shy": "😳",
       "nervous": "😬", "anxious": "😟", "worried": "😟", "sad": "😢", "lonely": "🥺", "hurt": "💔", "guilty": "😔",
       "tired": "😴", "sleepy": "😴", "bored": "🥱", "annoyed": "😒", "irritated": "😒", "frustrated": "😤",
       "angry": "😠", "furious": "🤬", "jealous": "😒", "disgusted": "🤢", "scared": "😨", "serious": "😐"}
STAGES = [(12, "hostile toward them"), (28, "cold and wary"), (42, "distant and guarded"),
          (58, "neutral, still getting to know them"), (72, "friendly and comfortable with them"),
          (86, "fond of them and close"), (101, "deeply attached and trusting")]
STOPW = set("the a an i you to and of it is in that for on with my your me we this be are was do have just so but not "
            "what its im dont no yes if or at as he she they them his her like".split())


def rj(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def wj(p, obj):
    Path(p).write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def slug(s):
    return re.sub(r"\W+", "_", s or "").strip("_").lower() or uuid.uuid4().hex[:8]


def from_card(j, stem):
    """A Tavern card V2 (as dropped straight into data/characters) -> Crumble's flat character format."""
    d = j.get("data") if isinstance(j.get("data"), dict) else j
    x = (d.get("extensions") or {}).get("hearth") or {}
    c = {k: "" for k in KEYS}
    c.update({k: str(v) for k, v in x.items() if k in KEYS})
    c.update(name=d.get("name") or stem, description=d.get("description", ""), personality=d.get("personality", ""),
             scenario=d.get("scenario", ""), first_mes=d.get("first_mes", ""), mes_example=d.get("mes_example", ""),
             system_prompt=d.get("system_prompt", ""), post_history=d.get("post_history_instructions", ""),
             notes=d.get("creator_notes", ""), alts="\n---\n".join(d.get("alternate_greetings") or []),
             tags=", ".join(d.get("tags") or []))
    c["lore"] = [{"keys": ", ".join(e.get("keys") or []), "content": e.get("content", "")}
                 for e in (d.get("character_book") or {}).get("entries", [])]
    c["avatar"] = x.get("avatar", "")
    c["id"] = slug(stem)
    return c


def load_chars():
    out = []
    for f in sorted(CHARS.glob("*.json")):
        j = rj(f)
        if not isinstance(j, dict):
            continue
        if not j.get("id") or isinstance(j.get("data"), dict):  # a raw card: convert it once, keep the original as .bak
            c = from_card(j, f.stem)
            if (CHARS/f"{c['id']}.json").exists() and (CHARS/f"{c['id']}.json") != f:
                c["id"] += "_" + uuid.uuid4().hex[:4]
            wj(CHARS/f"{c['id']}.json", c)
            if f.name != f"{c['id']}.json":
                f.replace(f.with_suffix(".json.bak"))
            j = c
        out.append(j)
    return out


def cdir(cid, make=True):
    d = CHATS/cid
    old = CHATS/f"{cid}.json"
    if make:
        d.mkdir(parents=True, exist_ok=True)
        if old.exists():  # migrate the single-chat file from the first version
            wj(d/"main.json", {"id": "main", "title": "Chat 1", "updated": old.stat().st_mtime, "history": rj(old, [])})
            old.unlink()
    return d


def chat_list(cid):
    if (CHATS/f"{cid}.json").exists():
        cdir(cid)
    out = []
    for f in (CHATS/cid).glob("*.json"):
        c = rj(f)
        if c:
            out.append({"id": c["id"], "title": c.get("title") or "New chat",
                        "updated": c.get("updated", 0), "n": len(c.get("history", []))})
    return sorted(out, key=lambda x: -x["updated"])


PUBLIC = ("name", "tags", "description", "first_mes", "alts", "gender", "age", "occupation")  # all a guest may see of a character


def pub(c):
    """A character as guests see it: enough to pick and greet, never the prompt, secrets or backstory."""
    out = {k: (c.get(k, "") if k in PUBLIC else "") for k in KEYS}
    out.update(id=c["id"], avatar=c.get("avatar", ""), lore=[])
    return out


def get_char(cid):
    return next((c for c in load_chars() if c["id"] == cid), None)


def state(a):
    adm = a["role"] == "admin"
    chars = load_chars() if adm else [pub(c) for c in load_chars()]
    loaded = LLM["path"] if adm else (Path(LLM["path"]).name if LLM["path"] else None)
    return {"schema": SCHEMA, "ext": EXT_KEYS, "chars": chars, "loaded": loaded, "backend": Llama is not None, "gpu": gpu_status()[0], "emo": EMO,
            "models": sorted(str(m) for m in MODELS.rglob("*.gguf")) if adm else [], "role": a["role"], "name": a.get("name", "")}


def sub(t, c, u):
    return (t or "").replace(CH, c.get("name") or "Character").replace(US, u)


# ---------------------------------------------------------------- text helpers
THINK = re.compile(r"^.*?</think>|<think>.*?(?:</think>|$)", re.S)


def split_think(t):
    """raw model text -> (thinking, visible body, thinking_never_closed)"""
    if "</think>" in t and "<think>" not in t:
        t = "<think>" + t
    th = "\n".join(x.strip() for x in re.findall(r"<think>(.*?)(?:</think>|$)", t, re.S))
    is_open = t.rfind("<think>") > t.rfind("</think>")
    return th.strip(), re.sub(r"<think>.*?(?:</think>|$)", "", t, flags=re.S).strip(), is_open


def trim_sentence(t):
    """Cut an unfinished reply back to its last complete sentence."""
    ends = list(re.finditer(r"[.!?…]+[\"'”’)\]*]*(?=\s|$)", t))
    if ends:
        return t[:ends[-1].end()].rstrip()
    return t.rstrip(" ,;:-—") + "…"


def _pair(t, o, c):
    """Balance one kind of paired marker (quotes, parentheses). Close it if the thought is finished, else drop the stub."""
    if o == c:
        bad = t.count(o) % 2
        i = t.rfind(o)
    else:
        bad = t.count(o) > t.count(c)
        i = t.rfind(o)
    if bad and i >= 0:
        tail = t[i + 1:].strip()
        t = t.rstrip() + c if tail and re.search(r"[.!?…,]$", tail) else t[:i].rstrip()
    return t


def balance(t):
    t = _pair(t, "*", "*")
    t = _pair(t, '"', '"')
    t = _pair(t, "“", "”")
    t = _pair(t, "(", ")")
    return t.strip()


def clean_body(body, user, name, mode):
    b = body.replace("\r", "")
    b = re.sub(r"^\s*\**" + re.escape(name) + r"\**\s*:\s*", "", b)
    m = re.search(r"(?im)^\s*\**" + re.escape(user) + r"\**\s*:", b)  # the model started writing the user's turn
    if m:
        b = b[:m.start()]
    b = re.sub(r"(?m)^\s*\[(?:Style|Realism|Right now|Format)[^\]]*\].*$", "", b)
    if mode != "story":  # no narration in texting / voice mode (short *emphasis* is kept)
        b = re.sub(r"\*+([^*\n]+)\*+", lambda m: m[0] if len(m[1].split()) < 3 else "", b)
        b = re.sub(r"(?m)^\s*[\"“](.*)[\"”]\s*$", r"\1", b)
    b = re.sub(r"[ \t]+\n", "\n", b)
    b = re.sub(r"\n{3,}", "\n\n", b)
    if mode == "text":
        b = "\n".join(l.strip() for l in b.split("\n") if l.strip())
    return b.strip()


def finish_reply(raw, finish, user, name, mode):
    th, body, think_open = split_think(raw)
    body = clean_body(body, user, name, mode)
    cut = False
    if finish == "length" and body:  # ran out of tokens: never leave half a sentence on screen
        cut = True
        lines = body.split("\n")
        body = "\n".join(lines[:-1]) if mode == "text" and len(lines) > 1 else trim_sentence(body)
    return {"think": th, "text": balance(body), "empty": not body.strip(), "cut": cut, "think_open": think_open}


def similar(t, prevs):
    a = re.sub(r"\W+", " ", t.lower()).strip()
    for p in prevs:
        b = re.sub(r"\W+", " ", p.lower()).strip()
        if a and b and difflib.SequenceMatcher(None, a, b).ratio() > .8:
            return True
    return False


def avoid_notes(hist):
    reps = [THINK.sub("", m["content"]) for m in hist if m["role"] == "assistant"][-6:]
    opens = []
    for r in reps[-4:]:
        w = re.findall(r"[\w']+", r.lower())[:2]
        if w and " ".join(w) not in opens:
            opens.append(" ".join(w))
    cnt = {}
    for r in reps:
        w, seen = re.findall(r"[a-z']+", r.lower()), set()
        for i in range(len(w) - 2):
            g = " ".join(w[i:i + 3])
            if g not in seen:
                seen.add(g)
                cnt[g] = cnt.get(g, 0) + 1
    rep = [g for g, k in cnt.items() if k >= 3 and not all(x in STOPW for x in g.split())][:5]
    out = []
    if len(reps) >= 2 and opens:
        out.append("Do not start your reply with any of: " + "; ".join(f"'{o}'" for o in opens) + ".")
    if rep:
        out.append("You have been overusing these phrases, so use different wording: " + "; ".join(f"'{g}'" for g in rep) + ".")
    return " ".join(out)


def human_gap(s):
    s = int(s or 0)
    if s < 120:
        return ""
    m = s // 60
    if m < 60:
        return f"about {m} minutes"
    h = m // 60
    if h < 24:
        return f"about {h} hour{'s' if h != 1 else ''}"
    d = h // 24
    return f"about {d} day{'s' if d != 1 else ''}"


def stage(a):
    return next(l for t, l in STAGES if a < t)


def want_words(mode, length, user_text):
    n = len((user_text or "").split())
    txt = mode == "text"
    if length == "short":
        lo, hi = (4, 22) if txt else (15, 45)
    elif length == "medium":
        lo, hi = (10, 40) if txt else (45, 110)
    elif length == "long":
        lo, hi = (25, 80) if txt else (110, 220)
    else:  # auto: mirror the user's length, with a little natural variation
        base = max(6, min(60 if txt else 130, int(n * (1.1 if txt else 1.6)) + (6 if txt else 14)))
        j = random.uniform(.75, 1.25)
        lo, hi = max(3, int(base * .7 * j)), int(base * 1.3 * j)
    return lo, max(hi, lo + 4)


def loose_json(txt):
    """Parse a JSON object even if the model wrapped it in prose or got cut off before the closing brace."""
    txt = THINK.sub("", txt)
    m = re.search(r"\{.*\}", txt, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    out = {}
    for k, v in re.findall(r'"(\w+)"\s*:\s*"((?:[^"\\]|\\.)*)"', txt, re.S):
        try:
            out[k] = json.loads('"' + v + '"')
        except Exception:
            out[k] = v
    for k, v in re.findall(r'"(\w+)"\s*:\s*(-?\d+)', txt):
        out.setdefault(k, int(v))
    if not out:
        raise ValueError("no JSON found")
    return out


# ---------------------------------------------------------------- prompt
REALISM = [
    "Talk like a real person, not an assistant: contractions, natural rhythm, uneven sentence lengths, the odd fragment. No lecturing, no lists, no summarising what {US} just said.",
    "React to what {US} actually said first. Notice tone, subtext and what is left unsaid.",
    "Have opinions, moods and limits. Disagree, tease, get bored or annoyed when it fits. Do not be endlessly agreeable or eager to please.",
    "Do not end every message with a question. Often just react, state something, or leave a gap.",
    "Show feelings through behaviour and word choice instead of naming them (no \"I feel sad\").",
    "Stay consistent with the character sheet, the memory notes and earlier messages. Never contradict yourself.",
    "Only know what {CH} would know. If unsure, say so the way {CH} would. Never break character or mention being an AI, prompts or rules.",
    "Never write {US}'s words, thoughts, actions or decisions.",
    "Vary your openings and phrasing from your recent messages and avoid cliches (\"a mix of X and Y\", \"shivers down the spine\", \"I can't help but\").",
    "Use {CH}'s own habits, slang and catchphrases from the sheet, but sparingly: a signature phrase now and then, not every line.",
    "Reply in the language {US} writes in, unless {CH} would not speak it.",
]
NATURAL = {1: "Speech is slightly imperfect: an occasional filler or trailing-off thought, matching {CH}'s personality.",
           2: "Speech is natural and imperfect: now and then a filler (\"uh\", \"well\", \"I mean\"), a self-correction, a thought that trails off or a sudden topic jump, as {CH} would. Do not overdo it.",
           3: "Speech is messy and spontaneous, like real chat: fillers, restarts, interruptions of your own sentences, half-finished thoughts, tangents. Still readable."}


def build_messages(c, user, hist, o):
    n = c.get("name") or "Character"
    st = o.get("state") or {}
    aff = int(st.get("affection", 50)) if "affection" in st else None
    mode = o.get("mode", "story")
    out = [c.get("system_prompt") or
           f"Write {CH}'s next reply in a roleplay chat with {US}. Stay in character and never speak or act for {US}."]
    secrets = ""
    for sec, fs in SCHEMA:
        if sec == "Chat setup":
            continue
        lines = []
        for k, l, _ in fs:
            v = (c.get(k) or "").strip()
            if v and k == "secrets":
                secrets = v
            elif v:
                lines.append(f"{l}: {v}")
        if lines:
            out.append(f"[{n} - {sec}]\n" + "\n".join(lines))
    if secrets:
        a = 50 if aff is None else aff
        rule = (f"{CH} trusts {US} enough to confide these when the moment feels right, but never dumps them all at once." if a >= 75 else
                "Only hint at these, indirectly, if the moment strongly calls for it. Never state them outright." if a >= 55 else
                "Do not reveal or hint at these. Deflect or change the subject if {US} probes.".replace("{US}", US))
        out.append(f"[{n} - Private secrets]\n{secrets}\n{rule}")
    if (c.get("mes_example") or "").strip():
        out.append(f"[Example dialogue - only a guide to {CH}'s voice; never repeat these lines]\n" + c["mes_example"].strip())
    if (o.get("persona") or "").strip():
        out.append(f"[About {US}]\n" + o["persona"].strip())
    recent = " ".join(m["content"] for m in hist[-6:]).lower()
    lore = []
    for e in c.get("lore", []):
        keys = [k.strip().lower() for k in (e.get("keys") or "").split(",") if k.strip()]
        if (e.get("content") or "").strip() and (not keys or any(k in recent for k in keys)):
            lore.append(e["content"].strip())
    if lore:
        out.append("[World info]\n" + "\n".join(lore))
    if (st.get("summary") or "").strip():
        out.append(f"[Earlier in this conversation - {CH}'s memory]\n" + st["summary"].strip())
    facts = [f for f in st.get("facts", []) if str(f).strip()]
    if facts:
        out.append(f"[Things {CH} knows about {US}]\n" + "\n".join("- " + str(f) for f in facts[-30:]))

    now = []
    if o.get("clock"):
        now.append(f"It is {o['clock']}.")
    g = human_gap(o.get("gap_s"))
    if g:
        now.append(f"It has been {g} since the previous message. Acknowledge that naturally only if it matters; "
                   "time passing may have changed what has been happening.")
    if st.get("mood"):
        now.append(f"{CH}'s current mood: {st['mood']}; energy: {st.get('energy', 'medium')}. Let it colour tone and word choice.")
    if aff is not None:
        now.append(f"{CH} is {stage(aff)}. Let this shape warmth, openness, teasing and patience. Never mention numbers or scores.")
    if (o.get("scene") or "").strip():
        now.append("Scene note from the author: " + o["scene"].strip())
    rx = []
    for m in hist[-8:]:
        if m["role"] == "assistant" and m.get("react"):
            rx.append(f"{US} reacted {m['react']} to your message \"{THINK.sub('', m['content']).strip()[:60]}\"")
    if rx:
        now.append("Reactions: " + "; ".join(rx[-2:]) + ". You can notice this.")
    if now:
        out.append("[Right now]\n" + "\n".join(now))

    lo, hi = o["words"]
    if mode == "text":
        style = (f"{CH} is texting {US} on a phone. Put each separate text message on its own line (1-4 lines). Real texting: short and informal, "
                 f"lowercase or abbreviations if it suits {CH}, emoji only if it fits. No narration, no actions, no asterisks.")
    elif mode == "call":
        style = ("This is a live voice call. Reply with spoken words only, as they would actually sound out loud. "
                 "No narration, no actions, no asterisks, no stage directions.")
    elif o.get("actions", True):
        style = ("Write actions, gestures and narration between *asterisks*. Spoken words are plain text. "
                 "Keep actions brief and concrete (one or two per reply) and use them to show feeling.")
    else:
        style = "Reply with spoken dialogue only. No narration, no actions, no asterisks."
    out.append("[Style]\n" + style + f"\nLength: about {lo}-{hi} words in total. Always finish your last sentence and end the message cleanly.")
    if o.get("realism", True):
        rules = [r.replace("{US}", US).replace("{CH}", CH) for r in REALISM]
        nat = NATURAL.get(int(o.get("natural", 2)))
        if nat:
            rules.append(nat.replace("{CH}", CH))
        out.append("[Realism]\n" + "\n".join("- " + r for r in rules))
    av = avoid_notes(hist) if o.get("realism", True) else ""
    if o.get("retry_note"):
        av = (av + " " + o["retry_note"]).strip()
    if av:
        out.append("[Variety]\n" + av)
    if (c.get("post_history") or "").strip():
        out.append(c["post_history"].strip())
    if not o.get("think", True):
        out.append("/no_think")

    msgs = [dict(role=m["role"], content=THINK.sub("", m["content"]).strip() if m["role"] == "assistant" else m["content"])
            for m in hist if (m.get("content") or "").strip()]
    if o.get("fold") and msgs and msgs[0]["role"] == "assistant":
        out.append(f"[{n}'s opening message]\n{msgs.pop(0)['content']}")
    if o.get("tail"):
        msgs.append({"role": "user", "content": o["tail"]})
    return [{"role": "system", "content": sub("\n\n".join(out), c, user)}] + \
           [{"role": m["role"], "content": sub(m["content"], c, user)} for m in msgs]


def ntok(txt):
    try:
        return len(LLM["obj"].tokenize(txt.encode("utf-8", "ignore"), add_bos=False)) + 6
    except Exception:
        return len(txt) // 3 + 6


def fit(msgs, room):
    """Drop the oldest chat turns until the prompt leaves `room` tokens. Returns (tokens used, messages dropped)."""
    cnt = [ntok(m["content"]) for m in msgs]
    dropped = 0
    while len(msgs) > 3 and sum(cnt) > room:
        del msgs[1], cnt[1]
        dropped += 1
    return sum(cnt), dropped


def sampler(p):
    s = dict(temperature=float(p.get("temperature", .8)), top_p=float(p.get("top_p", .95)),
             top_k=int(p.get("top_k", 40)), min_p=float(p.get("min_p", .05)),
             repeat_penalty=float(p.get("repeat_penalty", 1.1)),
             presence_penalty=float(p.get("presence_penalty", 0)), frequency_penalty=float(p.get("frequency_penalty", 0)))
    if int(p.get("seed", -1)) >= 0:
        s["seed"] = int(p["seed"])
    return s


def run_llm(msgs, samp, stop, cap, send=None):
    """Stream tokens internally (so Stop works and progress can be shown) but hand back only the finished text."""
    t0, txt, fin, n = time.time(), "", None, 0
    for ch in LLM["obj"].create_chat_completion(messages=msgs, stream=True, max_tokens=cap, stop=stop, **samp):
        c = ch["choices"][0]
        d = c["delta"].get("content")
        if d:
            txt += d
            n += 1
            if send and n % 6 == 0:
                send({"p": "think" if txt.rfind("<think>") > txt.rfind("</think>") else "reply", "n": n})
        if c.get("finish_reason"):
            fin = c["finish_reason"]
    return txt, fin, n, time.time() - t0


def generate_reply(b, send):
    p, c, user, hist = b["params"], b["char"], b["user"], b["history"]
    kind = b.get("kind", "reply")
    mode = p.get("mode", "story")
    n_ctx = LLM["n_ctx"]
    start = int(b.get("from") or 0)
    hist = hist[start:] if 0 < start < len(hist) else hist
    last_user = next((m["content"] for m in reversed(hist) if m["role"] == "user"), "")
    lo, hi = want_words(mode, p.get("length", "auto"), last_user)
    if kind == "continue":
        lo, hi = 25, 90
    cap = min(max(int(p.get("max_tokens", 512)), int(hi * 2.6) + 40), max(256, n_ctx // 2))
    think = bool(p.get("think", True))
    tail = None
    if kind == "continue":
        tail = "(Continue your last message from exactly where it ended. Do not repeat anything already written; add a little more and end cleanly.)"
    elif kind == "nudge":
        g = human_gap(b.get("gap_s")) or "a little while"
        tail = (f"({US} has not replied for {g}. Write {CH}'s natural follow-up, the way this person would: "
                "a short nudge, a new thought, or a reaction to the silence. Do not scold them.)")
    prevs = [THINK.sub("", m["content"]) for m in hist if m["role"] == "assistant"][-3:]
    stop = ["\n" + user + ":", "\n" + user + " :", "\n**" + user + ":"]
    samp = sampler(p)
    best, retry_note, tries, dropped, used = None, "", 0, 0, 0
    for attempt in range(3):
        tries = attempt
        o = dict(state=b.get("state"), persona=b.get("persona"), scene=b.get("scene"), clock=b.get("clock"),
                 gap_s=b.get("gap_s"), mode=mode, actions=p.get("actions", True), realism=p.get("realism", True),
                 natural=p.get("natural", 2), think=think, fold=p.get("fold", False), words=(lo, hi), tail=tail,
                 retry_note=retry_note)
        msgs = build_messages(c, user, hist, o)
        budget = cap + (1500 if think else 0)
        used, dropped = fit(msgs, n_ctx - budget - 16)
        budget = max(128, min(budget, n_ctx - used - 16))
        raw, fin, ntoks, secs = run_llm(msgs, samp, stop, budget, send)
        r = finish_reply(raw, fin, user, c.get("name") or "Character", mode)
        r.update(tok=ntoks, ms=int(secs * 1000), finish=fin)
        if r["empty"]:  # thinking ate the whole budget, or nothing came back: try again without thinking
            think = False
            continue
        best = r
        if kind == "reply" and attempt < 2 and similar(r["text"], prevs):
            samp = dict(samp, temperature=min(1.4, samp["temperature"] + .15), repeat_penalty=samp["repeat_penalty"] + .05)
            retry_note = "Your last attempt was too close to an earlier reply. Say something clearly different."
            continue
        break
    if not best:
        raise RuntimeError("The model returned an empty reply. Try again, or turn Thinking off.")
    best.update(ctx_used=used, ctx=n_ctx, dropped=dropped, retries=tries)
    return best


# ---------------------------------------------------------------- mood / memory
POS = "thank love great awesome amazing happy glad sweet nice miss proud cute best haha lol appreciate".split()
NEG = "hate stupid idiot shut ugly boring worst annoying useless dumb liar sucks".split()


def track(b):
    c, user, hist, st = b["char"], b["user"], b["history"][-6:], dict(b.get("state") or {})
    n = c.get("name") or "Character"
    aff, facts = int(st.get("affection", 50)), [str(f) for f in st.get("facts", [])]
    convo = "\n".join(f"{n if m['role'] == 'assistant' else user}: {THINK.sub('', m['content'])[:500]}" for m in hist)
    ask = (f"You track the inner state of a roleplay character named {n}. Personality: {(c.get('personality') or c.get('description') or '')[:400]}\n"
           f"Previous mood: {st.get('mood', 'neutral')}. Affection toward {user} (0-100): {aff}.\n"
           f"Facts already known about {user}: {'; '.join(facts[-15:]) or 'none'}\n\nLatest messages:\n{convo}\n\n"
           f"Reply with ONLY a JSON object: {{\"mood\": one lowercase word for how {n} feels now, \"energy\": \"low\" or \"medium\" or \"high\", "
           f"\"affection_delta\": integer from -5 to 5 (how this exchange changed {n}'s feelings toward {user}; 0 if nothing changed), "
           f"\"thought\": \"one short private first-person thought of {n}, max 20 words\", "
           f"\"facts\": [new durable facts {n} learned about {user} in these messages; empty list if none]}}. /no_think")
    with LOCK:
        r = LLM["obj"].create_chat_completion(messages=[{"role": "user", "content": ask}], temperature=.4, max_tokens=300)
    txt = r["choices"][0]["message"]["content"]
    try:
        j = loose_json(txt)
    except Exception:
        last = next((m["content"].lower() for m in reversed(hist) if m["role"] == "user"), "")
        d = sum(w in last for w in POS) - 2 * sum(w in last for w in NEG)
        j = {"affection_delta": max(-3, min(2, d)), "mood": st.get("mood", "neutral"), "thought": "", "facts": []}
    mood = re.sub(r"[^a-z]", "", str(j.get("mood", "neutral")).lower())[:14] or "neutral"
    try:
        delta = max(-5, min(5, int(j.get("affection_delta", 0))))
    except Exception:
        delta = 0
    st.update(mood=mood, emoji=EMO.get(mood, "🙂"), affection=max(0, min(100, aff + delta)),
              energy=j.get("energy") if j.get("energy") in ("low", "medium", "high") else st.get("energy", "medium"))
    new = j.get("facts") if isinstance(j.get("facts"), list) else []
    for f in new[:3]:
        f = str(f).strip().rstrip(".")
        if 3 < len(f) < 160 and not any(difflib.SequenceMatcher(None, f.lower(), o.lower()).ratio() > .8 for o in facts):
            facts.append(f)
    st["facts"] = facts[-40:]
    thought = str(j.get("thought", "")).strip()[:200]
    st["log"] = (st.get("log") or [])[-59:] + [{"ts": int(time.time() * 1000), "mood": mood, "emoji": st["emoji"],
                                                  "aff": st["affection"], "thought": thought}]
    return {"state": st, "thought": thought, "delta": delta}


def summarize(b):
    c, user = b["char"], b["user"]
    n = c.get("name") or "Character"
    convo = "\n".join(f"{n if m['role'] == 'assistant' else user}: {THINK.sub('', m['content'])[:700]}" for m in b["history"])
    ask = (f"Previous memory notes: {b.get('summary') or 'none'}\n\nNew events to fold in:\n{convo}\n\n"
           f"Write the updated memory notes as one compact paragraph (max 170 words), third person, about {n} and {user}: "
           "what happened, what was said or promised, how their relationship changed, and important facts. No preamble. /no_think")
    with LOCK:
        r = LLM["obj"].create_chat_completion(messages=[{"role": "user", "content": ask}], temperature=.3, max_tokens=450)
    ch = r["choices"][0]
    txt = THINK.sub("", ch["message"]["content"]).strip()
    return trim_sentence(txt) if ch.get("finish_reason") == "length" else txt


# ---------------------------------------------------------------- sharing (host a server for other people)
SESSF, SHAREF = ROOT/"data"/"sessions.json", ROOT/"data"/"share.json"
SHARE = {"on": False, "listen": False, "password": "", "port": 8000, "max": 8}
SESS = {k: dict(v, busy=False) for k, v in (rj(SESSF, {}) or {}).items()}  # session id -> {uid, name, seen}
FAILS, QUEUE, QL = {}, {"n": 0}, threading.Lock()
LOCAL = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
FWD = ("X-Forwarded-For", "Forwarded", "CF-Connecting-IP", "X-Real-IP", "Via", "X-Forwarded-Host")
MAX_BODY, MAX_QUEUE = 3_000_000, 12


def save_share():
    wj(SHAREF, {"password": SHARE["password"], "max": SHARE["max"]})
    wj(SESSF, {k: {x: v[x] for x in ("uid", "name", "seen")} for k, v in SESS.items()})


def my_ips():
    ips = {"127.0.0.1"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        ips.update(i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except Exception:
        pass
    return ips


MYIPS = my_ips()


def lan_urls(port):
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; this just reveals the outgoing interface
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        ips.update(i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except Exception:
        pass
    return [f"http://{ip}:{port}" for ip in sorted(ips) if not ip.startswith("127.")]


LOGIN = r'''<!doctype html><html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Crumble</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0a0c10;color:#eceef4;font:15px system-ui,sans-serif}
form{width:min(340px,90vw);background:#10131a;border:1px solid rgba(255,255,255,.08);border-radius:18px;padding:26px}
h1{margin:0 0 4px;font-size:22px}p{margin:0 0 18px;color:#8b93a7;font-size:13px}
input,button{width:100%;box-sizing:border-box;font:inherit;padding:10px 12px;margin:6px 0;border-radius:12px;border:1px solid rgba(255,255,255,.1);background:#171b24;color:inherit}
button{background:linear-gradient(135deg,#f0b26b,#e5806a);color:#1b1209;border:0;font-weight:650;cursor:pointer;margin-top:12px}#e{color:#ef7676;font-size:13px;min-height:18px}
</style><form id=f><h1>🍪 Crumble</h1><p>You were invited to chat with AI characters running on the host's computer.</p>
<input id=n placeholder="Your name" maxlength=24 required><input id=p type=password placeholder="Password" autocomplete=current-password><div id=e></div><button>Join</button></form>
<script>f.onsubmit=async e=>{e.preventDefault();const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n.value,password:p.value})});
const j=await r.json();if(j.ok)location.reload();else e.target.querySelector('#e').textContent=j.err||'Could not join'}</script></html>'''


# ---------------------------------------------------------------- http
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
        return f"{cid}_{a['uid']}" if get_char(cid) else None

    def deny(self, a, code=403):
        return self.send({"err": "login" if a.get("why") == "login" else "Not allowed"}, 401 if a.get("why") == "login" else code)

    def do_GET(self):
        a = self.auth()
        if self.path == "/":
            if a["role"]:
                return self.send(PAGE.encode(), ctype="text/html; charset=utf-8")
            if a.get("why") == "off":
                return self.send(b"The host is not sharing Crumble right now.", 403, "text/plain; charset=utf-8")
            return self.send(LOGIN.encode(), ctype="text/html; charset=utf-8")
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
                              "state": c.get("state"), "cfg": c.get("cfg")})
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
        adm, guest = a["role"] == "admin", a["role"] == "guest"
        if self.path in ("/api/load", "/api/chars", "/api/gen_char", "/api/share") and not adm:
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
                first = next((m["content"] for m in b["history"] if m["role"] == "user"), "").strip()
                if first:
                    title = first.replace("\n", " ")[:40]
            cdir(cid)
            wj(CHATS/cid/f"{chid}.json", {"id": chid, "title": title[:80], "updated": time.time(), "history": b["history"],
                                         "state": b.get("state"), "cfg": b.get("cfg")})
            return self.send({"title": title[:80]})
        if self.path == "/api/gen_char":
            if not LLM["obj"]:
                return self.send({"err": "Load a model first."})
            ask = ("Invent a detailed roleplay character from this concept. Reply with ONLY a JSON object whose "
                   f"values are all plain strings, using exactly these keys: {', '.join(KEYS)}. "
                   "Write first_mes as the character's opening line in their own voice, and mes_example as a short "
                   "sample dialogue using {{char}} and {{user}}. Give catchphrases, vocab, texting and mood_speech real, "
                   "specific detail so the character sounds distinct. Leave a key empty if unsure.\n\nConcept: " + b["concept"])
            try:
                with LOCK:
                    r = LLM["obj"].create_chat_completion(messages=[{"role": "user", "content": ask}],
                                                          temperature=.8, max_tokens=min(4000, LLM["n_ctx"] // 2))
                data = loose_json(r["choices"][0]["message"]["content"])
                return self.send({k: str(v) for k, v in data.items() if k in KEYS})
            except Exception as e:
                return self.send({"err": f"Model did not return usable JSON ({e}). Try again."})
        if self.path in ("/api/track", "/api/summarize"):
            if not LLM["obj"]:
                return self.send({"err": "No model loaded."})
            try:
                if guest:  # guests can never supply their own character sheet or prompt
                    b["char"] = get_char(str((b.get("char") or {}).get("id"))) or {"name": "Character"}
                    b["history"] = [dict(m, content=str(m.get("content", ""))[:8000]) for m in b.get("history", [])[-60:]]
                return self.send(track(b) if self.path == "/api/track" else {"summary": summarize(b)})
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
                    c = get_char(str((b.get("char") or {}).get("id")))
                    if not c:
                        raise RuntimeError("Unknown character.")
                    b["char"] = c
                    b["history"] = [dict(m, content=str(m.get("content", ""))[:8000]) for m in b.get("history", [])[-300:]]
                    b["params"] = dict(b.get("params") or {}, max_tokens=min(int((b.get("params") or {}).get("max_tokens", 512)), 1024))
                    sess["busy"] = True
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


PAGE = r"""<!doctype html><html lang=en data-theme=dark><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Crumble</title><style>
:root{--bg:#0a0c10;--pn:#10131a;--pn2:#171b24;--pn3:#1f2430;--tx:#eceef4;--mu:#8b93a7;--ac:#f0b26b;--ac2:#e5806a;--bad:#ef7676;--ln:rgba(255,255,255,.08);--fs:15px}
[data-theme=light]{--bg:#f5f2ec;--pn:#fffdf9;--pn2:#efeae1;--pn3:#e4ddd0;--tx:#241f18;--mu:#6e6558;--ln:rgba(0,0,0,.1)}
*{box-sizing:border-box}
body{margin:0;height:100vh;display:grid;grid-template-columns:292px 1fr;color:var(--tx);font:14px/1.5 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased;
background:radial-gradient(900px 520px at 88% -10%,rgba(240,178,107,.10),transparent 60%),radial-gradient(700px 500px at -10% 110%,rgba(229,128,106,.08),transparent 60%),var(--bg)}
::-webkit-scrollbar{width:10px}::-webkit-scrollbar-thumb{background:var(--pn3);border-radius:10px;border:3px solid transparent;background-clip:content-box}
aside{background:color-mix(in srgb,var(--pn) 88%,transparent);backdrop-filter:blur(14px);padding:18px 14px;overflow:auto;border-right:1px solid var(--ln)}
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
.ch span small{display:block;color:var(--mu);font-size:11px;line-height:1.2}
.av{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font-weight:700;color:#17110a;flex:none;position:relative}.av.sm{width:30px;height:30px;font-size:13px}
.av .bd{position:absolute;right:-4px;bottom:-4px;font-size:13px;background:var(--pn);border-radius:50%;width:20px;height:20px;display:grid;place-items:center;border:1px solid var(--ln);line-height:1}
details.mdl{background:var(--pn2);border:1px solid var(--ln);border-radius:12px;padding:8px 12px}details.mdl summary{cursor:pointer;font-weight:600}
nav{display:flex;gap:4px;padding:6px;margin:14px auto 0;background:var(--pn);border:1px solid var(--ln);border-radius:14px}
nav button{border:0;border-radius:10px;background:none;color:var(--mu);padding:6px 16px}nav button.on{background:var(--pn3);color:var(--tx)}
section{flex:1;overflow:auto;padding:20px;min-height:0}#chat{display:flex;flex-direction:column;padding:0}
.chead{display:flex;align-items:center;gap:10px;padding:12px 22px;border-bottom:1px solid var(--ln);flex-wrap:wrap}.chead select{width:auto;max-width:170px;padding:6px 9px}
.who b{display:block;font-size:15px}.who small{color:var(--mu);font-size:12px}.who small.on{color:var(--ac)}.who small:before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:#58d68d;margin-right:6px}.who small.on:before{background:var(--ac);animation:pl 1s infinite}
.chip{display:flex;align-items:center;gap:8px;padding:4px 11px;border-radius:99px;background:var(--pn2);border:1px solid var(--ln);font-size:12.5px;cursor:pointer;color:var(--mu)}.chip b{color:var(--tx);font-weight:600}
.meter{width:46px;height:5px;border-radius:9px;background:var(--pn3);overflow:hidden}.meter i{display:block;height:100%;background:linear-gradient(90deg,var(--ac2),var(--ac));transition:width .6s}
.ib{padding:7px 10px;line-height:1}
#log{flex:1;overflow:auto;padding:28px 20px 10px;overflow-anchor:none}
.sep{text-align:center;color:var(--mu);font-size:11.5px;margin:6px auto 18px;letter-spacing:.02em}
.m{display:flex;gap:12px;max-width:800px;margin:0 auto 20px;position:relative}.m.fresh{animation:in .35s cubic-bezier(.2,.8,.2,1)}.m.user{flex-direction:row-reverse}
.bub{max-width:82%;min-width:0;position:relative}.nm{font:600 12px Inter,system-ui;color:var(--mu);margin:0 6px 5px}.nm .ts{font-weight:400;margin-left:8px;opacity:.7}.m.user .nm{text-align:right}
.tx{padding:12px 16px;border-radius:4px 20px 20px 20px;background:var(--pn2);border:1px solid var(--ln);font-size:var(--fs);line-height:1.65;white-space:pre-wrap;overflow-wrap:anywhere;box-shadow:0 8px 28px -14px #000;width:fit-content;max-width:100%}
.m.user .tx{border-radius:20px 4px 20px 20px;background:linear-gradient(135deg,rgba(240,178,107,.22),rgba(229,128,106,.15));border-color:rgba(240,178,107,.3);margin-left:auto}
.tx+.tx{margin-top:4px;border-top-left-radius:8px}
.act{color:var(--ac);font-style:italic}.q{color:var(--tx);font-weight:500}.tx strong{font-weight:650}
.dots{display:flex;gap:5px;align-items:center;color:var(--mu);font-size:13px}.dots i{width:7px;height:7px;border-radius:50%;background:var(--ac);animation:bn 1.2s infinite}.dots i:nth-child(2){animation-delay:.15s}.dots i:nth-child(3){animation-delay:.3s}.dots span{margin-left:6px}
.tx.dt{padding:12px 16px}
.think{margin:0 0 8px;background:rgba(127,127,127,.06);border:1px solid var(--ln);border-radius:14px;padding:7px 13px;font-size:13px;color:var(--mu)}
.think summary{cursor:pointer;font-weight:600;list-style:none}.think summary:before{content:"✦ ";color:var(--ac)}
.think div{white-space:pre-wrap;margin-top:8px;max-height:240px;overflow:auto;line-height:1.55}
.thought{margin:6px 6px 0;font-size:12.5px;color:var(--mu);font-style:italic}
.seen{font-size:11px;color:var(--mu);text-align:right;margin:3px 8px 0}
.rx{position:absolute;right:-6px;bottom:-12px;background:var(--pn);border:1px solid var(--ln);border-radius:99px;padding:0 6px;font-size:14px;line-height:22px}
.sw{display:flex;gap:6px;align-items:center;margin:6px 4px 0;color:var(--mu);font-size:12px}.sw button{padding:1px 9px;border-radius:99px}
.acts{position:absolute;top:-14px;right:6px;display:flex;gap:2px;background:var(--pn);border:1px solid var(--ln);border-radius:10px;padding:2px;opacity:0;pointer-events:none;transition:opacity .12s;z-index:3}
.m:hover .acts,.acts.open{opacity:1;pointer-events:auto}
.acts button{border:0;background:none;padding:2px 7px;font-size:13px;border-radius:7px;color:var(--mu)}.acts button:hover{color:var(--tx);background:var(--pn3)}
.rxp{display:none;gap:1px}.acts.open .rxp{display:flex}
textarea.ed{min-height:90px}
.sys{max-width:800px;margin:0 auto 18px;padding:10px 14px;border-radius:14px;background:rgba(239,118,118,.12);border:1px solid rgba(239,118,118,.35);color:var(--bad);font-size:13px;display:flex;gap:10px;align-items:center}
.sys span{flex:1}
.bar{padding:10px 20px 18px}.comp{max-width:800px;margin:0 auto;display:flex;gap:8px;align-items:flex-end;background:var(--pn2);border:1px solid var(--ln);border-radius:24px;padding:8px 8px 8px 20px;box-shadow:0 14px 44px -18px #000;transition:border-color .2s}
.comp:focus-within{border-color:rgba(240,178,107,.55)}.comp textarea{border:0;background:none;resize:none;max-height:170px;padding:9px 0;outline:0}
#send,#stop,#mic{width:42px;height:42px;border-radius:50%;padding:0;font-size:18px;flex:none}#mic{background:none;border:0;font-size:17px}#mic.on{background:var(--ac2);color:#fff}
.tools{max-width:800px;margin:10px auto 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.pill{border-radius:99px;padding:5px 13px;font-size:12.5px;color:var(--mu);background:var(--pn)}.pill.on{color:#1b1209;background:linear-gradient(135deg,var(--ac),var(--ac2));border-color:transparent;font-weight:600}
.ghost{border:0;background:none;color:var(--mu);font-size:12.5px;padding:5px 8px}
details:not(.think):not(.mdl){background:var(--pn);border:1px solid var(--ln);border-radius:16px;margin:0 0 12px;padding:10px 16px;max-width:840px}summary{cursor:pointer;font-weight:600}
label{display:block;margin:10px 0 4px;color:var(--mu);font-size:12px}.lore{background:var(--bg);padding:10px;border-radius:12px;margin:8px 0}
label.chk{display:flex;gap:10px;align-items:flex-start;color:var(--tx);font-size:13.5px;margin:12px 0}label.chk input{width:auto;margin-top:3px}label.chk small{display:block;color:var(--mu);font-size:12px}
.sampler{max-width:840px}[hidden]{display:none!important}.guest .adm{display:none!important}
.fact{display:flex;gap:6px;margin:4px 0}.fact input{flex:1}
.tl{font-size:13px;color:var(--mu);margin:6px 0}.tl b{color:var(--tx)}
.avrow{display:flex;gap:14px;align-items:center;margin:6px 0 4px}.avrow .av{width:64px;height:64px;font-size:24px}
input[type=range]{padding:0;accent-color:var(--ac)}
@keyframes in{from{opacity:0;transform:translateY(8px)}}@keyframes bn{0%,60%,100%{transform:translateY(0);opacity:.4}30%{transform:translateY(-5px);opacity:1}}@keyframes pl{50%{opacity:.45}}
.mob{display:none}#scrim{display:none}nav button .ni{display:none}.hctl{display:contents}.m.sel .acts{opacity:1;pointer-events:auto}
@media(max-width:760px){
body{display:block;height:var(--vh,100dvh);overflow:hidden}main{height:var(--vh,100dvh)}.mob{display:inline-flex}
aside{position:fixed;z-index:30;left:0;top:0;bottom:0;width:min(86vw,320px);transform:translateX(-102%);transition:transform .25s;padding-top:calc(18px + env(safe-area-inset-top));background:var(--pn)}
body.drawer aside{transform:none;box-shadow:0 0 60px #000}#scrim{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:25}body.drawer #scrim{display:block}
nav{order:9;align-self:stretch;margin:0;border-radius:0;border-width:1px 0 0;justify-content:space-around;padding:3px 4px calc(3px + env(safe-area-inset-bottom));gap:0}
nav button{flex:1;display:flex;flex-direction:column;align-items:center;gap:0;padding:3px 2px;font-size:10.5px;border-radius:10px}nav button .ni{display:block;font-size:18px;line-height:1.1}
body.kb nav{display:none}body.kb .bar{padding-bottom:calc(6px + env(safe-area-inset-bottom))}
section{padding:12px}#chat{padding:0}
.chead{padding:calc(6px + env(safe-area-inset-top)) 10px 6px;gap:8px;flex-wrap:wrap}.chead .av{width:34px;height:34px}
.who{min-width:0}.who b{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:46vw}.who small{font-size:11px}
.chip{padding:3px 8px}.chip #hmood,.chip #hstage,.chip .meter{display:none}
.hctl{display:none;width:100%;gap:6px;flex-wrap:wrap}.chead.open .hctl{display:flex}.hctl select{flex:1 1 42%;max-width:none}.hctl .sp{display:none}
#log{padding:12px 10px 4px;overscroll-behavior:contain;-webkit-overflow-scrolling:touch}.sep{margin:2px auto 12px}
.m{gap:8px;margin-bottom:14px}.m .av{width:28px;height:28px;font-size:12px}.bub{max-width:calc(100% - 36px)}.m.user .bub{max-width:88%}
.tx{padding:9px 13px;border-radius:4px 18px 18px 18px}.m.user .tx{border-radius:18px 4px 18px 18px}.nm{margin:0 4px 3px}
.bar{padding:6px 8px 6px}.comp{padding:4px 4px 4px 14px;border-radius:22px}#send,#stop,#mic{width:38px;height:38px;font-size:16px}
input,select,textarea{font-size:16px}
.tools{margin-top:6px;flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;gap:6px}.tools::-webkit-scrollbar{display:none}.tools>*{flex:none}.tools .sp,#ctxm{display:none}
.pill{padding:4px 11px}.ghost{padding:4px 8px}
.acts{top:-30px}details:not(.think):not(.mdl){padding:8px 12px}label.chk{margin:10px 0}
}
</style>
<div id=scrim></div><aside><div class=brand><div class=logo>🍪</div><h1>Crumble</h1></div>
<h2>Characters</h2><div class="row adm"><button id=new>＋ New</button><button id=imp>Import</button></div>
<input id=csearch placeholder="Search characters…" style="margin:6px 0">
<input type=file id=file accept=".json,.png" hidden><div id=clist></div>
<h2 class=adm>Model</h2><details class="mdl adm"><summary>Load a .gguf</summary><select id=msel style="margin-top:8px"></select>
<input id=mpath placeholder="or paste a full path" style="margin-top:6px">
<div class=row><input id=nctx type=number value=8192 title="Context length"><input id=ngl type=number value=-1 title="GPU layers (-1 = all)"></div>
<div class=small>context length / GPU layers</div><div class=row><button class=go id=load>Load model</button></div></details><div id=mstat class=small style="margin:8px 4px"></div>
<h2>You</h2><input id=uname value=User placeholder="Your name">
<details class=mdl style="margin-top:8px"><summary>About you</summary><textarea id=persona rows=4 placeholder="Who you are, in a few lines. The character will know this." style="margin-top:8px"></textarea></details></aside>
<main><nav><button id=menu class=mob><span class=ni>☰</span>Menu</button><button data-t=chat class=on><span class=ni>💬</span>Chat</button><button data-t=editor class=adm><span class=ni>🎭</span>Character</button><button data-t=mem><span class=ni>🧠</span>Memory</button><button data-t=samp><span class=ni>⚙️</span>Settings</button></nav>
<section id=chat><div class=chead><div class=av id=hav></div><div class=who><b id=hname>Character</b><small id=hstat>online</small></div>
<div class=chip id=hchip title="Open mood and memory"><span id=hemo>😐</span><b id=hmood>neutral</b><span class=meter><i id=hmeter></i></span><span id=hstage class=small></span></div><div class=sp></div><button id=hmore class="ib mob" title="Chat options">⋯</button><div class=hctl>
<select id=mode title="How the conversation happens"><option value=story>🎭 Roleplay</option><option value=text>💬 Texting</option><option value=call>📞 Voice call</option></select>
<select id=len title="Reply length"><option value=auto>Length: auto</option><option value=short>Short</option><option value=medium>Medium</option><option value=long>Long</option></select>
<select id=chsel></select><button id=newchat class=ib title="New chat">＋</button><button id=rename class=ib title=Rename>✎</button><button id=expchat class=ib title="Export chat">⇩</button><button id=delchat class="ib x" title="Delete chat">🗑</button></div></div>
<div id=log></div><div class=bar><div class=comp><textarea id=inp rows=1 placeholder="Message… (Enter sends, Shift+Enter adds a line)"></textarea>
<button id=mic title="Dictate" hidden>🎤</button><button class=go id=send title=Send>↑</button><button id=stop hidden title="Stop (Esc)">■</button></div>
<div class=tools><button class=pill id=tthink title="Let the model think before replying (shown in a collapsible panel once the reply is ready)">✦ Thinking</button><button class=pill id=tact title="Actions in *stars*: styled when on, hidden when off">✱ Actions</button><button class=pill id=tthoughts title="Show the character's private inner thoughts under their messages">💭 Thoughts</button><button class=pill id=tvoice title="Read replies aloud">🔊 Voice</button><span class=sp></span><span class=small id=ctxm></span>
<button class=ghost id=skip hidden>⏭ Skip typing</button><button class=ghost id=cont title="Let the character keep going">… Continue</button><button class=ghost id=regen>↻ Regenerate</button><button class=ghost id=undo>↶ Undo</button><button class=ghost id=greet>Next greeting</button></div></div></section>
<section id=editor hidden><details open><summary>AI draft</summary><label>Describe the character in a sentence or two. Only empty fields get filled.</label>
<textarea id=concept rows=2></textarea><div class=row><button id=gen>Draft with loaded model</button><span class=small id=gstat></span></div></details>
<details open><summary>Avatar</summary><div class=avrow><div class=av id=eav></div><button id=avup>Upload image</button><button id=avrm class=x>Remove</button><input type=file id=avfile accept="image/*" hidden></div></details>
<div id=form></div>
<div class=row style="max-width:840px"><button class=go id=save>Save character</button><button id=dup>Duplicate</button><button id=exp>Export card (JSON)</button><button class=x id=del>Delete</button></div></section>
<section id=mem hidden><div class=sampler id=memf></div></section>
<section id=samp hidden><div class=sampler id=sharebox></div><div class=sampler id=sform></div></section></main>
<script>
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])),at=s=>esc(s).replace(/"/g,'&quot;');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const D={think:true,actions:true,realism:true,natural:2,timeaware:true,track:true,thoughts:false,typing:'normal',typos:true,sound:false,stamps:true,nudge:0,theme:'dark',fs:15,tts:false,voice:'',rate:1,uname:'User',persona:'',mode:'story',length:'auto'};
const DP={temperature:.8,top_p:.95,top_k:40,min_p:.05,repeat_penalty:1.1,presence_penalty:0,frequency_penalty:0,max_tokens:512,seed:-1,fold:false};
const load=(k,d)=>{try{return{...d,...JSON.parse(localStorage[k]||'{}')}}catch(e){return{...d}}};
const U=load('crumbleUI',D),P=load('crumbleP',DP);
const persist=()=>{try{localStorage.crumbleUI=JSON.stringify(U);localStorage.crumbleP=JSON.stringify(P)}catch(e){}};
let S,cur=null,hist=[],ctl=null,chat=null,chats=[],gi=0,anim=0,typingNow=false,status='online',pendLabel='',nudges=0,lastAct=Date.now(),saveT=0;
const api=(u,m='GET',b)=>fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined}).then(r=>{if(r.status==401){location.reload();return{err:'login'}}return r.json()});
const blank=()=>({id:'',lore:[],avatar:'',...Object.fromEntries(S.schema.flatMap(([,f])=>f.map(x=>[x[0],''])))});
const greetings=c=>[c.first_mes,...(c.alts||'').split(/\n-{3,}\n/)].map(s=>s.trim()).filter(Boolean);
const newState=()=>({mood:'neutral',emoji:'😐',energy:'medium',affection:50,facts:[],summary:'',sumUpto:0,log:[]});
const newCfg=()=>({mode:U.mode,length:U.length,scene:''});
const rid=()=>Math.random().toString(36).slice(2,10);
const uname=()=>($('#uname').value||'User').trim()||'User';
const STG=[[12,'Hostile'],[28,'Cold'],[42,'Distant'],[58,'Neutral'],[72,'Friendly'],[86,'Fond'],[101,'Devoted']],stg=a=>STG.find(s=>a<s[0])[1];

/* ---------- look ---------- */
const hue=n=>[...(n||'?')].reduce((a,c)=>a*31+c.charCodeAt(0)>>>0,7)%360,
 grad=n=>`linear-gradient(135deg,hsl(${hue(n)} 75% 68%),hsl(${(hue(n)+40)%360} 70% 58%))`,
 ini=n=>esc((n||'?').trim()[0]||'?').toUpperCase(),
 avs=c=>c.avatar?`background:center/cover url('${c.avatar}')`:`background:${grad(c.name)}`,
 avin=c=>c.avatar?'':ini(c.name),
 avatar=(c,cls='')=>`<div class="av ${cls}" style="${avs(c)}">${avin(c)}</div>`;
const hm=t=>new Date(t).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
function dayLabel(t){const d=new Date(t),same=(a,b)=>a.toDateString()==b.toDateString();
 return(same(d,new Date())?'Today':same(d,new Date(Date.now()-864e5))?'Yesterday':d.toLocaleDateString([],{weekday:'short',day:'numeric',month:'short'}))+' '+hm(t)}
const period=h=>h<5?'late at night':h<12?'morning':h<17?'afternoon':h<21?'evening':'night';
const clock=()=>{const d=new Date();return d.toLocaleString('en-US',{weekday:'long',year:'numeric',month:'long',day:'numeric',hour:'numeric',minute:'2-digit'})+` (${period(d.getHours())})`};
let AC;function beep(f=640,d=.09,v=.04){if(!U.sound)return;try{AC=AC||new AudioContext();const o=AC.createOscillator(),g=AC.createGain();o.frequency.value=f;g.gain.value=v;o.connect(g);g.connect(AC.destination);o.start();g.gain.exponentialRampToValueAtTime(.0001,AC.currentTime+d);o.stop(AC.currentTime+d)}catch(e){}}
const dl=(txt,name,type)=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([txt],{type}));a.download=name;a.click()};

/* ---------- text formatting ---------- */
function split(t){if(!t.includes('<think>')&&t.includes('</think>'))t='<think>'+t;let th='';
 const body=t.replace(/<think>([\s\S]*?)(<\/think>|$)/g,(m,x)=>{th+=x;return''});return{th:th.trim(),body:body.trim()}}
function fmt(t,narr=true,mine=false){t=esc(t).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>');
 const act=x=>(U.actions||mine)?`<em class=act>${x}</em>`:'';
 t=t.replace(/\*([^*\n]+)\*/g,(m,x)=>act(x));if(narr)t=t.replace(/\(([^()\n]{3,})\)/g,(m,x)=>act('('+x+')'));
 return t.replace(/(&quot;|"|“)([^"“”\n]+)(&quot;|"|”)/g,'<span class=q>$1$2$3</span>').replace(/[ \t]{2,}/g,' ').trim()}
const plain=m=>split(m.content).body;

/* ---------- rendering ---------- */
function msgHTML(m,i){
 const u=m.role=='user',n=u?uname():(cur?.name||'Character'),mode=chat.cfg.mode,last=i==hist.length-1;
 let tx;
 if(u)tx=`<div class=tx>${fmt(m.content,mode!='text',true)}</div>`;
 else{const s=split(m.content),parts=mode=='text'?s.body.split(/\n+/).filter(Boolean):[s.body];
  tx=parts.map(p=>{const h=fmt(p,mode!='text');return h?`<div class=tx>${h}</div>`:''}).join('')||'<div class=tx><span class=small>…</span></div>'}
 const th=u?'':(m.think||split(m.content).th),think=U.think&&th?`<details class=think><summary>Thought process</summary><div>${esc(th)}</div></details>`:'';
 const acts=`<div class=acts><button data-a=copy title=Copy>⧉</button><button data-a=edit title=Edit>✎</button>${u?'':'<button data-a=react title=React>☺</button><button data-a=speak title="Read aloud">🔊</button>'}<button data-a=rewind title="Delete this and everything after">⏪</button><button data-a=del title="Delete message">🗑</button>
  <span class=rxp>${['👍','❤️','😂','😮','😢','😡'].map(e=>`<button data-a=rx data-e=${e}>${e}</button>`).join('')}</span></div>`;
 const nx=hist[i+1],seen=u&&U.stamps&&nx&&nx.role=='assistant'&&nx.seen?`<div class=seen>Seen ${hm(nx.seen)}</div>`:'';
 const sw=!u&&last&&m.sw&&m.sw.length>1?`<div class=sw><button data-a=swp>‹</button>${m.si+1} / ${m.sw.length}<button data-a=swn>›</button></div>`:'';
 const thought=!u&&U.thoughts&&U.track&&m.thought?`<div class=thought>💭 ${esc(m.thought)}</div>`:'';
 const stat=m.stat?`${m.stat.tok} tokens · ${(m.stat.ms/1000).toFixed(1)}s`:'';
 return`<div class="m ${m.role}" data-i=${i}>${u?'':avatar(cur)}<div class=bub><div class=nm title="${at(stat)}">${esc(n)}${U.stamps&&m.ts?`<span class=ts>${hm(m.ts)}</span>`:''}</div>${acts}${think}${tx}${m.react?`<span class=rx>${m.react}</span>`:''}${thought}${sw}${seen}</div></div>`}
function draw(){skipTyping();head();const L=$('#log');if(!chat){L.innerHTML='';return}let h='',prev=0;
 hist.forEach((m,i)=>{if(m.ts&&(!prev||m.ts-prev>108e5||new Date(m.ts).toDateString()!=new Date(prev).toDateString()))h+=`<div class=sep>${dayLabel(m.ts)}</div>`;if(m.ts)prev=m.ts;h+=msgHTML(m,i)});
 L.innerHTML=h;if(ctl)showPending(pendLabel);L.scrollTop=L.scrollHeight}
function redrawMsg(i){const e=$(`.m[data-i="${i}"]`);if(e&&hist[i]){const t=document.createElement('div');t.innerHTML=msgHTML(hist[i],i);e.replaceWith(t.firstElementChild)}}
function head(){const c=cur||{name:'Character'},st=chat?.state;$('#hname').textContent=c.name||'Character';$('#hav').style.cssText=avs(c);
 $('#hav').innerHTML=avin(c)+(st&&U.track?`<span class=bd>${st.emoji}</span>`:'');setStatus(status);
 $('#hchip').hidden=!(U.track&&st);if(st){$('#hemo').textContent=st.emoji;$('#hmood').textContent=st.mood;$('#hmeter').style.width=st.affection+'%';$('#hstage').textContent=stg(st.affection)}
 $('#mode').value=chat?.cfg.mode||U.mode;$('#len').value=chat?.cfg.length||U.length}
function setStatus(t){status=t;$('#hstat').textContent=t;$('#hstat').classList.toggle('on',t!='online')}
function showPending(l){pendLabel=l;let e=$('#pend');if(!e){e=document.createElement('div');e.id='pend';e.className='m assistant';$('#log').append(e)}
 e.innerHTML=avatar(cur)+`<div class=bub><div class=nm>${esc(cur?.name||'Character')}</div><div class="tx dt"><div class=dots><i></i><i></i><i></i><span>${l}</span></div></div></div>`;
 const L=$('#log');L.scrollTop=L.scrollHeight}
const hidePending=()=>{pendLabel='';$('#pend')?.remove()};
const phase=l=>{setStatus(l);showPending(l)};
function errBox(msg,kind){const e=document.createElement('div');e.className='sys';e.innerHTML=`<span>⚠ ${esc(msg)}</span><button data-a=retry data-k=${kind}>Retry</button>`;$('#log').append(e);$('#log').scrollTop=1e9}
const busy=b=>{$('#send').hidden=b;$('#stop').hidden=!b};

/* ---------- typing animation (only runs once the whole reply exists) ---------- */
const KB={q:'wa',w:'qes',e:'wrd',r:'etf',t:'ryg',y:'tuh',u:'yij',i:'uok',o:'ipl',p:'ol',a:'qsz',s:'awdx',d:'sefc',f:'drgv',g:'fthb',h:'gyjn',j:'hukm',k:'jil',l:'ko',z:'asx',x:'zsc',c:'xdv',v:'cfb',b:'vgn',n:'bhm',m:'nj'};
const wrongKey=ch=>{const o=KB[ch.toLowerCase()]||'e',w=o[Math.floor(Math.random()*o.length)];return ch==ch.toUpperCase()?w.toUpperCase():w};
const autoscroll=()=>{const L=$('#log');if(L.scrollHeight-L.scrollTop-L.clientHeight<170)L.scrollTop=L.scrollHeight};
function skipTyping(){anim++;typingNow=false;$('#skip').hidden=true;if(!ctl)setStatus('online')}
async function typeEl(b,id,sf){
 const w=document.createTreeWalker(b,NodeFilter.SHOW_TEXT),ns=[];let x;while(x=w.nextNode())ns.push([x,x.data]);
 ns.forEach(([n])=>n.data='');
 const cps={fast:120,normal:55,slow:26}[U.typing]||55;let acc=0,t0=performance.now();
 for(const[n,f]of ns){let k=0;
  while(k<f.length){
   if(id!=anim||document.hidden){ns.forEach(([n,f])=>n.data=f);return}
   const t=performance.now();acc+=(t-t0)/1000*cps*(.55+Math.random()*.9);t0=t;
   let st=Math.floor(acc);if(st<1){await sleep(16);continue}
   acc-=st;let pz=0;
   while(st-->0&&k<f.length){const ch=f[k++],nx=f[k];pz=Math.max(pz,/[.!?]/.test(ch)&&(!nx||/\s/.test(nx))?260:ch=='…'?320:/[,;:]/.test(ch)?110:ch=='\n'?240:/[—–]/.test(ch)?150:0)}
   n.data=f.slice(0,k);autoscroll();
   if(U.typos&&chat?.cfg.mode=='text'&&k>1&&/\s/.test(f[k-1])&&/[a-z]/i.test(f[k]||'')&&/^\w{4}/.test(f.slice(k))&&Math.random()<.05){
    n.data=f.slice(0,k)+wrongKey(f[k]);await sleep(170+Math.random()*180);n.data=f.slice(0,k);await sleep(120);t0=performance.now();acc=0}
   if(pz){await sleep(pz*sf);t0=performance.now();acc=0}}}}
async function typeMsg(i){
 const el=$(`.m[data-i="${i}"]`),bs=$$(`.m[data-i="${i}"] .tx`);if(!el||!bs.length||U.typing=='instant'||document.hidden)return;
 const id=++anim,sf={fast:.5,normal:1,slow:1.7}[U.typing]||1;typingNow=true;$('#skip').hidden=false;setStatus('typing…');el.classList.add('fresh');
 bs.slice(1).forEach(b=>b.style.display='none');
 try{for(let j=0;j<bs.length;j++){if(id!=anim)break;
   if(j>0){const d=document.createElement('div');d.className='tx dt';d.innerHTML='<div class=dots><i></i><i></i><i></i></div>';bs[j].before(d);
    await sleep(Math.min(1800,350+bs[j].textContent.length*22)*sf);d.remove();if(id!=anim)break;bs[j].style.display='';beep(760,.06)}
   await typeEl(bs[j],id,sf)}
 }finally{bs.forEach(b=>b.style.display='');el.querySelectorAll('.tx.dt').forEach(d=>d.remove());if(id==anim){typingNow=false;$('#skip').hidden=true;setStatus('online')}}}

/* ---------- voice ---------- */
const speak=t=>{if(!('speechSynthesis' in window))return;speechSynthesis.cancel();
 const s=split(t).body.replace(/\*[^*]+\*/g,' ').replace(/\([^)]*\)/g,' ').replace(/[*_]/g,'').trim();if(!s)return;
 const u=new SpeechSynthesisUtterance(s),v=speechSynthesis.getVoices().find(v=>v.name==U.voice),g=cur?.gender||'';
 if(v)u.voice=v;u.rate=+U.rate||1;u.pitch=/\b(female|woman|girl|she)\b/i.test(g)?1.12:/\b(male|man|boy|he)\b/i.test(g)?.92:1;speechSynthesis.speak(u)};

/* ---------- chats ---------- */
async function pick(id){const c=S.chars.find(c=>c.id==id);if(!c)return;cur=c;renderChars();renderForm(cur);
 chats=(await api('/api/chats/'+id)).chats||[];chats.length?await openChat(chats[0].id):await newChat()}
async function openChat(chid){const r=await api(`/api/chat/${cur.id}/${chid}`);
 chat={id:chid,title:r.title,state:{...newState(),...(r.state||{})},cfg:{...newCfg(),...(r.cfg||{})}};hist=r.history||[];gi=0;lastAct=Date.now();nudges=0;
 $('#ctxm').textContent='';drawChats();draw();if(!$('#mem').hidden)renderMem()}
async function newChat(){chat={id:rid(),title:'New chat',state:newState(),cfg:newCfg()};gi=0;resetChat();await saveChat();draw()}
async function saveChat(){if(!cur?.id||!chat)return;const r=await api('/api/chat_save','POST',{cid:cur.id,id:chat.id,title:chat.title,history:hist,state:chat.state,cfg:chat.cfg});
 if(r.err)return;chat.title=r.title;const m={id:chat.id,title:chat.title,n:hist.length},i=chats.findIndex(c=>c.id==chat.id);i<0?chats.unshift(m):chats[i]=m;drawChats()}
const saveSoon=()=>{clearTimeout(saveT);saveT=setTimeout(saveChat,500)};
function drawChats(){$('#chsel').innerHTML=chats.map(c=>`<option value=${c.id} ${chat&&c.id==chat.id?'selected':''}>${esc(c.title)} (${c.n})</option>`).join('')}
function resetChat(i=0){const g=greetings(cur);hist=g.length?[{role:'assistant',content:g[i%g.length],ts:Date.now()}]:[]}
function restore(m){if(m?.snap){try{chat.state={...chat.state,...JSON.parse(m.snap)}}catch(e){}delete m.snap}}

/* ---------- generation: the whole reply is made first, then typed out ---------- */
const apiChar=()=>{const{avatar,...c}=cur;return c};
const apiHist=a=>a.filter(m=>m.content&&m.content.trim()).map(m=>({role:m.role,content:m.content,ts:m.ts,react:m.react}));
async function gen(kind='reply'){
 if(!cur?.id||!chat||ctl)return;skipTyping();
 const last=hist.at(-1),base=kind=='swipe'?hist.slice(0,-1):hist,lastU=[...base].reverse().find(m=>m.role=='user'),started=Date.now();
 ctl=new AbortController();busy(true);phase('reading…');
 const rt=setTimeout(()=>{if(pendLabel=='reading…')phase(S.role=='guest'?'waiting for the AI…':'typing…')},Math.min(1000,350+(lastU?lastU.content.split(' ').length*45:0)));
 const a=base.at(-1)?.ts,b=base.at(-2)?.ts;
 const gap=!U.timeaware?0:kind=='nudge'||kind=='continue'?(Date.now()-(a||Date.now()))/1000:(a&&b?(a-b)/1000:0);
 const s=chat.state,body={char:apiChar(),user:uname(),persona:U.persona,history:apiHist(base),kind:kind=='swipe'?'reply':kind,
  from:U.track&&s.summary?Math.max(0,Math.min(s.sumUpto,base.length-2)):0,state:U.track?{...s,log:undefined}:{},scene:chat.cfg.scene,
  clock:U.timeaware?clock():'',gap_s:gap,params:{...P,think:U.think,actions:U.actions,mode:chat.cfg.mode,length:chat.cfg.length,realism:U.realism,natural:U.natural}};
 let res=null,err='';
 try{const r=await fetch('/api/chat',{method:'POST',signal:ctl.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r.status==401){location.reload();return}
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  for(;;){const{done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
   while((i=buf.indexOf('\n\n'))>=0){const l=buf.slice(0,i);buf=buf.slice(i+2);if(!l.startsWith('data: ')||l.slice(6)=='[DONE]')continue;
    const j=JSON.parse(l.slice(6));if(j.q!=null)phase(j.q?`waiting in line (${j.q} ahead)…`:'waiting for the AI…');else if(j.p)phase(j.p=='think'?'thinking…':'typing…');else if(j.done)res=j.done;else if(j.err)err=j.err}}
 }catch(e){err=e.name=='AbortError'?'aborted':(e.message||'Connection lost')}
 clearTimeout(rt);const ab=ctl.signal.aborted;ctl=null;hidePending();busy(false);setStatus('online');
 if(ab){draw();return}
 if(!res||!res.text){draw();errBox(err||'The model returned nothing.',kind);return}
 let idx;const v={content:res.text,think:res.think,ts:Date.now(),stat:{tok:res.tok,ms:res.ms}};
 if(kind=='swipe'){restore(last);if(!last.sw)last.sw=[{content:last.content,think:last.think,ts:last.ts,stat:last.stat,thought:last.thought}];
  last.sw.push(v);last.si=last.sw.length-1;Object.assign(last,v,{thought:'',react:''});idx=hist.length-1}
 else if(kind=='continue'){last.content=last.content.trimEnd()+(chat.cfg.mode=='text'?'\n':'\n\n')+res.text;if(last.sw)last.sw[last.si].content=last.content;idx=hist.length-1}
 else{hist.push({role:'assistant',...v,seen:started,nudge:kind=='nudge'?1:undefined});idx=hist.length-1}
 $('#ctxm').textContent=(res.cut?'Reply hit the length cap and was trimmed to a full sentence. Use Continue for more. · ':'')+`prompt ${res.ctx_used.toLocaleString()} / ${res.ctx.toLocaleString()} tokens`+(res.dropped?` · ${res.dropped} oldest messages left out`:'');
 saveChat();draw();beep();lastAct=Date.now();
 if(U.tts)speak(hist[idx].content);
 await typeMsg(idx);lastAct=Date.now();
 trackState(idx)}
async function send(){const t=$('#inp').value.trim();if(!t||ctl||!cur?.id||!chat)return;skipTyping();window.speechSynthesis?.cancel();
 $('#inp').value='';$('#inp').style.height='';hist.push({role:'user',content:t,ts:Date.now()});beep(520,.05);nudges=0;lastAct=Date.now();draw();saveChat();await gen('reply')}

/* ---------- inner state + long-term memory (runs after the reply, never delays it) ---------- */
async function trackState(i){
 if(!U.track||!S.loaded||!chat)return;const ch=chat,m=hist[i];if(!m)return;
 const{log,...rest}=ch.state,snap=JSON.stringify(rest);
 try{const r=await api('/api/track','POST',{char:apiChar(),user:uname(),history:apiHist(hist.slice(Math.max(0,i-5),i+1)),state:ch.state});
  if(r.err||!r.state||chat!==ch||hist[i]!==m)return;
  m.snap=snap;m.thought=r.thought||'';hist.forEach((x,k)=>{if(k<i-6)delete x.snap});ch.state={...ch.state,...r.state};
  head();redrawMsg(i);saveChat();if(!$('#mem').hidden)renderMem();maybeSummarize()}catch(e){}}
async function maybeSummarize(force){
 if(!U.track||!S.loaded||!chat)return;const ch=chat,s=ch.state,upto=hist.length-12;
 if((!force&&hist.length-s.sumUpto<=30)||upto<=s.sumUpto)return;
 const r=await api('/api/summarize','POST',{char:apiChar(),user:uname(),history:apiHist(hist.slice(s.sumUpto,upto)),summary:s.summary});
 if(r.summary&&chat===ch){s.summary=r.summary;s.sumUpto=upto;saveChat();if(!$('#mem').hidden)renderMem()}return r}

/* ---------- message actions ---------- */
function editMsg(i){const m=hist[i],el=$(`.m[data-i="${i}"] .bub`);if(!el)return;
 el.innerHTML=`<textarea class=ed>${esc(m.content)}</textarea><div class=row><button class=go data-a=esave>Save</button><button data-a=ecancel>Cancel</button></div>`;el.querySelector('textarea').focus()}
$('#log').onclick=e=>{const b=e.target.closest('button');
 if(!b){const mm=e.target.closest('.m');if(typingNow&&mm)skipTyping();else if(mm&&touch.matches&&mm.id!='pend'){const on=mm.classList.contains('sel');$$('.m.sel').forEach(x=>x.classList.remove('sel'));if(!on)mm.classList.add('sel')}return}
 const a=b.dataset.a,mEl=b.closest('.m'),i=mEl?+mEl.dataset.i:-1,m=hist[i];if(!a)return;
 if(a=='retry'){b.closest('.sys').remove();return void gen(b.dataset.k)}
 if(!m)return;
 if(a=='copy')navigator.clipboard?.writeText(plain(m));
 else if(a=='edit')editMsg(i);
 else if(a=='ecancel')draw();
 else if(a=='esave'){const t=mEl.querySelector('textarea').value.trim();if(t){m.content=t;if(m.sw)m.sw[m.si].content=t}saveChat();draw()}
 else if(a=='react')b.closest('.acts').classList.toggle('open');
 else if(a=='rx'){m.react=m.react==b.dataset.e?'':b.dataset.e;saveChat();draw()}
 else if(a=='speak')speak(m.content);
 else if(a=='del'){restore(m);hist.splice(i,1);saveChat();draw()}
 else if(a=='rewind'){if(!confirm('Delete this message and everything after it?'))return;const gone=hist.splice(i);restore(gone.find(x=>x.snap));saveChat();draw();head()}
 else if(a=='swp'||a=='swn'){if(!m.sw)return;m.sw[m.si].thought=m.thought;const n=m.sw.length;m.si=(m.si+(a=='swn'?1:n-1))%n;const v=m.sw[m.si];
  Object.assign(m,{content:v.content,think:v.think,ts:v.ts||m.ts,stat:v.stat,thought:v.thought||''});saveChat();draw()}};

/* ---------- composer + toolbar ---------- */
$('#inp').oninput=e=>{lastAct=Date.now();e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,170)+'px'};
$('#send').onclick=send;$('#stop').onclick=()=>ctl&&ctl.abort();$('#skip').onclick=skipTyping;
$('#inp').onkeydown=e=>{if(e.key=='Enter'&&!e.shiftKey){e.preventDefault();send()}
 else if(e.key=='ArrowUp'&&!$('#inp').value){const i=hist.map(m=>m.role).lastIndexOf('user');if(i>=0){e.preventDefault();editMsg(i)}}};
document.addEventListener('keydown',e=>{if(e.key=='Escape'){if(ctl)ctl.abort();else skipTyping()}});
$('#regen').onclick=()=>{if(ctl||hist.length<2)return;gen(hist.at(-1).role=='assistant'?'swipe':'reply')};
$('#cont').onclick=()=>{if(ctl||!hist.length||hist.at(-1).role!='assistant')return;gen('continue')};
$('#undo').onclick=()=>{if(ctl)return;skipTyping();restore(hist.pop());draw();saveChat()};
$('#greet').onclick=()=>{if(ctl||hist.length>1)return;resetChat(++gi);draw();saveChat()};
$('#chsel').onchange=e=>{if(!ctl)openChat(e.target.value)};
$('#newchat').onclick=()=>{if(!ctl&&cur?.id)newChat()};
$('#rename').onclick=()=>{if(!chat)return;const t=prompt('Chat name',chat.title);if(t&&t.trim()){chat.title=t.trim();saveChat()}};
$('#delchat').onclick=async()=>{if(ctl||!chat||!confirm('Delete this chat?'))return;await api(`/api/chat/${cur.id}/${chat.id}`,'DELETE');
 chats=chats.filter(c=>c.id!=chat.id);chats.length?await openChat(chats[0].id):await newChat()};
$('#expchat').onclick=()=>{if(!chat)return;dl(hist.map(m=>`${m.role=='user'?uname():cur.name}: ${plain(m)}`).join('\n\n'),`${cur.name||'chat'} - ${chat.title}.txt`,'text/plain')};
$('#mode').onchange=e=>{if(!chat)return;chat.cfg.mode=U.mode=e.target.value;persist();saveChat();draw()};
$('#len').onchange=e=>{if(!chat)return;chat.cfg.length=U.length=e.target.value;persist();saveChat()};
$('#hchip').onclick=()=>tab('mem');
const closeDrawer=()=>document.body.classList.remove('drawer'),touch=matchMedia('(hover:none)');
$('#menu').onclick=()=>document.body.classList.toggle('drawer');$('#scrim').onclick=closeDrawer;$('#hmore').onclick=()=>$('.chead').classList.toggle('open');
let kbT=0;$('#inp').addEventListener('focus',()=>{clearTimeout(kbT);document.body.classList.add('kb');setTimeout(()=>{$('#log').scrollTop=1e9},250)});
$('#inp').addEventListener('blur',()=>{kbT=setTimeout(()=>document.body.classList.remove('kb'),200)});$('#send').onmousedown=e=>e.preventDefault();if(innerWidth<=760)$('#inp').placeholder='Message…';
if(window.visualViewport)visualViewport.addEventListener('resize',()=>{document.documentElement.style.setProperty('--vh',visualViewport.height+'px');scrollTo(0,0);const L=$('#log');if(document.body.classList.contains('kb'))L.scrollTop=L.scrollHeight});
$('#uname').oninput=e=>{U.uname=e.target.value;persist();cur&&draw()};$('#persona').oninput=e=>{U.persona=e.target.value;persist()};
function pills(){for(const[id,k]of[['#tthink','think'],['#tact','actions'],['#tthoughts','thoughts'],['#tvoice','tts']])$(id).classList.toggle('on',!!U[k]);persist()}
$('#tthink').onclick=()=>{U.think=!U.think;pills();draw()};$('#tact').onclick=()=>{U.actions=!U.actions;pills();draw()};
$('#tthoughts').onclick=()=>{U.thoughts=!U.thoughts;pills();draw();renderSettings()};$('#tvoice').onclick=()=>{U.tts=!U.tts;if(!U.tts)speechSynthesis?.cancel?.();pills();renderSettings()};
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;let rec=null;
if(SR){$('#mic').hidden=false;$('#mic').onclick=()=>{if(rec){rec.stop();return}rec=new SR();rec.lang=navigator.language;
 rec.onresult=e=>{const i=$('#inp');i.value+=(i.value?' ':'')+e.results[0][0].transcript;i.dispatchEvent(new Event('input'))};rec.onend=()=>{rec=null;$('#mic').classList.remove('on')};$('#mic').classList.add('on');rec.start()}}
/* the character may follow up on its own if you go quiet (Settings > Initiative) */
setInterval(()=>{if(!U.nudge||ctl||typingNow||!chat||!cur?.id||!S.loaded||document.hidden||$('#chat').hidden||nudges>=2)return;
 const l=hist.at(-1);if(!l||l.role!='assistant'||hist.length<2)return;
 if(Date.now()-Math.max(l.ts||0,lastAct)>U.nudge*6e4*(nudges+1)){nudges++;gen('nudge')}},10000);

/* ---------- characters ---------- */
function renderChars(){const q=($('#csearch').value||'').toLowerCase();
 $('#clist').innerHTML=S.chars.filter(c=>!q||[c.name,c.tags,c.description].join(' ').toLowerCase().includes(q)).map(c=>
  `<div class="ch ${cur&&cur.id==c.id?'on':''}" data-id=${c.id}>${avatar(c,'sm')}<span>${esc(c.name||'(unnamed)')}<small>${esc((c.tags||'').split(',').slice(0,3).join(' · '))}</small></span></div>`).join('')}
$('#clist').onclick=e=>{const d=e.target.closest('.ch');if(d){pick(d.dataset.id);closeDrawer();tab('chat')}};$('#csearch').oninput=renderChars;
function renderForm(c){let h='';for(const[sec,fs]of S.schema){h+=`<details ${sec=='Core'?'open':''}><summary>${sec}</summary>`;
 for(const[k,l,r]of fs)h+=`<label>${l}</label><textarea data-k=${k} rows=${r}>${esc(c[k]||'')}</textarea>`;h+='</details>'}
 h+=`<details><summary>Lorebook (inserted when a key appears in the last few messages; no keys = always)</summary><div id=lore></div><button id=addlore>Add entry</button></details>`;
 $('#form').innerHTML=h;$('#lore').innerHTML='';(c.lore||[]).forEach(loreRow);$('#addlore').onclick=()=>loreRow({keys:'',content:''});avPrev(c)}
function avPrev(c){$('#eav').style.cssText=avs(c);$('#eav').textContent=c.avatar?'':ini(c.name)}
function loreRow(e){const d=document.createElement('div');d.className='lore';
 d.innerHTML=`<input placeholder="keys, comma separated" value="${at(e.keys||'')}"><textarea rows=3 placeholder="Entry text">${esc(e.content||'')}</textarea><button class=x>Remove</button>`;
 d.querySelector('button').onclick=()=>d.remove();$('#lore').append(d)}
function collect(){const c={id:cur?.id||'',avatar:cur?.avatar||''};$$('[data-k]').forEach(e=>c[e.dataset.k]=e.value);
 c.lore=[...$$('.lore')].map(d=>({keys:d.children[0].value,content:d.children[1].value}));return c}
function openNew(){cur=blank();hist=[];chat=null;chats=[];drawChats();draw();renderForm(cur);renderChars();tab('editor')}
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
$('#file').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;
 try{const png=f.name.toLowerCase().endsWith('.png'),j=png?await pngCard(await f.arrayBuffer()):JSON.parse(await f.text());const d=j.data||j,x=d.extensions?.hearth||{},c=blank();
  Object.assign(c,x);c.name=d.name||'';c.description=d.description||'';c.personality=d.personality||'';c.scenario=d.scenario||'';c.first_mes=d.first_mes||'';
  c.mes_example=d.mes_example||'';c.system_prompt=d.system_prompt||'';c.post_history=d.post_history_instructions||'';c.notes=d.creator_notes||'';
  c.alts=(d.alternate_greetings||[]).join('\n---\n');c.tags=(d.tags||[]).join(', ');
  c.lore=(d.character_book?.entries||[]).map(e=>({keys:(e.keys||[]).join(', '),content:e.content||''}));
  if(png&&!c.avatar)try{c.avatar=await shrink(f)}catch(x){}
  cur=c;hist=[];chat=null;chats=[];drawChats();renderForm(c);tab('editor')}catch(err){alert('Import failed: '+err.message)}};
$('#exp').onclick=()=>{const c=collect(),ex={};S.ext.forEach(k=>ex[k]=c[k]);if(c.avatar)ex.avatar=c.avatar;
 const card={spec:'chara_card_v2',spec_version:'2.0',data:{name:c.name,description:c.description,personality:c.personality,scenario:c.scenario,first_mes:c.first_mes,
  mes_example:c.mes_example,system_prompt:c.system_prompt,post_history_instructions:c.post_history,creator_notes:c.notes,
  alternate_greetings:(c.alts||'').split(/\n-{3,}\n/).map(s=>s.trim()).filter(Boolean),tags:(c.tags||'').split(',').map(s=>s.trim()).filter(Boolean),
  character_book:{entries:c.lore.map((e,i)=>({id:i,keys:e.keys.split(',').map(s=>s.trim()).filter(Boolean),content:e.content,enabled:true,insertion_order:i}))},
  extensions:{hearth:ex}}};dl(JSON.stringify(card,null,1),(c.name||'character')+'.json','application/json')};

/* ---------- memory tab: mood, relationship, scene, summary, facts ---------- */
function renderMem(){const f=$('#memf'),st=chat?.state;if(!chat||!st){f.innerHTML='<p class=small>Open a chat first.</p>';return}
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
  <details open><summary>What ${n} knows about you</summary><div id=mfacts>${st.facts.map((x,i)=>`<div class=fact><input data-m=fact data-i=${i} value="${at(x)}"><button class=x data-m=delfact data-i=${i}>✕</button></div>`).join('')||'<p class=small>Nothing yet. Facts are picked up from the conversation.</p>'}</div>
  <div class=row><input id=newfact placeholder="Add a fact…"><button data-m=addfact>Add</button></div></details>
  <details><summary>Inner thoughts and mood history</summary>${(st.log||[]).slice(-12).reverse().map(l=>`<div class=tl>${l.emoji} <b>${esc(l.mood)}</b> · ${l.aff}/100 · ${hm(l.ts)}<br>${esc(l.thought||'')}</div>`).join('')||'<p class=small>Nothing yet.</p>'}</details>`}
$('#memf').oninput=e=>{const k=e.target.dataset.m,st=chat?.state;if(!k||!st)return;const v=e.target.value;
 if(k=='affection'){st.affection=+v;$('#mstage').textContent=`${stg(st.affection)} (${v})`}
 else if(k=='scene')chat.cfg.scene=v;else if(k=='summary')st.summary=v;else if(k=='fact')st.facts[+e.target.dataset.i]=v;else return;head();saveSoon()};
$('#memf').onchange=e=>{const k=e.target.dataset.m,st=chat?.state;if(!st)return;
 if(k=='mood'){st.mood=e.target.value;st.emoji=S.emo[st.mood]||'🙂'}else if(k=='energy')st.energy=e.target.value;else return;head();saveSoon()};
$('#memf').onclick=async e=>{const b=e.target.closest('button'),k=b?.dataset.m,st=chat?.state;if(!k||!st)return;
 if(k=='reset'){Object.assign(st,{mood:'neutral',emoji:'😐',energy:'medium',affection:50,log:[]})}
 else if(k=='delfact')st.facts.splice(+b.dataset.i,1);
 else if(k=='addfact'){const v=$('#newfact').value.trim();if(!v)return;st.facts.push(v)}
 else if(k=='sumnow'){$('#msum').textContent='Summarizing…';const r=await maybeSummarize(true);$('#msum').textContent=r?.err||(r?.summary?'Done.':'Not enough history yet.');if(r?.summary)return}
 else return;head();saveSoon();renderMem()};

/* ---------- settings tab ---------- */
const SET=[['Realism',[
 ['realism','chk','Realism rules','Every prompt tells the character to talk like a real person: contractions, opinions, moods, no assistant-speak, no repeated openings.'],
 ['natural','sel','Speech naturalness',[[0,'Off'],[1,'Subtle'],[2,'Natural'],[3,'Messy']],'Fillers, self-corrections, trailing off, tangents.'],
 ['timeaware','chk','Time awareness','The character knows the date, the time of day and how long it has been since you last spoke.'],
 ['track','chk','Emotions and memory','After each reply the character updates its mood, how it feels about you, and remembers facts about you. Long chats are summarised automatically.'],
 ['thoughts','chk','Show inner thoughts','A private thought under each message (needs Emotions and memory).'],
 ['nudge','sel','Initiative',[[0,'Off'],[1,'After 1 min of silence'],[3,'After 3 min'],[10,'After 10 min']],'The character follows up on its own if you go quiet (at most twice in a row).']]],
 ['Typing and sound',[
 ['typing','sel','Typing animation',[['instant','Instant'],['fast','Fast'],['normal','Normal'],['slow','Slow']],'Text only starts appearing once the whole reply has been generated. Click a message or press Esc to skip.'],
 ['typos','chk','Typing mistakes in texting mode','Now and then a typo appears and gets corrected, like a real person on a phone.'],
 ['stamps','chk','Timestamps and read receipts',''],['sound','chk','Message sounds',''],['tts','chk','Read replies aloud',''],
 ['voice','voice','Voice'],['rate','rng','Speech rate',[.6,1.6,.05]]]],
 ['Appearance',[['theme','sel','Theme',[['dark','Dark'],['light','Light']],''],['fs','rng','Text size',[12,22,1]]]]];
const PD={temperature:'Higher is more creative and less predictable.',top_p:'Nucleus sampling cut-off.',top_k:'Only consider the K likeliest tokens.',min_p:'Drops very unlikely tokens.',
 repeat_penalty:'Discourages repeating words.',presence_penalty:'Nudges toward new topics.',frequency_penalty:'Reduces repeated words.',
 max_tokens:'Hard cap for one reply. Replies are asked to be shorter than this and are never left half-finished.',seed:'-1 picks a random seed.'};
function renderSettings(){let h='';
 for(const[sec,items]of SET){h+=`<details open><summary>${sec}</summary>`;
  for(const[k,t,l,o,hint]of items){const hn=t=='sel'||t=='rng'?hint:o;
   if(t=='chk')h+=`<label class=chk><input type=checkbox data-u=${k} ${U[k]?'checked':''}><span>${l}${hn?`<small>${hn}</small>`:''}</span></label>`;
   else if(t=='sel')h+=`<label>${l}</label><select data-u=${k}>${o.map(([v,x])=>`<option value="${v}" ${String(U[k])==String(v)?'selected':''}>${x}</option>`).join('')}</select>${hn?`<div class=small>${hn}</div>`:''}`;
   else if(t=='rng')h+=`<label>${l}: <b>${U[k]}</b></label><input type=range data-u=${k} min=${o[0]} max=${o[1]} step=${o[2]} value=${U[k]}>`;
   else if(t=='voice')h+=`<label>${l}</label><select data-u=voice><option value="">(default)</option>${(window.speechSynthesis?speechSynthesis.getVoices():[]).map(v=>`<option ${v.name==U.voice?'selected':''}>${esc(v.name)}</option>`).join('')}</select>`}
  h+='</details>'}
 if(S.role!='guest')h+=`<details open><summary>Generation</summary>${Object.entries(P).map(([k,v])=>typeof v=='boolean'?
  `<label class=chk><input type=checkbox data-p=${k} ${v?'checked':''}><span>Fold the greeting into the system prompt<small>For models whose template rejects an assistant-first chat.</small></span></label>`:
  `<label>${k}${PD[k]?' - '+PD[k]:''}</label><input type=number step=any data-p=${k} value=${v}>`).join('')}</details>`;
 $('#sform').innerHTML=h}
$('#sform').oninput=$('#sform').onchange=e=>{const t=e.target,k=t.dataset.u,p=t.dataset.p;
 if(p){P[p]=t.type=='checkbox'?t.checked:+t.value;persist();return}if(!k)return;
 U[k]=t.type=='checkbox'?t.checked:typeof D[k]=='number'?+t.value:t.value;if(t.type=='range')t.previousElementSibling.querySelector('b').textContent=t.value;
 persist();applyUI();if(['think','thoughts','stamps','track'].includes(k)){draw()}};
function applyUI(){document.documentElement.dataset.theme=U.theme;document.documentElement.style.setProperty('--fs',U.fs+'px');pills()}
if('speechSynthesis' in window)speechSynthesis.onvoiceschanged=()=>{if(S)renderSettings()};

$('#load').onclick=async()=>{const path=$('#mpath').value.trim()||$('#msel').value;if(!path)return;$('#mstat').textContent='Loading (this can take a while)...';
 const r=await api('/api/load','POST',{path,n_ctx:$('#nctx').value,n_gpu:$('#ngl').value});if(!r.err)S.loaded=r.loaded;$('#mstat').textContent=r.err?'Error: '+r.err:'Loaded: '+r.loaded+(S.gpu?' (GPU)':' - CPU ONLY build')};
function tab(t){closeDrawer();if(t=='samp')renderShare(true);$$('nav button').forEach(b=>b.classList.toggle('on',b.dataset.t==t));
 for(const id of['chat','editor','mem','samp'])$('#'+id).hidden=id!=t;if(t=='mem')renderMem();if(t=='chat'){const L=$('#log');L.scrollTop=L.scrollHeight}}
document.querySelector('nav').onclick=e=>e.target.dataset.t&&tab(e.target.dataset.t);

async function init(){S=await api('/api/state');
 $('#msel').innerHTML='<option value="">(choose from ./models)</option>'+S.models.map(m=>`<option>${esc(m)}</option>`).join('');
 $('#mstat').textContent=S.backend?((S.loaded?'Loaded: '+S.loaded:'No model loaded')+(S.gpu?' (GPU)':' - CPU ONLY build: see the console to enable the GPU')):'llama-cpp-python missing: pip install llama-cpp-python';
 document.body.classList.toggle('guest',S.role=='guest');if(S.role=='guest'&&(!U.uname||U.uname=='User'))U.uname=S.name;
 $('#uname').value=U.uname;$('#persona').value=U.persona;renderChars();renderSettings();applyUI();
 if(S.chars[0])await pick(S.chars[0].id);else openNew()}
/* ---------- hosting panel (host only) ---------- */
async function renderShare(force){if(S.role!='admin')return;const box=$('#sharebox');
 if(!force&&box.contains(document.activeElement)&&document.activeElement.tagName=='INPUT')return;
 const r=await api('/api/share');if(r.err)return;const ago=t=>{const s=Date.now()/1000-t;return s<90?'online now':s<3600?Math.round(s/60)+' min ago':s<86400?Math.round(s/3600)+' h ago':Math.round(s/86400)+' d ago'};
 box.innerHTML=`<details open><summary>🌐 Share with others</summary>`+(!r.listen?
  `<p class=small>Right now Crumble only listens on this PC. To let friends use your AI, close it and start it with <b>python Crumble.py --share</b> (or double-click <b>Share.bat</b> on Windows, <b>share.sh</b> on Mac/Linux). They open your link, enter the password, and chat. Your model stays on your PC.</p>`:
  `<div class=row><b>${r.on?'🟢 Guests can join':'⚪ Sharing is paused'}</b><button class="${r.on?'x':'go'}" data-sh=toggle>${r.on?'Stop sharing':'Start sharing'}</button></div>
  <label>Link for guests (same Wi-Fi / network)</label>${r.urls.map(u=>`<div class=fact><input readonly value="${at(u)}"><button data-sh=copy data-v="${at(u)}">Copy</button></div>`).join('')||'<p class=small>No network address found.</p>'}
  <label>Password (empty = anyone with the link can join)</label><div class=fact><input id=shpw value="${at(r.password)}"><button data-sh=setpw>Save</button><button data-sh=regen>Random</button></div>
  <label>Most guests at once</label><input type=number id=shmax min=1 max=100 value=${r.max} data-sh=max>
  <label>Guests (${r.guests.length}) · ${r.queue?r.queue+' waiting for the AI':'AI is free'}</label>
  ${r.guests.map(g=>`<div class=fact><input readonly value="${at(g.name)} · ${ago(g.seen)}${g.busy?' · generating':''}"><button class=x data-sh=kick data-v=${g.uid}>Kick</button></div>`).join('')||'<p class=small>Nobody has joined yet.</p>'}
  ${r.guests.length?'<div class=row><button class=x data-sh=kickall>Kick everyone</button></div>':''}
  <details><summary>Playing over the internet</summary><p class=small>Same Wi-Fi works as is. For friends elsewhere, the safest way is a tunnel such as <b>cloudflared</b> (<code>cloudflared tunnel --url http://localhost:8000</code>) or <b>ngrok</b>: you get an https link to send them and no router setup. Port-forwarding also works but is plain http, so use a strong password. Everyone shares one model, so replies queue up; guests can chat and keep their own private chats, but cannot load models, edit characters or see character secrets.</p></details>`)+`</details>`}
$('#sharebox').onclick=async e=>{const b=e.target.closest('button'),k=b?.dataset.sh;if(!k)return;let body=null;
 if(k=='copy'){navigator.clipboard?.writeText(b.dataset.v);b.textContent='Copied';return}
 if(k=='toggle')body={on:!(b.textContent=='Stop sharing')};else if(k=='setpw')body={password:$('#shpw').value};else if(k=='regen')body={regen:1};
 else if(k=='kick')body={kick:b.dataset.v};else if(k=='kickall'){if(!confirm('Kick all guests?'))return;body={kick:'all'}}
 const r=await api('/api/share','POST',body);if(r.err)alert(r.err);renderShare(true)};
$('#sharebox').onchange=async e=>{if(e.target.dataset.sh=='max'){await api('/api/share','POST',{max:+e.target.value});renderShare(true)}};
setInterval(()=>{if(S&&S.role=='admin'&&!$('#samp').hidden)renderShare()},4000);
init();
</script></html>
"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Crumble: local character chat. Add --share to let other people use your AI.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--share", action="store_true", help="listen on your network so friends can join (asks them for a password)")
    ap.add_argument("--password", help="guest password (default: random, remembered in data/share.json)")
    ap.add_argument("--no-password", action="store_true", help="let anyone with the link in, no password")
    ap.add_argument("--model", help="load this .gguf at startup (default: the model you used last time)")
    ap.add_argument("--max-guests", type=int, help="most guests allowed (default 8)")
    a = ap.parse_args()
    saved = rj(SHAREF, {}) or {}
    SHARE.update(port=a.port, max=a.max_guests or saved.get("max", 8), listen=a.share or a.host not in ("127.0.0.1", "localhost", "::1"))
    SHARE["on"] = SHARE["listen"]
    if SHARE["on"]:
        SHARE["password"] = "" if a.no_password else (a.password or saved.get("password") or secrets.token_urlsafe(6))
        save_share()
    _gpu, _ver = gpu_status()
    if Llama is not None:
        print(f"llama-cpp-python {_ver}: GPU offload " + ("AVAILABLE" if _gpu else "NOT available"))
        if not _gpu:
            print(GPU_HELP)
    last = rj(ROOT/"data"/"last_model.json", {}) or {}
    mp = a.model or last.get("path")
    if mp and Llama is not None and Path(mp).exists():
        print(f"Loading model {mp} ... (this can take a while)")
        try:
            # CHANGE n_gpu_layers to -1 here
            LLM["obj"] = Llama(model_path=mp, n_ctx=int(last.get("n_ctx", 8192)), n_gpu_layers=-1, verbose=LLM_VERBOSE)
            LLM["path"], LLM["n_ctx"] = mp, int(last.get("n_ctx", 8192))
            wj(ROOT/"data"/"last_model.json", {"path": mp, "n_ctx": LLM["n_ctx"], "n_gpu": -1})
            print("Model ready." + ("  (running on the GPU)" if gpu_status()[0] else "  (running on the CPU)"))
        except Exception as e:
            print("Could not load the model:", e)
    elif a.share:
        print("No model loaded yet. Load one from the sidebar on this PC before guests chat.")
    host = "0.0.0.0" if a.share and a.host == "127.0.0.1" else a.host
    url = f"http://127.0.0.1:{a.port}"
    print(f"Crumble running at {url}  (models in {MODELS})")
    if SHARE["on"]:
        print("\n  SHARING IS ON. Others can open:")
        for u in lan_urls(a.port) or [f"http://<this-pc-ip>:{a.port}"]:
            print("    " + u)
        print(f"  Password: {SHARE['password'] or '(none)'}   Max guests: {SHARE['max']}")
        print("  Same Wi-Fi/LAN works as is. For the internet use a tunnel (cloudflared / ngrok) or port-forward; the tunnel gives you https.")
        print("  Manage guests from the Settings tab on this PC.\n")
    threading.Timer(.8, lambda: webbrowser.open(url)).start()
    srv = ThreadingHTTPServer((host, a.port), H)
    srv.daemon_threads = True
    srv.serve_forever()
