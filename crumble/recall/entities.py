"""Who is who, and how they relate over time. Lives inside the memory store (mem["ents"], mem["rels"]); no model call.

    mem["ents"]  {key: {name, kind, aliases, first, last, n}}   every person or place the chat has named
    mem["rels"]  [{a, b, rel, from, to, ts, src, text}]          relationship timeline: when a bond began and when it ended

    detect(text, mem, user, char)        canonical names mentioned in a text (aliases and first names resolve to the one entity)
    relations_in(sentence, ...)          "my sister Nadia", "Marcus and Elena are married", "Garrick betrayed Mira", "we broke up"
    link_rel(mem, a, b, label, ...)      add a bond; a bond that contradicts an older one ends the older one instead of erasing it
    timeline(mem, a, b)                  the history between two people, oldest first

The user and the character are written as the placeholders {{user}} / {{char}} (so a rename never breaks the record);
every other person keeps their real name.
"""
import re

U, C = "{{user}}", "{{char}}"

COMMON = set(\
    "the a an and but so then this that these those what when where why how who which not no yes maybe perhaps honestly actually anyway hello hey oh ah hmm okay "
    "alright come look listen wait stop do did does can could would should will let lets give take tell show here there now just still even also only never always "
    "sometimes today tomorrow tonight yesterday typical noted fine great good thanks thank please sorry well right sure mister miss mrs mr dr my his her their our "
    "your its i you he she they we it me him them us if because since while though although after before until once every each some any all both either neither "
    "monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october november december "
    "one two three four five six seven eight nine ten no nothing nobody everyone everybody someone somebody something everything".split())
TITLES = set(\
    "captain king queen prince princess lord lady sir dame baron baroness duke duchess count countess doctor professor master mistress father mother "
    "sister brother commander general sergeant officer inspector detective mayor judge uncle aunt old young little big saint".split())
ROLES = (r"(?:best friend|mother|father|mom|mum|dad|sister|brother|wife|husband|girlfriend|boyfriend|fianc[eé]e?|friend|boss|teacher|student|son|daughter|cousin|"
         r"uncle|aunt|grand(?:mother|father|ma|pa)|roommate|ex|partner|colleague|neighbou?r|rival|enemy|master|apprentice|mentor|captain|king|queen|lord|twin)")
NAME_VERBS = set(\
    "said says told tells asked asks replied replies whispered whispers shouted laughed laughs smiled smiles nodded nods grinned frowned stiffens stiffened "
    "sighed shrugged shrugs is was has had will can owes owed wants wanted knows knew saw sees did does doesn't didn't isn't wasn't hasn't won't can't "
    "thinks thought believes lied lies cried cries walked walks looked looks turned turns left leaves arrived arrives".split())
_SEQ = re.compile(r"\b([A-Z][a-z]{1,}(?:[-'][A-Za-z]+)?(?:\s+(?:of\s+|the\s+)?[A-Z][a-z]{1,}(?:[-'][A-Za-z]+)?){0,2})\b")
_MENTION = re.compile(r"@([\w'-]{2,})")
_PLACE_PREP = re.compile(r"\b(?:at|in|inside|outside|near|to|from|toward|towards|into|entering|reached|reach|visit(?:ed)?)\s+(?:the\s+)?$", re.I)
ROMANTIC = {"wife", "husband", "girlfriend", "boyfriend", "fiance", "fiancee", "fiancé", "fiancée", "partner", "married", "dating", "lovers", "engaged", "couple", "together"}
HOSTILE = {"enemy", "enemies", "rival", "rivals", "hostile"}
FRIENDLY = {"friend", "friends", "best friend", "ally", "allies"}


def ensure(mem):
    if not isinstance(mem.get("ents"), dict):
        mem["ents"] = {}
    if not isinstance(mem.get("rels"), list):
        mem["rels"] = []
    return mem


def _key(n):
    return re.sub(r"\s+", " ", str(n or "").strip().lower())


def canon(mem, name):
    """The one canonical spelling for a name or alias, or the name itself if unknown."""
    ensure(mem)
    k = _key(name)
    if k in mem["ents"]:
        return mem["ents"][k]["name"]
    for e in mem["ents"].values():
        if k in e.get("aliases", []):
            return e["name"]
    return str(name).strip()


def known(mem):
    return [e["name"] for e in ensure(mem)["ents"].values()]


def register(mem, name, *, kind="person", turn=0, ts=0):
    """Make sure an entity exists (and remember a first-name alias for a longer name). Returns the entity."""
    ensure(mem)
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not name or name in (U, C):
        return None
    cn = canon(mem, name)
    k = _key(cn)
    e = mem["ents"].get(k)
    if not e:
        e = mem["ents"][k] = {"name": cn, "kind": kind, "aliases": [], "first": turn, "last": turn, "n": 0}
        parts = cn.split()
        if len(parts) > 1:                       # "Captain Reyes" is also "Reyes"
            tail = _key(parts[-1])
            if tail not in mem["ents"] and not any(tail in x.get("aliases", []) for x in mem["ents"].values()) and parts[-1].lower() not in COMMON:
                e["aliases"].append(tail)
    e["n"] += 1
    e["last"] = max(e.get("last", 0), turn)
    if kind == "place" and e.get("kind") == "person" and e["n"] <= 2:
        e["kind"] = "place"
    return e


def add_alias(mem, name, alias):
    e = register(mem, name)
    if e and _key(alias) not in e["aliases"] and _key(alias) != _key(e["name"]):
        e["aliases"].append(_key(alias))


def _sentence_start(text, pos):
    before = text[:pos].rstrip(" \t\"'“”*_(")
    return not before or before[-1] in ".!?…\n:"


def detect(text, mem, user="", char="", speaker="", extra=()):
    """Canonical names of the people and places a text mentions, excluding the user and the character."""
    ensure(mem)
    t = str(text or "").replace("’", "'")
    skip = set()
    for n in (user, char):
        for p in {n, (n or "").split(" ")[0]} - {""}:
            skip.add(_key(p))
    found = []

    def add(raw, kind="person"):
        raw = raw.strip()
        if not raw or _key(raw) in skip:
            return
        cn = canon(mem, raw)
        if _key(cn) not in skip and cn not in found:
            found.append(cn)

    for m in _MENTION.finditer(t):
        add(m.group(1))
    for k in list(mem["ents"]) + [a for e in mem["ents"].values() for a in e.get("aliases", [])] + [_key(x) for x in extra if x]:
        if len(k) >= 3 and re.search(r"(?<![\w])" + re.escape(k) + r"(?![\w])", t, re.I):
            add(k)
    for m in _SEQ.finditer(t):
        toks = m.group(1).split()
        lead = 0
        while lead < len(toks) and toks[lead].lower() in COMMON:
            lead += 1
        rest = toks[lead:]
        if not rest:
            continue
        name = " ".join(rest)
        start = m.start() + sum(len(x) + 1 for x in toks[:lead])
        if len(rest) == 1 and rest[0].lower() in TITLES:
            continue
        if _sentence_start(t, start) and lead == 0:
            nxt = t[m.end():m.end() + 24].lstrip().split(" ")[0].strip(".,!?;:\"'*").lower()
            if len(rest) == 1 and _key(name) not in mem["ents"] and nxt not in NAME_VERBS and not t[m.end():m.end() + 2].startswith("'s"):
                continue                          # a sentence opener like "Noted." is not a person
        add(name)
    return found


def place_kind(text, name):
    """Was this name used as a place ('at the Old Pier')?"""
    m = re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", text or "")
    return bool(m and _PLACE_PREP.search(text[:m.start()]))


def observe(mem, text, user, char, *, speaker="", turn=0, ts=0, extra=()):
    """Register every name in a text. Returns the canonical names found."""
    ensure(mem)
    out = detect(text, mem, user, char, speaker, extra)
    for n in out:
        register(mem, n, kind="place" if place_kind(text, n) else "person", turn=turn, ts=ts)
    return out


# ---- relationships ----
_N = r"([A-Z][a-z]{1,}(?:[-'][A-Za-z]+)?(?:\s+[A-Z][a-z]{1,})?)"
_R1 = re.compile(r"\b(?i:my|your)\s+((?i:" + ROLES + r"))\s+(?i:is\s+|was\s+)?(?i:named\s+|called\s+)?" + _N)
_R2 = re.compile(_N + r"\s+(?:is|was)\s+((?i:my|your))\s+((?i:" + ROLES + r"))\b")
_R3 = re.compile(_N + r"\s+(?:is|was)\s+" + _N + r"'s\s+((?i:" + ROLES + r"))\b")
_R4 = re.compile(_N + r"\s+and\s+" + _N + r"\s+(?:are|were)\s+(?:both\s+)?(married|dating|siblings|brothers|sisters|friends|enemies|rivals|partners|lovers|engaged|twins|cousins|together)\b")
_R5 = re.compile(_N + r"\s+(betrayed|saved|rescued|kissed|married|killed|hit|helped|hired|fired|forgave|trusted|lied to|threatened|protected|abandoned|stabbed|robbed)\s+" + _N)
_BREAK = re.compile(r"\b(" + _N[1:-1] + r"|we|We|I)\s+(?:broke up|split up|have split|got divorced|divorced|are no longer (?:together|friends)|aren't (?:together|friends) anymore|stopped being friends)(?:\s+with\s+" + _N + r")?")
_BREAK2 = re.compile(_N + r"\s+and\s+(?:I|me|we)\s+(?:broke up|split up|got divorced|divorced|are no longer (?:together|friends)|stopped being friends)")
_WE = re.compile(r"\b(?:we(?:'re| are)|me and you are|you and i are)\s+(?:now\s+)?(dating|together|a couple|friends|best friends|enemies|rivals|engaged|married)\b", re.I)


def relations_in(sent, speaker="", user="", char="", addressee=""):
    """Bonds a sentence states. -> [{a, b, rel, kind: 'bond'|'event'|'end'}] with placeholders for the user and the character."""
    s = str(sent or "").replace("’", "'")
    sp = _ph(speaker, user, char)
    ad = _ph(addressee, user, char)
    out = []
    for m in _R1.finditer(s):
        owner = sp if s[m.start():m.start() + 2].lower() == "my" else ad
        if owner and owner != m.group(2):
            out.append({"a": m.group(2), "b": owner, "rel": m.group(1).lower(), "kind": "bond"})
    for m in _R2.finditer(s):
        owner = sp if m.group(2).lower() == "my" else ad
        if owner and owner != m.group(1):
            out.append({"a": m.group(1), "b": owner, "rel": m.group(3).lower(), "kind": "bond"})
    for m in _R3.finditer(s):
        out.append({"a": m.group(1), "b": m.group(2), "rel": m.group(3).lower(), "kind": "bond"})
    for m in _R4.finditer(s):
        out.append({"a": m.group(1), "b": m.group(2), "rel": m.group(3).lower(), "kind": "bond"})
    for m in _WE.finditer(s):
        if sp and ad:
            out.append({"a": sp, "b": ad, "rel": m.group(1).lower(), "kind": "bond"})
    for m in _R5.finditer(s):
        out.append({"a": m.group(1), "b": m.group(3), "rel": m.group(2).lower(), "kind": "event"})
    named_break = bool(_BREAK2.search(s))
    for m in _BREAK.finditer(s):
        first = m.group(1)
        if named_break and first.lower() in ("we", "i") and not m.group(2):
            continue            # "Elena and I broke up" is about Elena, not about the person being addressed
        a = sp if first.lower() in ("we", "i") else first
        b = m.group(2) or ad
        if a and b:
            out.append({"a": a, "b": b, "rel": "ended", "kind": "end"})
    for m in _BREAK2.finditer(s):
        if sp:
            out.append({"a": sp, "b": m.group(1), "rel": "ended", "kind": "end"})
    return [r for r in out if r["a"] and r["b"] and r["a"] != r["b"]]


def _ph(name, user, char):
    n = str(name or "").strip()
    if not n:
        return ""
    if n in (U, C):
        return n
    if user and (_key(n) == _key(user) or _key(n) == _key(user.split(" ")[0])):
        return U
    if char and (_key(n) == _key(char) or _key(n) == _key(char.split(" ")[0])):
        return C
    return n


def _group(label):
    l = label.lower()
    if l in ROMANTIC or l in ("dating", "lovers"):
        return "romantic"
    if l in HOSTILE:
        return "hostile"
    if l in FRIENDLY:
        return "friendly"
    return None


def _same_pair(r, a, b):
    return {_key(r["a"]), _key(r["b"])} == {_key(a), _key(b)}


def link_rel(mem, a, b, label, *, turn=0, ts=0, src="rule", text=""):
    """Record that a bond began. An older bond of the same pair that this one contradicts is ended (kept, with an end turn), never erased.
    -> the new/refreshed entry, or None for a repeat."""
    ensure(mem)
    label = label.lower()
    cur = [r for r in mem["rels"] if _same_pair(r, a, b) and r.get("to") is None]
    for r in cur:
        if r["rel"] == label:
            r["ts"] = max(r.get("ts", 0), ts)
            return None
    g = _group(label)
    for r in cur:
        if label == "ended" or (g and _group(r["rel"]) and _group(r["rel"]) != g) or (g == "romantic" and _group(r["rel"]) == "romantic"):
            if label == "ended" and not _group(r["rel"]):
                continue
            r["to"] = turn
    if label == "ended":
        e = {"a": a, "b": b, "rel": "ended", "from": turn, "to": turn, "ts": ts, "src": src, "text": text or f"{a} and {b} ended things"}
    else:
        e = {"a": a, "b": b, "rel": label, "from": turn, "to": None, "ts": ts, "src": src, "text": text or f"{a} and {b}: {label}"}
    mem["rels"].append(e)
    del mem["rels"][:-160]
    return e


def timeline(mem, a, b=None, user="", char="", limit=24):
    """What happened between two people (or around one), oldest first: bonds beginning and ending, and the events that involved them."""
    ensure(mem)
    A, B = _ph(a, user, char), _ph(b, user, char) if b else None
    keys = {_key(A)} | ({_key(B)} if B else set())

    def involves(names):
        ks = {_key(x) for x in names if x}
        return keys <= ks if B else bool(keys & ks)

    rows = []
    for r in mem["rels"]:
        if involves([r["a"], r["b"]]):
            rows.append({"turn": r.get("from", 0), "ts": r.get("ts", 0), "text": r["text"], "kind": "bond" if r["rel"] != "ended" else "end", "active": r.get("to") is None})
    for i in mem.get("items", []):
        if i.get("kind") in ("event", "gift", "promise", "secret", "decision", "relationship", "claim") and involves([i.get("who")] + list(i.get("about") or [])):
            rows.append({"turn": i.get("turn", 0), "ts": i.get("ts", 0), "text": i["text"], "kind": i.get("kind", "event"), "active": i.get("status") not in ("outdated",)})
    rows.sort(key=lambda r: (r["turn"], r["ts"]))
    return rows[-limit:]


def current_bonds(mem, who):
    """The bonds of one entity that have not ended."""
    ensure(mem)
    k = _key(who)
    return [r for r in mem["rels"] if r.get("to") is None and k in (_key(r["a"]), _key(r["b"]))]
