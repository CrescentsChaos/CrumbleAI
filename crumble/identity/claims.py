"""Claims: the things the user actually said about their own life (or about people they introduced), kept verbatim
and tagged with WHO they belong to. Re-derived from the chat every turn, so exact details (names, numbers, dates,
left/right, likes/dislikes) never depend on a summary or an extraction model, and survive trimming.

    extract    chat -> claims         ownership comes from the grammar: 'I broke my wrist' is the user's,
                                      'She hates roses' right after 'My sister Nadia...' is Nadia's
    relevant   claims + message       the few claims that answer the latest message
    conflict   text vs text           do two statements about the same thing disagree?
"""
import math
import re

from ..recall import lexicon as lx
from .common import norm, sentences, speech_only
from .names import REL_ALT, relations_in

FIRST = re.compile(r"\b(?:i|i'm|i've|i'll|i'd|me|my|mine|myself)\b", re.I)
TRANSIENT = re.compile(r"\b(?:right now|at the moment|just now|this (?:morning|evening|week))\b", re.I)
GENERIC = {lx.stem(w) for w in "name call thing stuff something anything always usually often old".split()}
_CLAUSE = re.compile(r"\b(?:but|and|while|although|though|whereas)\b|[,;]", re.I)
POS = {"lov", "lik", "enjoy", "prefer", "ador", "favorit", "favourit"}
NEG = {"hat", "dislik", "despis", "detest", "loath"}
ANTONYMS = [("left", "right"), ("hot", "cold"), ("older", "younger"), ("mother", "father"), ("mom", "dad"), ("mum", "dad"), ("son", "daughter"),
            ("brother", "sister"), ("uncle", "aunt"), ("always", "never"), ("morning", "evening"), ("early", "late"), ("sweet", "bitter")]
_NAMED = re.compile(r"\b(" + REL_ALT + r")(?:'s)?(?: name)?(?: (?:is|was))?(?: (?:named|called))?,?\s+(?-i:([A-Z][a-z][\w'-]{1,20}))\b", re.I)
_NAMED2 = re.compile(r"\b(?:named|called|name (?:is|was)|name's)\s+([A-Z][a-z][\w'-]{1,20})")


def _pol(clause):
    st = {lx.stem(w) for w in re.findall(r"[a-z']+", clause.lower())}
    p, n = st & POS, st & NEG
    if re.search(r"\b(?:can't stand|cannot stand|don't like|do not like|doesn't like|never liked)\b", clause.lower()):
        n = n | {"x"}
    return "neg" if n else "pos" if p else None


def _anchors(a, b):
    return (set(lx.terms(a)) & set(lx.terms(b))) - GENERIC - POS - NEG


def _nums(t):
    return set(re.findall(r"(?<![\w.])(\d{1,4})(?:st|nd|rd|th)?(?![\w])", t))


def _named(text):
    out = {}
    for m in _NAMED.finditer(text):
        out.setdefault(m.group(1).lower(), set()).add(m.group(2).lower())
    return out


def conflict(a, b):
    """Do two statements about the same thing disagree? Deterministic and deliberately narrow: different numbers,
    opposite words (left/right, mother/father), love vs hate of the same thing, or different names for the same relation."""
    a, b = norm(a), norm(b)
    na, nb = _named(a), _named(b)
    for rel in set(na) & set(nb):
        if not (na[rel] & nb[rel]):
            return True
    if not _anchors(a, b):
        return False
    wa, wb = set(re.findall(r"[a-z']+", a.lower())), set(re.findall(r"[a-z']+", b.lower()))
    for x, y in ANTONYMS:
        if (x in wa and y in wb and x not in wb) or (y in wa and x in wb and y not in wb):
            return True
    da, db = _nums(a), _nums(b)
    if da and db and not (da & db):
        return True
    for ca in _CLAUSE.split(a):
        for cb in _CLAUSE.split(b):
            pa, pb = _pol(ca), _pol(cb)
            if pa and pb and pa != pb and _anchors(ca, cb):
                return True
    return False


def extract(umsgs, others=None, persona=""):
    """umsgs = [(index, text)] the user's messages, oldest first. others = {lower name: {'name','g',...}} known third people.
    -> [{owner: 'user' or a person's name, quote, turn, people}]"""
    others = others or {}
    out, seen = [], set()

    def add(owner, quote, turn, people):
        q = re.sub(r"\s+", " ", quote).strip(" \"'")
        if 6 <= len(q) <= 200 and q.lower() not in seen:
            seen.add(q.lower())
            out.append({"owner": owner, "quote": q, "turn": turn, "people": people})

    for turn, raw in ([(-1, persona)] if str(persona or "").strip() else []) + list(umsgs):
        last = None
        for s in sentences(speech_only(raw)):
            if len(s) < 6 or s.endswith("?") or TRANSIENT.search(s):
                last = None if FIRST.search(s) else last
                continue
            people = [o["name"] for k, o in others.items() if re.search(r"(?<![\w'])" + re.escape(o["name"]) + r"(?![\w'])", s)]
            for n, _rel in relations_in(s):
                if n not in people:
                    people.append(n)
            m = re.match(r"(?i)(she|he|they|her|his|their)\b", s)
            if m and last:
                p = others.get(last.lower()) or {}
                pg = {"she": "f", "her": "f", "he": "m", "his": "m"}.get(m.group(1).lower())
                if pg is None or p.get("g") in (None, pg):
                    add(p.get("name") or last, re.sub(r"(?i)^(?:she|he|they)\b", p.get("name") or last, s, count=1)
                        if m.group(1).lower() in ("she", "he", "they") else s.replace(m.group(1), (p.get("name") or last) + "'s", 1), turn, [p.get("name") or last])
                    continue
            if FIRST.search(s) or turn == -1:
                add("user", s, turn, people)
                last = people[0] if people else None
            elif people:
                add(people[0], s, turn, people)
                last = people[0]
            else:
                last = None
    return out[-200:]


def relevant(claims, text, skip_turn=None, cap=4):
    """The claims that bear on a message: shared content words (rarer ones count more) or a shared person."""
    q = speech_only(text)
    qt = set(lx.terms(q)) - GENERIC
    if not claims or not qt and not re.search(r"[A-Z]", q):
        return []
    pool = [c for c in claims if c["turn"] != skip_turn]
    df = {}
    for c in pool:
        for t in set(lx.terms(c["quote"])):
            df[t] = df.get(t, 0) + 1
    n = max(1, len(pool))
    ql = q.lower()
    scored = []
    for c in pool:
        shared = (set(lx.terms(c["quote"])) & qt) - GENERIC
        sc = sum(1 + math.log(1 + n / (1 + df[t])) for t in shared)
        names = {c["owner"]} | set(c.get("people") or [])
        if any(re.search(r"(?<![\w'])" + re.escape(p.lower()) + r"(?![\w'])", ql) for p in names if p and p != "user"):
            sc += 2.0
        if sc > 0:
            scored.append((sc, c["turn"], c))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [c for _, _, c in scored[:cap]]


def clip(text, n=170):
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"
