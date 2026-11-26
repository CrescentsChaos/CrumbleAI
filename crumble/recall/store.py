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
SUBJECTS = ("user", "self", "bond", "other")
STATUSES = ("confirmed", "uncertain", "outdated", "hypothetical", "disputed")
# who wins a conflict: a higher number is the more reliable source
RELIABILITY = {"manual": 5.0, "user": 4.0, "scene": 3.5, "rule": 3.0, "char": 3.0, "model": 2.0, "legacy": 2.0, "auto": 2.0, "promoted": 2.0, "auto-lite": 1.5, "summary": 1.5, "report": 1.0}
ARCHIVE_CAP = 500
TOMB_CAP = 800
KEEP_KINDS = ("promise", "secret", "body", "relationship", "decision", "plan")
_POLARITY = (("pos", lx.LIKE_WORDS), ("neg", lx.DISLIKE_WORDS))


def blank():
    return {"v": 2, "seq": 0, "turn": 0, "rev": 0, "scene": "", "recent": [], "items": [], "legacy": False, "ents": {}, "rels": [], "archive": [], "tomb": [], "ing": {"n": 0, "fps": []}}


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
    if "status" in i and i["status"] not in STATUSES:
        i["status"] = "confirmed"
    for k in ("about", "known_by", "hist"):
        if k in i and not isinstance(i[k], list):
            i[k] = []
    if "msg" in i:
        i["msg"] = _num(i.get("msg"), -1, int)
    i["ver"] = _num(i.get("ver"), 1, int)
    if "open" in i:
        i["open"] = bool(i["open"])
    return i


def ensure(st, user="", char=""):
    """Make st["mem"] valid (in place) and fold the old flat facts list in, once. Returns it."""
    m = st.get("mem")
    if not isinstance(m, dict):
        m = st["mem"] = blank()
    for k, v in blank().items():
        m.setdefault(k, v)
    m["v"] = 2
    for k, kind in (("ents", dict), ("rels", list), ("archive", list), ("tomb", list), ("recent", list)):
        if not isinstance(m.get(k), kind):
            m[k] = kind()
    if not isinstance(m.get("ing"), dict) or not isinstance(m["ing"].get("fps"), list):
        m["ing"] = {"n": 0, "fps": []}
    m["items"] = [_sane(i) for i in m["items"] if isinstance(i, dict) and i.get("t") in TYPES and str(i.get("text", "")).strip()]
    if not m["legacy"]:
        m["legacy"] = True
        for f in st.get("facts") or []:
            f = placeholders(f, user, char)
            if f:
                add(m, "semantic", f, subj="user", imp=.5, src="legacy", ts=0)
    return m


_COMMON = set("will mark grace hope joy rose may june april august art bill rob pat sky dawn faith summer autumn winter amber ivy rain river "
              "wind lily daisy violet hunter fox wolf bird page rick dean ray jack case chase frank sue sunny honey angel star".split())


def placeholders(text, user, char):
    """Real names -> {{user}} / {{char}} so the memory survives a rename. Matches any capitalisation ('crescent's'), except
    that a name which is also an ordinary word (Will, Hope, Rose) is only matched when written with a capital."""
    t = str(text or "").strip()
    for name, ph in ((user, "{{user}}"), (char, "{{char}}")):
        for n in sorted({x for x in (name or "", (name or "").split(" ")[0]) if len(x) >= 2}, key=len, reverse=True):
            loose = n.lower() not in _COMMON and n.lower() not in lx.EXTRA_STOP and len(n) >= 3
            t = re.sub(r"(?<![\w{])" + re.escape(n) + r"(?![\w}])", ph, t, flags=re.I if loose else 0)
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


def _find_twin(m, t, text, subj, who="", kind=""):
    for i in m["items"]:
        if i["t"] != t or (t == "semantic" and i.get("subj") != subj):
            continue
        if who and i.get("who") and i["who"] != who:      # the same words said by someone else are a different memory
            continue
        if kind and i.get("kind") and i["kind"] != kind:
            continue
        if i.get("status") == "outdated":
            continue
        if similar(i["text"], text) >= (.66 if t == "episodic" else .7):
            return i, "same"
        if t == "semantic":   # "likes coffee" then "hates coffee": the newer statement replaces the old
            pa, pb = _polarity(i["text"]), _polarity(text)
            if pa and pb and pa != pb and set(lx.terms(i["text"])) & set(lx.terms(text)) - {lx.stem(w) for w in "likes loves enjoys prefers hates dislikes".split()}:
                return i, "flip"
    return None, ""


def _bump(m, item):
    item["ver"] = item.get("ver", 1) + 1
    item["upd"] = now_ms()
    m["rev"] = m.get("rev", 0) + 1


def reliability(src):
    return RELIABILITY.get(src or "", 2.0)


def archive_items(m, items, why):
    """Move memories out of play without destroying them: the record of what was forgotten, replaced or deleted stays recoverable."""
    at = now_ms()
    for i in items:
        m["archive"].append(dict(i, why=why, at=at))
    del m["archive"][:-ARCHIVE_CAP]


def add(m, t, text, *, subj="user", imp=.5, emo="", val=0.0, people=(), link="", turn=None, ts=None, src="auto", pin=False,
        kind="", who="", about=(), known_by=(), status="confirmed", rsrc="", open=False, when="", evid="", msg=None, slot="", obj="", ctx=""):
    """Add one memory, merging into a near-duplicate instead of piling up. Returns (item, created).
    kind/who/about/known_by/status/rsrc/open/when/evid/msg/slot/obj are the attribution fields (who did or said it, whom it concerns,
    who was there, whether it is confirmed or only hearsay or imagined, where the words came from)."""
    text = str(text or "").strip().strip('"')
    if t not in TYPES or len(text) < 4 or str(text) in ("{{user}}", "{{char}}"):
        return None, False
    text = text[:240]
    imp = max(0.0, min(1.0, float(imp)))
    status = status if status in STATUSES else "confirmed"
    rs = rsrc or src
    old, how = _find_twin(m, t, text, subj, who, kind)
    if old:
        old["imp"] = round(min(1.0, max(old.get("imp", .5), imp) + (.04 if how == "same" else 0)), 3)
        if how == "flip" or (len(text) > len(old["text"]) and src != "legacy"):
            if old["text"] != text:
                old.setdefault("hist", []).append({"text": old["text"], "status": old.get("status", "confirmed"), "turn": old.get("turn", 0), "ts": old.get("ts", 0), "why": "reworded" if how == "same" else "reversed"})
                del old["hist"][:-6]
            old["text"] = text
        old["pin"] = bool(old.get("pin") or pin)
        old["people"] = sorted(set(old.get("people") or []) | set(people or []))
        if about:
            old["about"] = sorted(set(old.get("about") or []) | {str(a) for a in about if a})[:6]
        if emo and not old.get("emo"):
            old["emo"], old["val"] = emo, round(float(val), 2)
        if how == "same":      # the same thing seen again from a source at least as reliable firms it up
            old["seen"] = old.get("seen", 1) + 1
            if reliability(rs) >= reliability(old.get("rsrc") or old.get("src")) and status == "confirmed" and old.get("status") == "uncertain":
                old["status"] = "confirmed"
                old["rsrc"] = rs
        _bump(m, old)
        return old, False
    m["seq"] += 1
    item = {"id": f"{t[0]}{m['seq']}", "t": t, "text": text, "imp": round(imp, 3), "ts": now_ms() if ts is None else ts,
            "turn": m["turn"] if turn is None else turn, "n": 0, "last": 0, "pin": bool(pin), "src": src, "ver": 1}
    if t == "semantic":
        item["subj"] = subj if subj in SUBJECTS else "user"
    if people:
        item["people"] = sorted({str(p).strip() for p in people if str(p).strip()})[:5]
    if kind:
        item["kind"] = kind
    if who:
        item["who"] = who
    if about:
        item["about"] = sorted({str(a) for a in about if a})[:6]
    if known_by:
        item["known_by"] = [str(k) for k in known_by if k][:8]
    if status != "confirmed":
        item["status"] = status
    if rs and rs != src:
        item["rsrc"] = rs
    if open:
        item["open"] = True
    if when:
        item["when"] = when
    if evid:
        item["evid"] = evid[:160]
    if msg is not None:
        item["msg"] = int(msg)
    if slot:
        item["slot"] = slot
    if obj:
        item["obj"] = obj
    if ctx:
        item["ctx"] = ctx[:100]
    if t == "emotional":
        item.update(emo=emo or "", val=round(float(val), 2))
        if link:
            item["link"] = link
    elif emo:
        item.update(emo=emo, val=round(float(val), 2))
    m["items"].append(item)
    m["rev"] = m.get("rev", 0) + 1
    return item, True


def keep_score(i, turn):
    age = max(0, turn - i.get("turn", 0))
    return (9.0 if i.get("pin") else 0.0) + i.get("imp", .5) + .25 * (.5 ** (age / 150)) + .06 * min(i.get("n", 0), 5)


def _protected(i, turn):
    """Never forgotten by age: pinned, recently recalled, unresolved, or the kinds of memory a story is built on."""
    used = i.get("n", 0) > 0 and turn - i.get("last", 0) < 200
    return bool(i.get("pin") or used or i.get("open") or i.get("kind") in KEEP_KINDS and i.get("imp", .5) >= .5 or i.get("status") in ("outdated", "disputed"))


def decay(m, turn):
    """Forget what no longer matters: a small memory that was never recalled is retired after a while (episodes and feelings ~140 messages,
    plain facts ~220). Pinned memories, unresolved promises and anything recalled lately stay; a feeling whose episode is gone goes with it.
    Retired memories are archived (m["archive"]), not destroyed."""
    keep, gone = [], []
    for i in m["items"]:
        age = turn - i.get("turn", 0)
        imp = i.get("imp", .5)
        if _protected(i, turn):
            keep.append(i)
        elif i["t"] in ("episodic", "emotional") and imp < .4 and age > 140:
            gone.append(i)
        elif i["t"] == "semantic" and imp < .3 and age > 220:
            gone.append(i)
        else:
            keep.append(i)
    ids = {i["id"] for i in keep}
    orphan = [i for i in keep if i["t"] == "emotional" and i.get("link") and i["link"] not in ids]
    m["items"] = [i for i in keep if i not in orphan]
    if gone or orphan:
        archive_items(m, gone + orphan, "aged out")
        m["rev"] = m.get("rev", 0) + 1
    return m


def compact(m, turn=None):
    """Keep each layer under its cap by retiring the least important, oldest, never-recalled memories (pinned and unresolved ones stay). Archived, not destroyed."""
    turn = m.get("turn", 0) if turn is None else turn
    for t, cap in CAPS.items():
        mine = [i for i in m["items"] if i["t"] == t]
        if len(mine) > cap:
            order = sorted((i for i in mine if not (i.get("open") or i.get("pin"))), key=lambda i: keep_score(i, turn))
            drop = {i["id"] for i in order[:len(mine) - cap]}
            archive_items(m, [i for i in m["items"] if i["id"] in drop], "over capacity")
            m["items"] = [i for i in m["items"] if i["id"] not in drop]
            m["rev"] = m.get("rev", 0) + 1
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


def remove(m, ids, why="deleted"):
    """Delete memories on purpose. They are tombstoned (so a stale copy of the chat cannot bring them back) and archived (so a mistake can be undone)."""
    ids = set(ids or [])
    gone = [i for i in m["items"] if i["id"] in ids]
    if gone:
        archive_items(m, gone, why)
        m.setdefault("tomb", []).extend(sorted(i["id"] for i in gone))
        del m["tomb"][:-TOMB_CAP]
        m["rev"] = m.get("rev", 0) + 1
    m["items"] = [i for i in m["items"] if i["id"] not in ids]
    for i in m["items"]:
        if i.get("link") in ids:
            i.pop("link", None)


def user_facts_mirror(m, limit=40):
    """The old flat facts list, derived from semantic memory, so switching the new system off keeps what was learned."""
    mine = [i for i in m["items"] if i["t"] == "semantic" and i.get("subj", "user") == "user"]
    return [i["text"] for i in sorted(mine, key=lambda i: (i.get("ts", 0), i["id"]))[-limit:]]
