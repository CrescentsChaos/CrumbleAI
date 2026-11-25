"""The history keeper: older conversation is folded down, but events, relationships and exact details are never folded away.

The rolling summary (memory.summarize) is one blob that the model rewrites every ~14 messages. Rewriting loses things: whatever
the model does not repeat is gone for good. The keeper sits next to it and holds what must survive, without any model call
(so it costs nothing and cannot invent anything):

    state["keep"] = {"v":1, "seq", "chapters":[{id, a, b, t}], "long", "events":[{id, t, k, w, turn}], "bonds":{key: {...}},
                     "main":{"stage", "log":[{turn, a, b}]}, "covered"}

    fold(keep, old_summary, msgs, ...)   after a summary: archive the summary being replaced as a chapter, record the key events and the
                                         people met in the folded messages, note changes in how the two feel about each other, and
                                         merge the oldest chapters into `long` once there are too many (protected lines always stay)
    render(keep, query, turn, tokens)    the part worth carrying for THIS message, as plain sentences for the private background
    digest(chat, user, char)             a finished or older chat boiled down to a few lines
    past_block(digests, ...)             earlier conversations with the same character, as background

Pure functions on plain dicts; the full chat stays on disk untouched.
"""
import copy
import re

from . import chronicle
from .identity.names import relations_in
from .recall import lexicon as lx
from .recall import store as rstore
from .textutil import THINK, stage

CHAPTERS = 4          # older summaries kept one by one; beyond that the oldest two are merged into `long`
CHAPTER_CAP = 700     # characters of one chapter
LONG_CAP = 1100       # characters of the merged long-ago digest
EVENTS_CAP = 90
BONDS_CAP = 24
KEY_WEIGHT = 4        # events at or above this weight are kept (the chronicle forgets small details; the timeline does not)
PROTECT = re.compile("|".join(x.pattern.replace("(?i)", "") for x in (chronicle._PROMISE, chronicle._SECRET)), re.I)     # sentences that must survive a merge


def blank():
    return {"v": 1, "seq": 0, "chapters": [], "long": "", "events": [], "bonds": {}, "main": {"stage": "", "log": []}, "covered": 0}


def ensure(keep):
    """A usable keeper dict from whatever the page sent (missing, old or damaged)."""
    k = copy.deepcopy(keep) if isinstance(keep, dict) else {}
    for key, v in blank().items():
        if not isinstance(k.get(key), type(v)):
            k[key] = copy.deepcopy(v)
    k["chapters"] = [c for c in k["chapters"] if isinstance(c, dict) and str(c.get("t", "")).strip()]
    k["events"] = [e for e in k["events"] if isinstance(e, dict) and str(e.get("t", "")).strip()]
    k["bonds"] = {str(a): b for a, b in k["bonds"].items() if isinstance(b, dict) and b.get("name")}
    if not isinstance(k["main"].get("log"), list):
        k["main"] = {"stage": "", "log": []}
    return k


def _clip(t, n):
    t = re.sub(r"\s+", " ", t or "").strip()
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def _sentences(t):
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+|\n+", t or "") if s.strip()]


# ---------- chapters: the summary that is about to be replaced is not thrown away ----------

def archive(keep, old_summary, a, b, user="", char=""):
    """Keep the summary being replaced as a chapter (plain sentences, labels gone) so a rewrite can never drop its facts."""
    from . import context
    text = context.recap(old_summary or "", char, user)
    text = _clip(text, CHAPTER_CAP * 2 if len(text) <= CHAPTER_CAP * 2 else CHAPTER_CAP)
    if len(text) < 25:
        return keep
    last = keep["chapters"][-1] if keep["chapters"] else None
    if last and rstore.similar(last["t"], text) >= .85:     # the same notes again: not a new chapter
        last["b"] = max(last.get("b", 0), b)
        return keep
    keep["seq"] += 1
    keep["chapters"].append({"id": f"k{keep['seq']}", "a": int(a), "b": int(b), "t": text})
    return keep


def _merge_text(a, b, cap=LONG_CAP):
    """Two digests in one, within `cap`: promises and secrets first, then the newest sentences. Deterministic, adds no word."""
    sents, seen = [], []
    for s in _sentences(a) + _sentences(b):
        if any(rstore.similar(s, o) >= .8 for o in seen):
            continue
        seen.append(s)
        sents.append(s)
    total = sum(len(s) + 1 for s in sents)
    if total <= cap:
        return " ".join(sents)
    prot = [i for i, s in enumerate(sents) if PROTECT.search(s)]
    keep_i = set(prot)
    used = sum(len(sents[i]) + 1 for i in keep_i)
    for i in range(len(sents) - 1, -1, -1):          # then the newest first
        if i in keep_i:
            continue
        if used + len(sents[i]) + 1 > cap:
            continue
        keep_i.add(i)
        used += len(sents[i]) + 1
    return " ".join(sents[i] for i in sorted(keep_i))


def compact(keep):
    """Too many chapters: the two oldest become part of `long`. Nothing protected is dropped."""
    while len(keep["chapters"]) > CHAPTERS:
        a, b = keep["chapters"].pop(0), keep["chapters"][0]
        keep["long"] = _merge_text(keep["long"], a["t"])
    return keep


# ---------- events ----------

KEY_KINDS = {"promise", "secret", "body", "identity", "relation", "object", "plan"}


def key_events(msgs, user, char, turn0):
    """The moments in these messages that matter for good: promises, secrets, gifts, injuries, plans, big happenings."""
    out = []
    for f in chronicle.extract(msgs, user, char, turn0):
        if f["w"] >= KEY_WEIGHT or f["pin"] or (f["k"] in KEY_KINDS and f["w"] >= 3):
            out.append({"t": f["t"], "k": f["k"], "w": f["w"], "turn": f["turn"]})
    return out


def add_events(keep, found):
    for f in found:
        twin = next((e for e in keep["events"] if rstore.similar(e["t"], f["t"]) >= .72), None)
        if twin:
            twin["w"] = max(twin["w"], f["w"])
            continue
        keep["seq"] += 1
        keep["events"].append({"id": f"k{keep['seq']}", **f})
    if len(keep["events"]) > EVENTS_CAP:
        ranked = sorted(keep["events"], key=lambda e: (e["w"] + (2 if e["k"] in ("promise", "secret", "body") else 0), e["turn"]))
        drop = {e["id"] for e in ranked[:len(keep["events"]) - EVENTS_CAP]}
        keep["events"] = [e for e in keep["events"] if e["id"] not in drop]
    keep["events"].sort(key=lambda e: e["turn"])
    return keep


# ---------- relationships ----------

def note_people(keep, msgs, user, char, turn0):
    """People named with a relationship ('my sister Nadia'), who said it, and how often they come up."""
    for n, m in enumerate(msgs or []):
        if m.get("ooc") or (isinstance(m.get("dyn"), dict) and m["dyn"].get("quirk") == "lie"):
            continue
        t = THINK.sub("", str(m.get("content") or ""))
        who = "user" if m.get("role") == "user" else "char"
        for name, rel in relations_in(t):
            if name.lower() in {user.lower(), char.lower(), (user or "").split(" ")[0].lower(), (char or "").split(" ")[0].lower()}:
                continue
            key = name.lower()
            b = keep["bonds"].get(key)
            if b:
                b["n"] += 1
                b["last"] = turn0 + n
                if rel and rel != b["rel"] and b["owner"] == who:
                    b["was"] = b["rel"]
                    b["rel"] = rel
            else:
                keep["bonds"][key] = {"name": name, "rel": rel, "owner": who, "first": turn0 + n, "last": turn0 + n, "n": 1}
    if len(keep["bonds"]) > BONDS_CAP:
        ranked = sorted(keep["bonds"].items(), key=lambda kv: (kv[1]["n"], kv[1]["last"]))
        for k, _ in ranked[:len(keep["bonds"]) - BONDS_CAP]:
            del keep["bonds"][k]
    return keep


def note_bond(keep, affection, turn):
    """How the two feel about each other: only a change of stage is recorded (and becomes a key event)."""
    if affection is None:
        return keep
    try:
        st = stage(max(0, min(100, int(affection))))
    except Exception:
        return keep
    main = keep["main"]
    if main.get("stage") and main["stage"] != st:
        main["log"] = (main["log"] + [{"turn": int(turn), "a": main["stage"], "b": st}])[-12:]
        add_events(keep, [{"t": f"{{{{char}}}}'s feelings toward {{{{user}}}} changed: from being {main['stage']} to being {st}", "k": "bond", "w": 4, "turn": int(turn)}])
    main["stage"] = st
    return keep


# ---------- the one call the server makes after a summary ----------

def fold(keep, old_summary, msgs, user, char, turn0, turn1, affection=None):
    """-> new keeper dict. `msgs` are the messages that were just folded into the summary (turns turn0..turn1)."""
    k = ensure(keep)
    msgs = [m for m in (msgs or []) if isinstance(m, dict) and not m.get("ooc")]
    if turn0 < k.get("covered", 0):           # the chat was rewound or edited: what came from messages that no longer exist goes
        k["events"] = [e for e in k["events"] if e["turn"] < turn0]
        k["bonds"] = {a: b for a, b in k["bonds"].items() if b["first"] < turn0}
        k["chapters"] = [c for c in k["chapters"] if c["b"] <= turn0]
    archive(k, old_summary, turn0, turn1, user, char)
    add_events(k, key_events(msgs, user, char, turn0))
    note_people(k, msgs, user, char, turn0)
    note_bond(k, affection, turn1)
    compact(k)
    k["covered"] = max(k.get("covered", 0) if turn0 >= k.get("covered", 0) else 0, int(turn1))
    return k


# ---------- what goes into the prompt ----------

def _rel_text(b, user, char):
    owner = char if b["owner"] == "char" else user
    return f"{b['name']} is {owner}'s {b['rel']}" + (f" (once called {b['was']})" if b.get("was") else "")


HEAD = "[Older history. It is true and consistent with everything else you know; use it only when it comes up naturally]"


def render(keep, query, turn, tokens, user="", char=""):
    """-> prose block (or ""). Long-ago digest and chapters first (oldest to newest), then the key events and relationships most relevant
    to this message, all within `tokens`. When tight, the oldest chapters go first; events are chosen by weight, relevance and recency."""
    k = ensure(keep)
    if tokens <= chronicle._tokens(HEAD) + 20 or not (k["long"] or k["chapters"] or k["events"] or k["bonds"] or k["main"]["log"]):
        return ""
    q = set(lx.terms(query or ""))
    cost = chronicle._tokens
    left = tokens - chronicle._tokens(HEAD) - 2
    parts = []
    # relationships: the people who matter (talked about more than once, or relevant right now)
    bl = []
    for b in sorted(k["bonds"].values(), key=lambda b: (-b["n"], -b["last"])):
        rel = b["n"] >= 2 or set(lx.terms(b["name"] + " " + b["rel"])) & q
        if rel and len(bl) < 5:
            bl.append(_rel_text(b, user, char))
    if k["main"]["log"]:
        last = k["main"]["log"][-1]
        bl.insert(0, f"{char}'s feelings toward {user} changed from being {last['a']} to being {last['b']}")
    rel_s = ("Relationships: " + "; ".join(bl) + ".") if bl else ""
    left -= cost(rel_s) if rel_s else 0
    # key events, ranked
    ev = []
    for e in k["events"]:
        rel = min(1.0, len(q & set(lx.terms(e["t"]))) / max(1, min(len(q), 3)))      # how much of the question this event answers
        sc = e["w"] + (3 if e["k"] in ("promise", "secret", "body") else 0) + 12 * rel + 1.5 * .5 ** (max(0, turn - e["turn"]) / 150)
        ev.append((sc, e))
    ev.sort(key=lambda x: -x[0])
    picked, spent = [], 0
    budget_ev = int(left * .55)
    for sc, e in ev:
        c = cost(e["t"]) + 2
        if spent + c > budget_ev:
            continue
        picked.append(e)
        spent += c
    picked.sort(key=lambda e: e["turn"])
    left -= spent
    # long ago + chapters with what is left (newest chapters are worth more than old ones)
    texts = []
    for c in reversed(k["chapters"]):
        c_cost = cost(c["t"])
        if c_cost > left:
            continue
        texts.insert(0, c["t"])
        left -= c_cost
    long_s = ""
    if k["long"] and cost(k["long"]) <= left:
        long_s = k["long"]
    out = []
    if long_s:
        out.append("A long time ago: " + long_s)
    if texts:
        out.append("Before that, in order: " + " ".join(texts))
    if picked:
        out.append("Things that really happened and still matter (in order):\n" + "\n".join("- " + rstore.resolve(e["t"], user, char) for e in picked))
    if rel_s:
        out.append(rel_s)
    if not out:
        return ""
    return HEAD + "\n" + "\n".join(out)


# ---------- earlier conversations with the same character ----------

def digest(chat, user, char, limit=420):
    """One saved chat boiled down: -> {title, updated, text} or None when there is nothing worth carrying."""
    if not isinstance(chat, dict):
        return None
    st = chat.get("state") if isinstance(chat.get("state"), dict) else {}
    from . import context
    k = ensure(st.get("keep"))
    bits = []
    if (st.get("summary") or "").strip():
        bits.append(_clip(context.recap(st["summary"], char, user), limit))
    elif k["chapters"]:
        bits.append(_clip(k["chapters"][-1]["t"], limit))
    ev = sorted(k["events"], key=lambda e: (-e["w"], -e["turn"]))[:3]
    if ev:
        bits.append("Key moments: " + "; ".join(rstore.resolve(e["t"], user, char).rstrip(".") for e in sorted(ev, key=lambda e: e["turn"])) + ".")
    if k["main"]["log"]:
        bits.append(f"By the end they were {k['main']['stage']}.")
    elif k["main"].get("stage"):
        bits.append(f"By the end they were {k['main']['stage']}.")
    if not bits:
        return None
    return {"title": str(chat.get("title") or "")[:60], "updated": float(chat.get("updated") or 0), "text": " ".join(bits)}


def past_block(digests, user="", char="", tokens=260):
    """Earlier conversations (newest first), as background. The current chat's own scene and opening always win."""
    ds = sorted([d for d in digests or [] if d and d.get("text")], key=lambda d: -d["updated"])
    if not ds or tokens < 100:
        return ""
    head = (f"[Earlier conversations between {char} and {user}. They happened before this one, in separate scenes. {char} remembers them like any past, "
            f"but this scene's own setting and opening come first; do not replay them or bring them up unless it fits]")
    out, left = [], tokens - chronicle._tokens(head) - 2
    for d in ds[:4]:
        line = "- " + d["text"]
        c = chronicle._tokens(line)
        if c > left:
            break
        out.append(line)
        left -= c
    if not out:
        return ""
    return head + "\n" + "\n".join(out)
