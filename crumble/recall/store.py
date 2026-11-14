"""The memory store that lives inside a character's chat state (state["mem"]).

    short-term   mem["scene"], mem["recent"]   the scene as it is right now + the last few events (small ring buffer)
    episodic     items with t="episodic"       things that happened between the character and the user
    semantic     items with t="semantic"       lasting facts: about the user ("user"), the character ("self"), their bond ("bond")
    emotional    items with t="emotional"      how the character remembers feeling about an experience (linked to an episode)

Everything is plain JSON, so it is saved with the chat, is private per chat (and per guest), and can be edited by hand.
Texts are stored with {{user}} / {{char}} placeholders, so renaming either of them later keeps old memories correct.
"""
import difflib
import re
import time

from . import lexicon as lx

TYPES = ("episodic", "semantic", "emotional")
CAPS = {"episodic": 120, "semantic": 80, "emotional": 80}
RECENT_MAX = 8
SUBJECTS = ("user", "self", "bond")
_POLARITY = (("pos", lx.LIKE_WORDS), ("neg", lx.DISLIKE_WORDS))


def blank():
    return {"v": 1, "seq": 0, "turn": 0, "scene": "", "recent": [], "items": [], "legacy": False}


def now_ms():
    return int(time.time() * 1000)


def _num(x, default, cast=float):
    try:
        return cast(x)
    except (TypeError, ValueError):
        return default


def _sane(i):
    """Hand-edited or foreign data must never break a reply: coerce the numeric fields."""
    i["text"], i["id"] = str(i["text"]), str(i.get("id") or "x")
    i["imp"] = max(0.0, min(1.0, _num(i.get("imp"), .5)))
    if i.get("t") == "emotional" or "val" in i or i.get("emo"):
        i["val"] = max(-1.0, min(1.0, _num(i.get("val"), 0.0)))
    for k in ("turn", "n", "last", "ts"):
        i[k] = _num(i.get(k), 0, int)
    i["pin"] = bool(i.get("pin"))
    if not isinstance(i.get("people"), list):
        i["people"] = []
    return i


def ensure(st, user="", char=""):
    """Make st["mem"] valid (in place) and fold the old flat facts list in, once. Returns it."""
    m = st.get("mem")
    if not isinstance(m, dict):
        m = st["mem"] = blank()
    for k, v in blank().items():
        m.setdefault(k, v)
    m["items"] = [_sane(i) for i in m["items"] if isinstance(i, dict) and i.get("t") in TYPES and str(i.get("text", "")).strip()]
    if not m["legacy"]:
        m["legacy"] = True
        for f in st.get("facts") or []:
            f = placeholders(f, user, char)
            if f:
                add(m, "semantic", f, subj="user", imp=.5, src="legacy", ts=0)
    return m


def placeholders(text, user, char):
    """Real names -> {{user}} / {{char}} so the memory survives a rename."""
    t = str(text or "").strip()
    for name, ph in ((user, "{{user}}"), (char, "{{char}}")):
        for n in sorted({x for x in (name or "", (name or "").split(" ")[0]) if len(x) >= 2}, key=len, reverse=True):
            t = re.sub(r"(?<![\w{])" + re.escape(n) + r"(?![\w}])", ph, t)
    return re.sub(r"\s+", " ", t).strip()


def resolve(text, user, char):
    return str(text or "").replace("{{user}}", user or "User").replace("{{char}}", char or "Character")


def _polarity(text):
    t = text.lower()
    for p, words in _POLARITY:
        if any(w in t for w in words):
            return p
    return None


def similar(a, b):
    """0..1 — how close two memory texts are, by their content words ("a necklace" and "a bracelet" are different gifts;
    the same sentence with other punctuation or filler words is the same memory)."""
    sa, sb = set(lx.terms(a)), set(lx.terms(b))
    if sa and sb:
        return len(sa & sb) / len(sa | sb)
    clean = lambda t: re.sub(r"[^\w]+", " ", t.lower()).strip()      # nothing but filler words: compare the raw text
    return 1.0 if difflib.SequenceMatcher(None, clean(a), clean(b)).ratio() >= .9 else 0.0


def _find_twin(m, t, text, subj):
    for i in m["items"]:
        if i["t"] != t or (t == "semantic" and i.get("subj") != subj):
            continue
        if similar(i["text"], text) >= (.66 if t == "episodic" else .7):
            return i, "same"
        if t == "semantic":   # "likes coffee" then "hates coffee": the newer statement replaces the old
            pa, pb = _polarity(i["text"]), _polarity(text)
            if pa and pb and pa != pb and set(lx.terms(i["text"])) & set(lx.terms(text)) - {lx.stem(w) for w in "likes loves enjoys prefers hates dislikes".split()}:
                return i, "flip"
    return None, ""


def add(m, t, text, *, subj="user", imp=.5, emo="", val=0.0, people=(), link="", turn=None, ts=None, src="auto", pin=False):
    """Add one memory, merging into a near-duplicate instead of piling up. Returns (item, created)."""
    text = str(text or "").strip().strip('"')
    if t not in TYPES or len(text) < 4:
        return None, False
    text = text[:240]
    imp = max(0.0, min(1.0, float(imp)))
    old, how = _find_twin(m, t, text, subj)
    if old:
        old["imp"] = round(min(1.0, max(old.get("imp", .5), imp) + (.04 if how == "same" else 0)), 3)
        if how == "flip" or (len(text) > len(old["text"]) and src != "legacy"):
            old["text"] = text
        old["pin"] = bool(old.get("pin") or pin)
        old["people"] = sorted(set(old.get("people") or []) | set(people or []))
        if emo and not old.get("emo"):
            old["emo"], old["val"] = emo, round(float(val), 2)
        return old, False
    m["seq"] += 1
    item = {"id": f"{t[0]}{m['seq']}", "t": t, "text": text, "imp": round(imp, 3), "ts": now_ms() if ts is None else ts,
            "turn": m["turn"] if turn is None else turn, "n": 0, "last": 0, "pin": bool(pin), "src": src}
    if t == "semantic":
        item["subj"] = subj if subj in SUBJECTS else "user"
    if people:
        item["people"] = sorted({str(p).strip() for p in people if str(p).strip()})[:5]
    if t == "emotional":
        item.update(emo=emo or "", val=round(float(val), 2))
        if link:
            item["link"] = link
    elif emo:
        item.update(emo=emo, val=round(float(val), 2))
    m["items"].append(item)
    return item, True


def keep_score(i, turn):
    age = max(0, turn - i.get("turn", 0))
    return (9.0 if i.get("pin") else 0.0) + i.get("imp", .5) + .25 * (.5 ** (age / 150)) + .06 * min(i.get("n", 0), 5)


def compact(m, turn=None):
    """Keep each layer under its cap by dropping the least important, oldest, never-recalled memories (pinned ones stay)."""
    turn = m.get("turn", 0) if turn is None else turn
    for t, cap in CAPS.items():
        mine = [i for i in m["items"] if i["t"] == t]
        if len(mine) > cap:
            drop = {i["id"] for i in sorted(mine, key=lambda i: keep_score(i, turn))[:len(mine) - cap]}
            m["items"] = [i for i in m["items"] if i["id"] not in drop]
    return m


def push_recent(m, text, imp, turn):
    """Short-term events; returns the ones that just fell out of the buffer (candidates for promotion to episodic)."""
    text = str(text or "").strip()
    out = []
    if len(text) >= 6 and not any(similar(r["text"], text) >= .75 for r in m["recent"]):
        m["recent"].append({"text": text[:160], "imp": round(float(imp), 2), "turn": turn, "ts": now_ms()})
    while len(m["recent"]) > RECENT_MAX:
        out.append(m["recent"].pop(0))
    return out


def touch(m, ids, turn):
    """Recalling a memory strengthens it a little (counts toward its importance when pruning and ranking)."""
    ids = set(ids or [])
    for i in m["items"]:
        if i["id"] in ids:
            i["n"] = i.get("n", 0) + 1
            i["last"] = turn


def remove(m, ids):
    ids = set(ids or [])
    m["items"] = [i for i in m["items"] if i["id"] not in ids]
    for i in m["items"]:
        if i.get("link") in ids:
            i.pop("link", None)


def user_facts_mirror(m, limit=40):
    """The old flat facts list, derived from semantic memory, so switching the new system off keeps what was learned."""
    mine = [i for i in m["items"] if i["t"] == "semantic" and i.get("subj", "user") == "user"]
    return [i["text"] for i in sorted(mine, key=lambda i: (i.get("ts", 0), i["id"]))[-limit:]]
