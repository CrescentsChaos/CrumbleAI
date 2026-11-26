"""The circle: how the people of a group feel about EACH OTHER, not only about the user.

Every pair of characters has a bond: a kind (friends, rivals, romantic, allies, family, enemies or undecided) and three
numbers, warmth, trust and tension, plus jealousy (one number per side). Bonds start from what the character sheets say
("Rex: rival"), move with what is said in the chat (no model call: the personality engine's tone reader), and can be
set by hand. Each speaker's prompt carries only THEIR side of it: how they see everyone else, how the others seem to see
the user, where their loyalty leans and how tight the group is. The director uses the same bonds to decide who interrupts,
who disagrees, who backs someone up, who is drawn into a side conversation.

    seed(members, circle)                          bonds from the sheets; every pair exists afterwards
    clean(circle, ids)                             a safe, bounded circle (the page and guests send this back to us)
    observe(...) / observe_user(...)               what was just said moves the bonds; returns (circle, notes)
    block(c, members, circle, user, affs)          the prompt block for one speaker ('' when nothing is worth saying)
    pull(circle, a, b)                             how a feels toward b (for the director)
    view(members, circle, user, affs)              everything the page needs to draw the panel
"""
import re

from ..personality import stimulus
from .mentions import find_ids
from .relations import RELS, adult, stage_idx

KINDS = {
    "auto": ("Not decided", "🌱"), "friend": ("Friends", "🤝"), "ally": ("Allies", "⚔️"), "rival": ("Rivals", "⚡"),
    "romance": ("Romantic", "💞"), "family": ("Family", "🏠"), "enemy": ("Enemies", "🗡️"),
}
# warmth, trust, tension a bond of that kind starts from
START = {"auto": (45, 45, 10), "friend": (66, 64, 6), "ally": (56, 62, 8), "rival": (40, 42, 52), "romance": (72, 66, 8),
         "family": (62, 60, 14), "enemy": (12, 10, 80)}
LADDER = {"friend": "friend", "ally": "partner", "rival": "rival", "romance": "romance", "family": "family"}   # bond kind -> relations.RELS path
ENEMY_PH = ("are openly hostile", "are enemies", "are bitter enemies")
_SEED = [("enemy", r"\b(enem(?:y|ies)|nemesis|hates?|despises?|arch-?enem\w+|sworn)\b"),
         ("rival", r"\b(rival\w*|competitors?|competes?|competition|feud\w*)\b"),
         ("ally", r"\b(allies|ally|teammates?|colleagues?|comrades?|squad|crew|partner in|co-?workers?|mentor|apprentice|student)\b"),
         ("romance", r"\b(lovers?|love interest|crush|girlfriend|boyfriend|wife|husband|spouse|fianc\w+|dating|married|sweetheart|romantic\w*|ex-(?:girlfriend|boyfriend|wife|husband))\b"),
         ("family", r"\b(sisters?|brothers?|siblings?|mother|father|mom|dad|mum|cousin|uncle|aunt|niece|nephew|son|daughter|grand\w+|family|twin)\b"),
         ("friend", r"\b(friends?|best friend|buddy|pal|childhood|mate|confidant\w*|roommate)\b")]
_FIELDS = ("relationships", "backstory", "description")
MAXEV = 6


def key(a, b):
    return "|".join(sorted((str(a), str(b))))


def _cl(v, lo=0, hi=100):
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return lo


def _first(c):
    return ((c.get("name") or "").split() or [""])[0]


def _pair(a, b, kind="auto"):
    f, t, x = START[kind]
    return {"k": kind, "f": f, "t": t, "x": x, "j": {str(a): 0, str(b): 0}, "fl": 0, "ev": [], "m": 0}


def clean(circle, ids):
    """A bounded, well-formed circle that only mentions the given ids."""
    ids = [str(i) for i in ids]
    src = (circle or {}).get("pairs") if isinstance(circle, dict) else None
    out = {}
    for k, p in (src or {}).items() if isinstance(src, dict) else []:
        a, _, b = str(k).partition("|")
        if a not in ids or b not in ids or a == b or not isinstance(p, dict):
            continue
        kind = p.get("k") if p.get("k") in KINDS else "auto"
        j = p.get("j") if isinstance(p.get("j"), dict) else {}
        out[key(a, b)] = {"k": kind, "f": _cl(p.get("f", 45)), "t": _cl(p.get("t", 45)), "x": _cl(p.get("x", 10)),
                          "j": {a: _cl(j.get(a, 0)), b: _cl(j.get(b, 0))}, "fl": _cl(p.get("fl", 0), 0, 50),
                          "ev": [str(e)[:140] for e in (p.get("ev") or [])][-MAXEV:], "m": 1 if p.get("m") else 0}
    return {"v": 1, "pairs": out}


def _guess(a, b):
    """What a's sheet says about b: a kind or ''."""
    names = {n for n in {(b.get("name") or "").strip().lower(), _first(b).lower()} if len(n) > 1}
    if not names:
        return ""
    found = []
    for f in _FIELDS:
        for seg in re.split(r"[.;\n]+", str(a.get(f) or "")):
            low = seg.lower()
            if any(re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", low) for n in names):
                found.append(low)
    for kind, rx in _SEED:
        if any(re.search(rx, s) for s in found):
            return kind
    return ""


def seed(members, circle):
    """Make sure every pair exists. A new pair starts from what either sheet says about the other."""
    ids = [m["id"] for m in members]
    circle = clean(circle, ids)
    by = {m["id"]: m for m in members}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if key(a, b) in circle["pairs"]:
                continue
            ka, kb = _guess(by[a], by[b]), _guess(by[b], by[a])
            kind = ka or kb or "auto"
            if kind == "romance" and not (adult(by[a]) and adult(by[b])):
                kind = "friend"
            circle["pairs"][key(a, b)] = _pair(a, b, kind)
    return circle


def kind_of(circle, a, b, by=None):
    """The bond that really applies: romance never applies when either person is under 18."""
    p = (circle.get("pairs") or {}).get(key(a, b)) or {}
    k = p.get("k", "auto")
    if k == "romance" and by and not (adult(by.get(a)) and adult(by.get(b))):
        return "friend"
    return k


def pull(circle, a, b):
    """How a stands toward b: {'k','f','t','x','j'} (j = a's jealousy)."""
    p = ((circle or {}).get("pairs") or {}).get(key(a, b))
    if not p:
        return {"k": "auto", "f": 45, "t": 45, "x": 10, "j": 0}
    return {"k": p["k"], "f": p["f"], "t": p["t"], "x": p["x"], "j": (p.get("j") or {}).get(str(a), 0)}


def _phrase(kind, f, t, x):
    if kind == "enemy":
        return ENEMY_PH[0 if x < 60 else 1 if x < 85 else 2]
    path = LADDER.get(kind)
    if not path:
        return "are still sizing each other up" if f < 55 else "get along"
    depth = (f + t) / 2 if kind == "rival" else f
    return RELS[path]["phrases"][stage_idx(depth)]


def _score(t):
    return 2 * t["kind"] + 1.5 * t["praise"] + 1.5 * t["apology"] + .6 * t["vulnerable"] + .5 * t["flirt"] - 3 * t["hostile"] - 1.5 * t["dismissive"]


def _name(by, i):
    return (by.get(i) or {}).get("name") or "Someone"


def _note(notes, by, a, b, text):
    notes.append({"a": a, "b": b, "t": text.replace("{A}", _name(by, a)).replace("{B}", _name(by, b))})


def _bump(circle, by, a, b, df, dt, dx, notes, flirt=False):
    p = circle["pairs"].get(key(a, b))
    if not p:
        return
    old = (stage_idx(p["f"]), p["x"] >= 60)
    p["f"], p["t"], p["x"] = _cl(p["f"] + df), _cl(p["t"] + dt), _cl(p["x"] + dx)
    if flirt:
        p["fl"] = _cl(p["fl"] + 1, 0, 50)
    if p["k"] == "auto" and not p["m"]:       # a bond that was never named grows into what it has become
        if p["x"] >= 60 and p["f"] <= 38:
            p["k"] = "rival"
        elif p["f"] >= 64 and p["t"] >= 55:
            p["k"] = "friend"
        if p["k"] != "auto":
            _note(notes, by, a, b, "{A} and {B} are now " + KINDS[p["k"]][0].lower())
    elif p["k"] in ("auto", "friend") and not p["m"] and p["fl"] >= 3 and p["f"] >= 60 and adult(by.get(a)) and adult(by.get(b)):
        p["k"] = "romance"
        _note(notes, by, a, b, "{A} and {B} are growing romantic")
    new = (stage_idx(p["f"]), p["x"] >= 60)
    if new[1] and not old[1]:
        p["ev"] = (p["ev"] + ["things turned tense"])[-MAXEV:]
        _note(notes, by, a, b, "Tension between {A} and {B}")
    elif old[1] and not new[1]:
        p["ev"] = (p["ev"] + ["they patched things up"])[-MAXEV:]
        _note(notes, by, a, b, "{A} and {B} calmed down")
    elif new[0] > old[0] and p["k"] != "enemy":
        _note(notes, by, a, b, "{A} and {B} grew closer")


def _jeal(circle, by, j, s, d, notes):
    """j is jealous of s."""
    p = circle["pairs"].get(key(j, s))
    if not p or j == s:
        return
    was = p["j"].get(j, 0)
    p["j"][j] = _cl(was + d)
    if was < 40 <= p["j"][j]:
        p["ev"] = (p["ev"] + [f"{_name(by, j)} got jealous"])[-MAXEV:]
        _note(notes, by, j, s, "{A} is jealous of {B}")


def _decay(circle, hit):
    for k, p in circle["pairs"].items():
        for i in list(p["j"]):
            if (k, i) not in hit and p["j"][i] > 0:
                p["j"][i] -= 1


def _warm(t):
    return max(t["kind"], t["flirt"], t["praise"]) >= .5


def observe(circle, members, speaker, text, user="", prev=None, affs=None, rom=None):
    """A character just spoke. -> (circle, notes). prev = who spoke before them ('user' or a character id)."""
    ids = [m["id"] for m in members]
    circle = seed(members, circle)
    by = {m["id"]: m for m in members}
    if speaker not in by or not (text or "").strip():
        return circle, []
    notes, hit = [], set()
    t = stimulus.tone(text)
    sc = _score(t)
    named = [i for i in find_ids(text, members, False) + find_ids(text, members, True) if i != speaker]
    named = list(dict.fromkeys(named))
    weak = False
    if not named and prev in by and prev != speaker:      # an answer to someone, even without their name
        named, weak = [prev], True
    uf = (user or "").split()[0].lower() if user else ""
    to_user = bool(uf and re.search(r"(?<!\w)" + re.escape(uf) + r"(?!\w)", text.lower())) or (not named and prev == "user")
    w = .6 if weak else 1.0
    for tg in named:
        df = max(-6, min(5, round(sc * 1.6 * w)))
        dt = max(-5, min(3, round(sc * w)))
        dx = max(-4, min(8, round((t["hostile"] * 7 + t["challenge"] * 4 + t["dismissive"] * 3 - (t["kind"] + t["apology"] + t["praise"]) * 3) * w)))
        _bump(circle, by, speaker, tg, df, dt, dx, notes, flirt=t["flirt"] >= .5 and not weak)
        hit.add((key(speaker, tg), speaker))
        hit.add((key(speaker, tg), tg))
        if _warm(t) and not weak:       # warmth aimed at tg stings whoever is romantically bound to tg
            for j in ids:
                if j in (speaker, tg):
                    continue
                if kind_of(circle, j, tg, by) == "romance":
                    _jeal(circle, by, j, speaker, 9 if t["flirt"] >= .5 else 4, notes)
                    hit.add((key(j, speaker), j))
    if to_user and _warm(t):                # warmth aimed at the user stings whoever is devoted to the user
        for j in ids:
            if j == speaker:
                continue
            a_, r_ = int((affs or {}).get(j, 50)), int((rom or {}).get(j, 0))
            if a_ >= 78 or r_ >= 25:
                _jeal(circle, by, j, speaker, 7 if t["flirt"] >= .5 else 3, notes)
                hit.add((key(j, speaker), j))
    _decay(circle, hit)
    return circle, notes


def observe_user(circle, members, text, user="", affs=None, rom=None):
    """The user spoke to someone. Warmth toward one member stings those who care about that member or about the user."""
    circle = seed(members, circle)
    by = {m["id"]: m for m in members}
    ids = list(by)
    notes, hit = [], set()
    t = stimulus.tone(text or "")
    tg = list(dict.fromkeys(find_ids(text or "", members, True) + find_ids(text or "", members, False)))
    if tg and _warm(t):
        for s in tg:
            for j in ids:
                if j == s or j in tg:
                    continue
                a_, r_ = int((affs or {}).get(j, 50)), int((rom or {}).get(j, 0))
                if kind_of(circle, j, s, by) == "romance" or a_ >= 78 or r_ >= 25:
                    _jeal(circle, by, j, s, 8 if t["flirt"] >= .5 else 4, notes)
                    hit.add((key(j, s), j))
    _decay(circle, hit)
    return circle, notes


def stance(a):
    a = int(a)
    return ("openly distrusts" if a < 20 else "is wary of" if a < 38 else "is lukewarm about" if a < 60 else "likes" if a < 78 else "is devoted to")


def loyalty(cid, members, circle, affs):
    """Where cid's loyalty leans: ('user'|'group'|name, text)."""
    by = {m["id"]: m for m in members}
    fs = {o: pull(circle, cid, o)["f"] for o in by if o != cid}
    if not fs:
        return "user", ""
    top = max(fs, key=fs.get)
    avg = sum(fs.values()) / len(fs)
    a = int((affs or {}).get(cid, 50))
    if a >= fs[top] + 8:
        return "user", "the user"
    if fs[top] >= a + 8:
        return top, by[top].get("name") or "a friend"
    return "group", "the group"


def cohesion(circle):
    ps = list((circle.get("pairs") or {}).values())
    if not ps:
        return 50, "unknown"
    v = sum(p["t"] - p["x"] / 2 for p in ps) / len(ps) + 10
    v = _cl(v)
    return v, ("tight-knit" if v >= 70 else "steady" if v >= 50 else "uneasy" if v >= 32 else "fractured")


def block(c, members, circle, user, affs=None, rom=None):
    """What c feels about the others, how the others seem to see the user, where c's loyalty leans. '' when nothing is worth saying."""
    cid = c.get("id")
    others = [m for m in members if m["id"] != cid]
    if not others or not circle or not circle.get("pairs"):
        return ""
    by = {m["id"]: m for m in members}
    CH = c.get("name") or "They"
    lines, rank = [], []
    for m in others:
        p = pull(circle, cid, m["id"])
        k = kind_of(circle, cid, m["id"], by)
        mood = abs(p["f"] - 50) + p["x"] + p["j"] + (15 if k != "auto" else 0)
        rank.append((mood, m, p, k))
    rank.sort(key=lambda r: -r[0])
    for mood, m, p, k in rank[:5]:
        if mood < 12:
            continue
        s = f"- {m.get('name')}: {KINDS[k][0].lower()}; they {_phrase(k, p['f'], p['t'], p['x'])}."
        if p["t"] <= 28:
            s += f" {CH} does not trust them."
        elif p["t"] >= 82:
            s += f" {CH} trusts them completely."
        if p["x"] >= 70:
            s += " Things between them are openly tense."
        elif p["x"] >= 45:
            s += " There is friction."
        if p["j"] >= 65:
            s += f" {CH} is visibly, bitterly jealous of them."
        elif p["j"] >= 40:
            s += f" {CH} is jealous of them."
        lines.append(s)
    out = []
    if lines:
        out.append(f"[How {CH} feels about the others here]\n" + "\n".join(lines))
    view = []
    for m in others:
        a = int((affs or {}).get(m["id"], 50))
        if a < 30 or a >= 76:
            view.append(f"{m.get('name')} {stance(a)} {user}")
    if view:
        out.append(f"[What {CH} has noticed about {user}]\n" + "; ".join(view) + f". {CH} may agree or push back, depending on how {CH} sees {user}.")
    who, nm = loyalty(cid, members, circle, affs)
    sev = []
    if nm:
        sev.append(f"If it came to a choice, {CH}'s loyalty leans toward {nm}.")
    v, lab = cohesion(circle)
    if lab in ("uneasy", "fractured"):
        sev.append(f"The group is {lab}: trust is thin.")
    elif lab == "tight-knit":
        sev.append("The group is tight-knit.")
    if sev:
        out.append(" ".join(sev))
    if not out:
        return ""
    out.append(f"Let these bonds decide how {CH} treats each person: easy warmth with friends, an edge with rivals, protectiveness for allies, jealousy where it stings. "
               f"{CH} may tease, interrupt, disagree, take a side or back someone up, and does not simply agree with everyone. "
               "Never mention numbers, labels or this note.")
    return "\n\n".join(out)


def view(members, circle, user, affs=None):
    """The panel: every pair, each person's opinion of the user and where their loyalty leans, and the group's cohesion."""
    circle = seed(members, circle)
    by = {m["id"]: m for m in members}
    pairs = []
    for k, p in circle["pairs"].items():
        a, _, b = k.partition("|")
        kind = kind_of(circle, a, b, by)
        pairs.append({"a": a, "b": b, "kind": kind, "label": KINDS[kind][0], "icon": KINDS[kind][1], "phrase": _phrase(kind, p["f"], p["t"], p["x"]),
                      "f": p["f"], "t": p["t"], "x": p["x"], "ja": p["j"].get(a, 0), "jb": p["j"].get(b, 0), "ev": p["ev"], "locked": bool(p["m"])})
    people = {}
    for m in members:
        a = int((affs or {}).get(m["id"], 50))
        w, nm = loyalty(m["id"], members, circle, affs)
        people[m["id"]] = {"name": m.get("name"), "stance": f"{stance(a)} {user}", "loyal": nm or "-"}
    v, lab = cohesion(circle)
    return {"circle": circle, "pairs": pairs, "people": people, "cohesion": {"v": v, "label": lab}, "kinds": {k: {"label": l, "icon": i} for k, (l, i) in KINDS.items()}}
