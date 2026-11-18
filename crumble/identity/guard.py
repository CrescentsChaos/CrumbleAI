"""Checks a finished reply for identity mistakes the prompt alone cannot prevent, and repairs what can be repaired.

    impersonation   the reply is written AS a person who was only mentioned (or addresses its own character by name)
    speaks_for_user the reply writes the user's own lines ('...,' Crescent replies)
    wrong_name      the user is called a name they said is not theirs
    misgender       he/she for someone whose gender is unknown or the other one
    contradiction   the reply states something that disagrees with what the user actually said
    invented        the user asked for something nobody ever told the character, and the reply answers anyway
    premise         the user's 'remember when I told you...' is false and the reply just agrees
"""
import re

from ..recall import lexicon as lx
from . import claims as cl
from .common import first_name, sentences, word_in
from .ledger import ADMIT, CORRECT, DONT_KNOW, user_labels

SAY = (r"replies|replied|says|said|asks|asked|answers|answered|responds|responded|whispers|whispered|murmurs|murmured|adds|added|laughs|laughed|"
       r"nods|nodded|smiles|smiled|sighs|sighed|shrugs|shrugged|exclaims|exclaimed|continues|continued|speaks|spoke|grins|grinned")
FEM, MASC = r"\b(?:she|her|hers|herself)\b", r"\b(?:he|him|his|himself)\b"
ANY = r"\b(?:she|her|hers|he|him|his|herself|himself)\b"


def _cut_before(text, pos):
    head = text[:pos]
    ends = [m.end() for m in re.finditer(r"[.!?…*][\"”)\]]?\s+|\n+", head)]
    return text[:ends[-1]].rstrip() if ends else ""


def check(text, led, mode="story"):
    """-> {'issues': [codes], 'note': str for a retry, 'text': repaired text}"""
    issues, notes, out = [], [], text
    ch, us = led["char"], led["user"]
    cname, cfirst = ch["name"], first_name(ch["name"])
    unames = user_labels(led)
    # 1. writing the user's lines (repairable: cut the reply before it)
    pos = None
    for u in unames:
        for rx in (rf'["”]\s*,?\s*{re.escape(u)}\s+(?:{SAY})\b', rf'(?m)^\s*[*_]*{re.escape(u)}\s+(?:{SAY})\b', rf'\*\s*{re.escape(u)}\s+(?:{SAY})\b',
                   rf'(?m)^\s*[*_]*{re.escape(u)}[*_]*\s*:', rf"\*\s*{re.escape(u)}\s+(?!and\b)[a-z]+(?:s|ed)\b"):   # the last one: '*Crescent walks away*'
            m = re.search(rx, out)
            if m and (pos is None or m.start() < pos):
                pos = m.start()
    if pos is not None:
        issues.append("speaks_for_user")
        notes.append(f"You wrote {unames[0]}'s own words or actions. Never do that: write only {cname}'s message and stop where {unames[0]} would answer.")
        cut = _cut_before(out, pos)
        if len(cut) >= 12:
            out = cut
    # 2. impersonation of a mentioned person, or addressing itself by its own name
    for o in led["others"].values():
        n = re.escape(o["name"])
        if re.match(rf"^[\s>_(]*\*\s*{n}(?:'s)?\b", out) or re.search(rf"(?i)\b(?:i'?m|i am|my name is|this is)\s+{n}\b", out):
            issues.append("impersonation")
            notes.append(f"You wrote as {o['name']}, who is only someone being talked about. You are {cname}. Speak and act only as {cname}.")
            break
    if re.search(rf'(?:^|["“]\s*|\n\s*){re.escape(cfirst)}\s*[,!]', out) and cfirst.lower() not in {u.lower() for u in unames}:
        issues.append("impersonation")
        notes.append(f"You addressed {cname} by name, so you were writing from someone else's side. You are {cname}: talk TO {unames[0]}.")
    for w in set(ch["slip"]) | set(ch["no"]):
        if re.search(rf"(?i)\b(?:i'?m|i am|my name is|call me)\s+{re.escape(w)}\b", out):
            issues.append("wrong_name")
            notes.append(f"Your name is {cname}, not {w}.")
            break
    # 3. calling the user by a wrong name
    bad = [w for w in us["wrong"] if word_in(w, out)]
    if bad:
        issues.append("wrong_name")
        notes.append(f"{unames[0]} is not called {bad[0]}. Call them {unames[0]}.")
    # 4. misgendering (only in sentences about one person, where the pronoun can be traced)
    people = [(n, us["g"] if i == 0 else None, True) for i, n in enumerate(unames[:1])]
    people += [(o["name"], o["g"], False) for o in led["others"].values()]
    for sent in sentences(out):
        if word_in(cname, sent) or word_in(cfirst, sent):
            continue
        named = [p for p in people if word_in(p[0], sent)]
        if len(named) != 1:
            continue
        name, g, is_user = named[0]
        after = sent[re.search(re.escape(name), sent, re.I).start():]
        wrong = (re.search(MASC, after, re.I) if g == "f" else re.search(FEM, after, re.I) if g == "m" else re.search(ANY, after, re.I) if (g in (None, "n") and is_user) else None)
        if wrong:
            issues.append("misgender")
            notes.append(f"Wrong pronoun for {name}: " + (f"use {'she/her' if g == 'f' else 'he/him'}." if g in ("f", "m") else "their gender is not stated, so use their name or \"you\", never he/she."))
            break
    # 5. contradicting what the user actually said
    p = led.get("probe") or {}
    hit = None
    for c in led.get("rel") or []:
        for s in sentences(out):
            if cl.conflict(c["quote"], s):
                hit = c
                break
        if hit:
            break
    if hit:
        issues.append("contradiction")
        notes.append(f"That contradicts what {unames[0]} actually said: \"{cl.clip(hit['quote'], 120)}\". Use exactly that.")
    # 5b. a recall question whose answer is on record, answered without using it
    if p.get("recall") and led.get("rel") and not hit and not p.get("premise"):
        top = led["rel"][0]
        qt = set(lx.terms(p.get("q", "")))
        new = {t for t in set(lx.terms(top["quote"])) - qt - cl.GENERIC if t not in {lx.stem(n.lower()) for n in unames + [cfirst]}}
        have = set(lx.terms(out))
        if new and not (new & have) and not DONT_KNOW.search(out):
            issues.append("ignored_fact")
            notes.append(f"{unames[0]} asked about something they already told you: \"{cl.clip(top['quote'], 120)}\". Answer from exactly that.")
    # 6. answering a question nobody ever answered
    if p.get("unknown") and not ADMIT.search(out) and "?" not in out:
        issues.append("invented")
        notes.append(f"{unames[0]} never told {cname} this. Do not invent it: {cname} does not know, and says so in character.")
    # 7. agreeing with a false 'remember when I told you'
    if p.get("premise") and not CORRECT.search(out):
        pol = {"neg": r"hat|dislik|despis|can't stand", "pos": r"lov|lik|enjoy|prefer"}.get(cl._pol(p["premise"]["quote"]) or "", "$^")
        if not re.search(pol, out, re.I):
            issues.append("premise")
            notes.append(f"{unames[0]} misremembers: they actually said \"{cl.clip(p['premise']['quote'], 120)}\". Gently correct them in character.")
    return {"issues": issues, "note": " ".join(notes), "text": out}
