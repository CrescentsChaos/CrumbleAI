"""Keeping memory honest. The mood tracker and the summariser are small models that read the whole exchange,
including the character's own inventions, so what they propose is checked here before it is stored:

    grounded     a fact about the user must be supported by the user's own words, not only by the character's reply
    owned        facts about people the USER introduced are never stored as the character's
    not shared   'both had a dog named Bruno as kids' is dropped unless the user actually said 'we'
    neutral      he/she/his/her for a user whose gender was never stated becomes they/their
"""
import re

from ..recall import lexicon as lx
from .claims import NEG, POS
from .common import first_name, speech_only
from .names import PRON

SHARED = re.compile(r"\b(?:both|also|shared|same|together|in common|too)\b", re.I)
PAST = re.compile(r"\b(?:childhood|growing up|grew up|as (?:kids|children)|when (?:they|we|she|he) were (?:kids|young|little|children)|years ago|back then|used to)\b", re.I)
MEETING = re.compile(r"\b(?:reunit\w*|hug\w*|embrac\w*|visit\w*|walk\w* (?:with|together)|met with|greet\w*|kiss\w*)\b", re.I)
_BE = {"was": "were", "is": "are", "has": "have", "does": "do", "doesn't": "don't", "wasn't": "weren't", "isn't": "aren't", "hasn't": "haven't"}


def _canon(ts):
    return {"POS" if t in POS else "NEG" if t in NEG else t for t in ts}


def neutralize(text, g=None):
    """Pronouns for the user in a stored sentence. Unknown / non-binary gender -> they/them; a known gender -> that gender's pronouns."""
    t = str(text or "")
    if g in ("f", "m"):
        sub = {"f": ("she", "her", "her", "herself", "hers"), "m": ("he", "his", "him", "himself", "his")}[g]
        wrongs = ((r"he", sub[0]), (r"his", sub[1]), (r"him", sub[2]), (r"himself", sub[3])) if g == "f" else ((r"she", sub[0]), (r"hers", sub[4]), (r"herself", sub[3]))
        for w, r in wrongs:
            t = re.sub(rf"\b{w}\b", lambda m: r.capitalize() if m.group(0)[0].isupper() else r, t, flags=re.I)
        return t
    t = re.sub(r"\b(she|he)(?:'s| is)\b", lambda m: "They're" if m.group(1)[0].isupper() else "they're", t, flags=re.I)
    t = re.sub(r"\b(?:she|he) (was|is|has|does|doesn't|wasn't|isn't|hasn't)\b", lambda m: "they " + _BE[m.group(1).lower()], t, flags=re.I)
    t = re.sub(r"\b(?:she|he)\b", lambda m: "They" if m.group(0)[0].isupper() else "they", t, flags=re.I)
    t = re.sub(r"\bhimself|herself\b", "themself", t, flags=re.I)
    t = re.sub(r"\bhers\b", "theirs", t, flags=re.I)
    t = re.sub(r"\bhis\b", "their", t, flags=re.I)
    t = re.sub(r"\b(?:her|him)\b(?=\s+(?:to|for|about|with|at|in|on|up|out|a|an|the|that|this|and|but|when)\b|[.,;!?]|$)", "them", t, flags=re.I)
    t = re.sub(r"\bher\b", "their", t, flags=re.I)
    t = re.sub(r"\bhim\b", "them", t, flags=re.I)
    return t


def make_guard(led, user_texts):
    """-> fn(text, kind) -> cleaned text, or None when it should not be stored. kind: fact | episode | feeling | event | scene.
    Texts use the {{user}} / {{char}} placeholders."""
    ug = led["user"]["g"] if led else None
    texts = " ".join(speech_only(t) for t in user_texts)
    ut = _canon(set(lx.terms(texts)))
    we = bool(re.search(r"\b(?:we|us|our|together|both)\b", texts, re.I))
    user_others = [o["name"] for o in (led or {}).get("others", {}).values() if o["owner"] == "user"]
    names = {n.lower() for n in [led["char"]["name"], first_name(led["char"]["name"])] + list(led["user"].get("wrong") or [])} if led else set()
    from .ledger import user_labels
    names |= {n.lower() for n in (user_labels(led) if led else [])}

    def has_other(t):
        return any(re.search(r"(?<![\w'])" + re.escape(n) + r"(?![\w'])", t) for n in (led or {}).get("others", {}) and [o["name"] for o in led["others"].values()])

    def g(text, kind="fact"):
        t = re.sub(r"\s+", " ", str(text or "")).strip()
        if not t:
            return None
        both = "{{user}}" in t and "{{char}}" in t
        if SHARED.search(t) and PAST.search(t) and both and not we:
            return None     # a shared past nobody established
        if kind in ("fact", "episode", "feeling") and t.startswith("{{char}}") and any(re.search(r"(?<![\w'])" + re.escape(n) + r"(?![\w'])", t) for n in user_others):
            if kind == "fact" or MEETING.search(t) and "{{user}}" not in t:
                return None     # the user's relatives are the user's, and they are not in the room because they were mentioned
        if kind == "fact" and not t.startswith("{{char}}"):
            terms = [x for x in lx.terms(re.sub(r"\{\{(?:user|char)\}\}", " ", t)) if x not in names]
            ft = _canon(set(terms))
            if ft and len(ft & ut) / len(ft) < .7:
                return None     # not supported by anything the user said
        if "{{user}}" in t and "{{char}}" not in t and not has_other(t):
            t = neutralize(t, ug)
        return t
    return g


def sanitize_summary(summary, led, user_texts=(), persona=""):
    """Remove what a summariser tends to invent: ages nobody stated, a gender for the user."""
    s = str(summary or "")
    if not s.strip() or not led:
        return s
    said = " ".join(list(user_texts) + [persona or ""])
    said_nums = set(re.findall(r"\b\d{1,2}\b", said))
    cname, cfirst = led["char"]["name"], first_name(led["char"]["name"])
    unames = [n for n in {led["user"]["name"], led["user"]["ui"]} if n]
    allnames = [(n, "u") for n in unames] + [(cname, "c"), (cfirst, "c")] + [(o["name"], "o") for o in led["others"].values()]

    def owner_before(text, pos):
        best = (-1, None)
        for n, kind in allnames:
            for mm in re.finditer(re.escape(n), text[:pos], re.I):
                if mm.start() > best[0]:
                    best = (mm.start(), kind)
        return best[1]

    out = []
    for line in s.split("\n"):
        for m in list(re.finditer(r"(?:,\s*|\s)\(?(?:aged? )?(\d{1,2})[- ]years?[- ]old\)?|\baged? (\d{1,2})\b", line)):
            num, who = m.group(1) or m.group(2), owner_before(line, m.start())
            keep = (num == led["char"]["age"]) if who == "c" and led["char"]["age"] else (num in said_nums) if who == "u" else True
            if not keep:
                line = line.replace(m.group(0), "", 1)
        if not led["user"]["g"]:     # a gender nobody gave the user: neutralise clause by clause, only where just the user is named
            parts = re.split(r"(;)", line)
            for i, part in enumerate(parts):
                has_u = any(re.search(re.escape(n), part, re.I) for n in unames)
                has_x = any(re.search(re.escape(n), part) for n in (cname, cfirst)) or any(re.search(re.escape(o["name"]), part) for o in led["others"].values())
                if has_u and not has_x:
                    parts[i] = neutralize(part, None)
            line = "".join(parts)
        out.append(line)
    return "\n".join(out)
