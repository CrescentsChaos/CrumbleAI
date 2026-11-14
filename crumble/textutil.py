"""Small text helpers: <think> handling, reply clean-up, repetition checks, JSON recovery."""
import difflib
import json
import random
import re

from .config import CH, STAGES, STOPW, US


def sub(t, c, u):
    return (t or "").replace(CH, c.get("name") or "Character").replace(US, u)


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


def clean_body(body, user, name, mode, others=()):
    b = body.replace("\r", "")
    b = re.sub(r"^\s*\**" + re.escape(name) + r"\**\s*:\s*", "", b)
    m = re.search(r"(?im)^\s*\**" + re.escape(user) + r"\**\s*:", b)  # the model started writing the user's turn
    if m:
        b = b[:m.start()]
    for o in others:  # the model started writing someone else's turn
        m = re.search(r"(?im)^\s*\**" + re.escape(o) + r"\**\s*:", b)
        if m:
            b = b[:m.start()]
    b = re.sub(r"(?m)^\s*\[(?:Style|Realism|Right now|Format|Voice|Personality)[^\]]*\].*$", "", b)
    if mode != "story":  # no narration in texting / voice mode (short *emphasis* is kept)
        b = re.sub(r"\*+([^*\n]+)\*+", lambda m: m[0] if len(m[1].split()) < 3 else "", b)
        b = re.sub(r"(?m)^\s*[\"“](.*)[\"”]\s*$", r"\1", b)
    b = re.sub(r"[ \t]+\n", "\n", b)
    b = re.sub(r"\n{3,}", "\n\n", b)
    if mode == "text":
        b = "\n".join(l.strip() for l in b.split("\n") if l.strip())
    return b.strip()


def finish_reply(raw, finish, user, name, mode, others=()):
    th, body, think_open = split_think(raw)
    body = clean_body(body, user, name, mode, others)
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
