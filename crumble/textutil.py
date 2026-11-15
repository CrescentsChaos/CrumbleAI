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
    body = re.sub(r"<think>.*?(?:</think>|$)", "", t, flags=re.S).strip()
    leak, body = split_plan(body)
    return "\n".join(x for x in (th.strip(), leak) if x), body, is_open


_PLAN_HEAD = re.compile(r"(?is)^\s*[#>\s]*[\*_]*(?:(?:thinking|thought)\s+process|thinking|reasoning|analysis|planning)[\*_]*\s*:|^\s*1[.)]\s*\**\s*(?:analy[sz]e|understand|identify|review)\b[^\n]{0,40}:")
_REPLY_MARK = re.compile(r"(?im)^[ \t]*[\[\*#_>(]*[ \t]*(?:final[ \t]+|actual[ \t]+)?(?:in[- ]character[ \t]+)?(?:reply|response|answer|output|draft)[ \t]*[\]\*_)]*[ \t]*:?[ \t]*[\]\*_)]*[ \t]*")


def split_plan(body):
    """The model wrote its reasoning in the visible text ('Thinking Process: 1. Analyze the Request ... [Reply] ...').
    Return (leaked reasoning, the real reply). The reply is empty when no marker shows where it starts."""
    if not _PLAN_HEAD.match(body or ""):
        return "", body
    marks = list(_REPLY_MARK.finditer(body))
    if not marks:
        return body.strip(), ""
    m = marks[-1]
    return body[:m.start()].strip(), body[m.end():].strip()


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


_META_LEAD = [
    # "Here is a reply that stays in character as Faith:" (must be a line of its own that ends in a colon)
    re.compile(r"^\s*[\*\(\[_>]*\s*(?:here(?:'s| is| are)|below is|this is)\b[^\n:]{0,90}?\b(?:repl(?:y|ies)|response|answer|continuation)\b[^\n:]{0,90}:[\*\)\]_]*[ \t]*(?:\n|$)", re.I),
    re.compile(r"^\s*[\*\(\[_>]*\s*(?:here(?:'s| is)|below is)\s+(?:a|the|my)\s+(?:in[- ]character\s+)?(?:reply|response)\b[^\n:]{0,60}?(?:in[- ]character|as [A-Z][\w' -]{0,30})[^\n:]{0,30}:[\*\)\]_]*[ \t]*", re.I),
    re.compile(r"^\s*[\*\(\[_>]*\s*(?:(?:my |the |a )?(?:in[- ]character )?(?:reply|response|answer|output)|in[- ]character)(?: as [A-Z][^\n:]{0,40})?[\*\)\]_]*:[ \t]*(?:\n|$)", re.I),
]
_META_TAIL = re.compile(r"(?is)(?:\n+|\s{2,})[\*\(\[_>-]*\s*(?:note|ooc|disclaimer|this (?:reply|response|message)|the (?:above|reply|response)|i (?:stayed|kept|have kept|made sure|tried to)|(?:and )?many thoughts)\b.*$")


def strip_meta(b):
    """Remove 'Here is a reply that stays in character as X:' style prefaces and trailing notes the model sometimes adds."""
    for _ in range(3):
        n = b
        for rx in _META_LEAD:
            b = rx.sub("", b, count=1)
        if b == n:
            break
    return _META_TAIL.sub("", b).strip()


def clean_body(body, user, name, mode, others=()):
    b = body.replace("\r", "")
    b = strip_meta(b)
    b = re.sub(r"^\s*\**" + re.escape(name) + r"\**\s*:\s*", "", b)
    b = strip_meta(b)
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


TEXT_LINES = {"short": 2, "medium": 3, "long": 5, "auto": 4}   # most separate text messages (lines) in texting mode


def cap_reply(text, mode, length, hi):
    """Enforce the Length setting after the fact: models often ignore the limit in the prompt.
    Texting: at most N lines. Other modes with a fixed length: cut back to a whole sentence near the word limit."""
    if not text:
        return text
    if mode == "text":
        lines = [l for l in text.split("\n") if l.strip()]
        n = TEXT_LINES.get(length, 4)
        if len(lines) > n:
            text = "\n".join(lines[:n])
    if length in ("short", "medium") and len(text.split()) > hi * 1.5:
        words, out = 0, []
        for sent in re.split(r"(?<=[.!?…])\s+", text):
            w = len(sent.split())
            if out and words + w > hi * 1.3:
                break
            out.append(sent)
            words += w
        text = " ".join(out)
    return balance(text)


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
