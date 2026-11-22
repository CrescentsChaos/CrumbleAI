"""The chronicle: nothing that matters is lost, and only what matters is carried.

Long chats used to survive by silently dropping their oldest messages once the prompt filled up. Now every exchange is read as it happens
(no model call, so it costs nothing and cannot invent anything) and every DETAIL in it is kept as a short verbatim line: names, numbers,
times, places, promises, secrets, gifts and objects, plans, family and identity facts, injuries, deaths. The raw messages can then leave the
prompt; the details stay.

    state["chron"] = {"v":1, "seq":0, "turn":0, "items":[{id, t, k, w, turn, keys, pin, n, last}]}

    extract(msgs, user, char, turn0)   details found in these messages
    merge(chron, found, turn)          add them (near-duplicates strengthen each other), then decay()
    decay(chron, turn)                 forget what no longer matters: small, old, never-needed lines are deleted after a while
    pick(chron, query, turn, tokens)   the lines worth carrying for THIS message: pinned ones, then the most relevant and recent, within a token budget
    render(lines, user, char)          prose for the private background (no labels)
    budget(n_ctx, reply, level)        the token plan, so a prompt never reaches the context limit

Pure functions on plain dicts; the full chat is always kept on disk untouched.
"""
import copy
import re

from .recall import lexicon as lx
from .recall import store as rstore
from .textutil import THINK

CAP = 420
BASE_CTX = 8192                      # the window the PLAN below was tuned for; a larger window scales it up, nothing caps it
PLAN = {0: dict(hist=2600, chron=420, mem=1.0, summ=1.0), 1: dict(hist=1900, chron=300, mem=.75, summ=.8),
        2: dict(hist=1300, chron=210, mem=.55, summ=.6), 3: dict(hist=800, chron=130, mem=.35, summ=.4)}

_SENT = re.compile(r"(?<=[.!?…])\s+|\n+")
_NUMS = re.compile(r"(?i)\b(?:\d[\d,.:]*|(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|half|dozen)\b(?=\s+(?:years?|months?|weeks?|days?|hours?|minutes?|dollars?|bucks|pounds?|euros?|miles?|km|people|men|guards|coins|gold|times|o'?clock)))")
_TIME = re.compile(r"(?i)\b(?:tomorrow|tonight|yesterday|next (?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|at (?:noon|midnight|dawn|dusk|\d)|deadline|appointment|birthday|anniversary|meet (?:me|you|at)|by (?:friday|monday|tomorrow|midnight))\b")
_PROMISE = re.compile(r"(?i)\b(?:promis\w*|i swear|swore|vow\w*|oath|i'?ll never|i will never|i'?ll always|i will always|guarantee\w*|cross my heart|on my (?:life|honou?r)|you have my word|i owe you)\b")
_SECRET = re.compile(r"(?i)\b(?:secret\w*|don'?t tell|do not tell|between us|confess\w*|admit\w*|truth is|never told|nobody knows|no one knows)\b")
_ITEM = re.compile(r"(?i)\b(?:gives?|gave|hands?|handed|offers?|offered|buys?|bought|steals?|stole|finds?|found|keeps?|kept|loses?|lost|drops?|dropped|carries|carried|wears?|wore|wields?|unlocks?|opens?|hides?|hid|burns?|burned|breaks?|broke|repairs?|signs?|signed|owns?|inherit\w*|borrow\w*)\s+(?:\w+\s+){0,3}(?:a|an|the|his|her|their|my|your|our)\s+[a-z]{3,}")
_REL = re.compile(r"(?i)\b(?:my|his|her|their|your|our)\s+(?:mother|father|mom|mum|dad|sister|brother|wife|husband|girlfriend|boyfriend|fianc[eé]e?|friend|boss|teacher|master|student|son|daughter|cousin|uncle|aunt|grand(?:mother|father|ma|pa)|dog|cat|pet|partner|roommate|rival|enemy|captain|king|queen|lord)\b")
_IDENT = re.compile(r"(?i)\b(?:my name is|i'?m called|call me|i work (?:as|at|for|in)|i live (?:in|at|on)|i'?m from|i'?m an? [a-z]+|i am an? [a-z]+|i study|i was born|i grew up|years old|i'?m \d{1,2}\b|i have (?:a|an|two|three|no) [a-z]+|i hate|i love|i can'?t stand|i'?m allergic|my favou?rite)\b")
_EVENT = re.compile(r"(?i)\b(?:kiss\w*|hugg?\w*|cries|cried|crying|leaves|left|arrives?|arrived|travel\w*|decid\w+|agree\w*|refus\w+|argu\w+|fought|fight|propos\w+|marri\w+|betray\w*|forgiv\w+|apolog\w+|thank\w*|saves?|saved|rescu\w+|attack\w*|escap\w+|captur\w+|arrest\w*|heal\w+|injur\w+|wound\w+|dies|died|dead|killed|reviv\w+|resurrect\w+)\b")
_PLACE = re.compile(r"\b(?:in|at|inside|outside|near|to|from|toward|towards|into|entering)\s+(?:the\s+)?([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)")
_CAP = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})\b")
_STOP = set("The And But Then This That They There When What Where Why How Not Yes Maybe Well Just Please Sorry Thanks Okay Fine Good Right Sure Now Here Her His She He You Your".split())


def blank():
    return {"v": 1, "seq": 0, "turn": 0, "covered": 0, "items": []}


def ensure(st):
    c = st.get("chron")
    if not isinstance(c, dict):
        c = st["chron"] = blank()
    for k, v in blank().items():
        c.setdefault(k, v)
    c["items"] = [i for i in c["items"] if isinstance(i, dict) and str(i.get("t", "")).strip()]
    return c


def _score(s, user, char):
    sc, kind, pin = 0, "detail", False
    if _PROMISE.search(s):
        sc, kind, pin = sc + 4, "promise", True
    if _SECRET.search(s):
        sc, kind, pin = sc + 3, "secret", True
    if _IDENT.search(s):
        sc, kind, pin = sc + 3, kind if kind != "detail" else "identity", True
    if _REL.search(s):
        sc, kind = sc + 3, kind if kind != "detail" else "relation"
    if _ITEM.search(s):
        sc, kind = sc + 3, kind if kind != "detail" else "object"
    if _TIME.search(s):
        sc, kind = sc + 2, kind if kind != "detail" else "plan"
    if _NUMS.search(s):
        sc += 2
    names = {m for m in _CAP.findall(s) if m not in _STOP and m not in (user, char)}
    sc += min(2, len(names))
    if _PLACE.search(s):
        sc += 1
    if _EVENT.search(s):
        sc += 1
        if re.search(r"(?i)\b(?:dies|died|dead|killed|reviv\w+|resurrect\w+|injur\w+|wound\w+)\b", s):
            sc, kind, pin = sc + 3, "body", True
    return sc, kind, pin


def extract(msgs, user="", char="", turn0=0):
    """Details in these messages, as short verbatim lines. msgs: [{role, content, name?}]"""
    found = []
    for n, m in enumerate(msgs or []):
        if m.get("ooc"):
            continue
        t = THINK.sub("", str(m.get("content") or ""))
        t = re.sub(r"[*_]{1,2}", "", t)
        who = user if m.get("role") == "user" else (m.get("name") or char or "Character")
        for s in _SENT.split(t):
            s = re.sub(r"\s+", " ", s).strip(' "“”')
            if len(s) < 14:
                continue
            sc, kind, pin = _score(s, user, char)
            if sc < 3:
                continue
            line = rstore.placeholders(f"{who}: {s[:170]}", user, char)
            found.append({"t": line, "k": kind, "w": min(5, max(2, sc // 2 + (1 if pin else 0))), "turn": turn0 + n, "pin": pin})
    return found


def _tokens(text):
    return len(text) // 3 + 3


def merge(c, found, turn):
    for f in found or []:
        keys = sorted(set(lx.terms(f["t"])))[:9]
        twin = next((i for i in c["items"] if rstore.similar(i["t"], f["t"]) >= .72), None)
        if twin:
            twin["w"] = min(5, max(twin["w"], f["w"]) + (1 if f["w"] >= twin["w"] and twin["w"] < 5 and twin.get("n", 0) else 0))
            twin["pin"] = bool(twin.get("pin") or f.get("pin"))
            continue
        c["seq"] += 1
        c["items"].append({"id": f"c{c['seq']}", "t": f["t"], "k": f["k"], "w": f["w"], "turn": f["turn"], "keys": keys, "pin": bool(f.get("pin")), "n": 0, "last": 0})
    c["turn"] = max(c.get("turn", 0), turn)
    decay(c, turn)
    return c


def decay(c, turn):
    """Forget what no longer matters. A line that is small (weight 2), old and never needed is deleted after ~90 messages; a middling one after
    ~260; pinned ones (promises, secrets, identity, bodies) and anything used lately stay. Over the cap, the least valuable go first."""
    keep = []
    for i in c["items"]:
        age = turn - i.get("turn", 0)
        used = i.get("n", 0) > 0 and turn - i.get("last", 0) < 160
        if not i.get("pin") and not used and ((i["w"] <= 2 and age > 90) or (i["w"] == 3 and age > 260)):
            continue
        keep.append(i)
    if len(keep) > CAP:
        keep.sort(key=lambda i: (9 if i.get("pin") else 0) + i["w"] + .4 * min(i.get("n", 0), 5) + .5 ** ((turn - i.get("turn", 0)) / 120))
        keep = keep[len(keep) - CAP:]
    c["items"] = sorted(keep, key=lambda i: i.get("turn", 0))
    return c


def pick(c, query, turn, tokens, veto=None):
    """The lines worth carrying for this message. Returns [item] in story order."""
    if not c or not c.get("items") or tokens <= 0:
        return []
    q = set(lx.terms(query or ""))
    ranked = []
    for i in c["items"]:
        rel = len(q & set(i.get("keys") or [])) / max(2, len(i.get("keys") or [1]))
        rec = .5 ** (max(0, turn - i.get("turn", 0)) / 40)
        s = i["w"] + (3.5 if i.get("pin") else 0) + 7 * rel + 1.6 * rec + .2 * min(i.get("n", 0), 5)
        ranked.append((s, rel, i))
    ranked.sort(key=lambda r: -r[0])
    out, spent = [], 0
    for s, rel, i in ranked:
        if veto and veto(i["t"]):
            continue
        cost = _tokens(i["t"])
        if spent + cost > tokens:
            continue
        if s < 4.2 and not rel:
            break
        out.append(i)
        spent += cost
    return sorted(out, key=lambda i: i.get("turn", 0))


def touch(c, ids, turn):
    ids = set(ids or [])
    for i in c.get("items", []):
        if i["id"] in ids:
            i["n"], i["last"] = i.get("n", 0) + 1, turn


def render(lines, user, char):
    if not lines:
        return ""
    body = "\n".join("- " + rstore.resolve(i["t"], user, char) for i in lines)
    return ("[Established details from earlier. Every one of these really happened or was really said; they stay true, exact (names, numbers, times, promises) and consistent. "
            "Use one only when it comes up naturally]\n" + body)


def budget(n_ctx, reply, level=0):
    """Token plan. There is no ceiling of its own: the prompt may use the model's whole window (n_ctx - reply - margin) and normally aims for ~80% of that,
    squeezing step by step. The PLAN was tuned for an 8192 window; a bigger window carries proportionally more chat and more details, so the whole
    context is actually used instead of being left empty."""
    ctx = int(n_ctx)
    room = ctx - int(reply) - 24
    k = max(1.0, ctx / BASE_CTX)
    pl = dict(PLAN[max(0, min(3, level))])
    pl["hist"], pl["chron"] = int(pl["hist"] * k), int(pl["chron"] * k)
    return {"room": room, "target": int(room * .8), **pl}


def trim_history(hist, tokens, keep=3):
    """Newest messages that fit in `tokens`. Returns (kept, dropped list). The dropped ones' details are already in the chronicle."""
    cnt = [_tokens(THINK.sub("", str(m.get("content") or ""))) for m in hist]
    total, start = 0, len(hist)
    for k in range(len(hist) - 1, -1, -1):
        if total + cnt[k] > tokens and len(hist) - k > keep:
            break
        total += cnt[k]
        start = k
    return hist[start:], hist[:start]


def update(st, window, user, char, turn, used=()):
    """After a reply: read the messages not yet read, add what the page sent along (details from messages that already left the prompt),
    forget what is stale. `window` is the newest messages and `turn` the position just after the last one. Mutates st["chron"] (a copy)."""
    c = copy.deepcopy(st.get("chron")) if isinstance(st.get("chron"), dict) else blank()
    st["chron"] = c
    ensure(st)
    window = window or []
    if c["covered"] > turn:        # the chat was rewound or edited: details from messages that no longer exist go
        c["items"] = [i for i in c["items"] if i.get("turn", 0) < turn]
        c["covered"] = turn
    start = max(0, turn - len(window))
    new = window[max(0, c["covered"] - start):]
    found = extract(new, user, char, max(c["covered"], start))
    found += [f for f in (st.pop("chron_in", None) or []) if isinstance(f, dict) and f.get("t")]
    c["covered"] = turn
    touch(c, [i for i in used or [] if str(i).startswith("c")], turn)
    return merge(c, found, turn)
