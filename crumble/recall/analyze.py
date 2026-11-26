"""Reading the conversation: what the user's latest message is about (for retrieval), how memorable the moment was,
and which durable facts the user just stated. Pure functions, no model calls."""
import re
from collections import Counter

from . import lexicon as lx
from .store import resolve

SKIP_CAPS = set(("i the a an and but so well oh hey hi hello yes no yeah okay ok please thanks thank what why how when where who which "
                 "that this it he she they we you my your our his her their if then maybe just sure monday tuesday wednesday thursday "
                 "friday saturday sunday january february march april may june july august september october november december "
                 "mr mrs ms dr").split())
CAPS = re.compile(r"(?<![\w'])([A-Z][a-z]{2,})\b")
MENTION = re.compile(r"@([\w'-]{2,})")


def people_in(text, known=()):
    """Names in a text: @mentions, capitalised words in mid-sentence, and any name already known from memory."""
    t = str(text or "")
    found = [m.group(1) for m in MENTION.finditer(t)]
    kn = {k.lower(): k for k in known}
    for m in CAPS.finditer(t):
        w = m.group(1)
        if w.lower() in SKIP_CAPS or w.lower() in lx.EXTRA_STOP:
            continue
        found.append(w)
    for k in kn:
        if re.search(r"\b" + re.escape(k) + r"\b", t, re.I):
            found.append(kn[k])
    seen, out = set(), []
    for f in found:
        if f.lower() not in seen:
            seen.add(f.lower())
            out.append(f)
    return out


def known_people(items, skip=()):
    skip = {s.lower() for s in skip if s}
    return sorted({p for i in items for p in (i.get("people") or []) if p.lower() not in skip})


def query(user_text, context=(), mood="", known=(), skip=()):
    """What the latest user message is about.
    context = [(text, weight)] of nearby text (the character's last line, the scene) that colours it a little.
    -> {terms: Counter(stem -> weight), people, events, emo: [(group, valence)], mood: (group, valence), reach, explicit}"""
    qt = Counter()
    for s in lx.terms(user_text):
        qt[s] += 1.0
    for text, w in context:
        for s in set(lx.terms(text)):
            qt[s] = max(qt[s], w) if s in qt else w
    skip = {s.lower() for s in skip if s}
    return {"text": str(user_text or ""), "terms": qt, "people": [p for p in people_in(user_text, known) if p.lower() not in skip],
            "events": lx.categories(user_text), "emo": lx.emotions_in(user_text), "mood": lx.emotion_group(mood),
            "reach": bool(lx.REACH_BACK.search(user_text or "")), "explicit": bool(lx.EXPLICIT_KEEP.search(user_text or ""))}


def moment(user_text, reply_text, delta, mood_before, mood_after, model_imp=None):
    """How memorable the exchange that just happened was, 0..1, from cheap signals plus the model's own 0-10 rating."""
    cats = lx.categories(f"{user_text} {reply_text}")
    h = max([lx.EVENT_BAGS[c][0] for c in cats], default=0.0)
    d = abs(int(delta or 0))
    h += .15 if d >= 3 else .08 if d == 2 else 0
    if mood_after != mood_before and lx.is_strong(mood_after):
        h += .10
    if len((user_text or "").split()) >= 50:
        h += .05
    h = min(1.0, h)
    explicit = bool(lx.EXPLICIT_KEEP.search(user_text or ""))
    try:
        m = max(0.0, min(1.0, float(model_imp) / 10)) if model_imp is not None else None
    except (TypeError, ValueError):
        m = None
    score = h if m is None else .65 * m + .35 * h
    if explicit:
        score = max(score, .92)
    return {"score": round(score, 2), "cats": cats, "explicit": explicit, "heur": round(h, 2)}


# ---- durable facts the user states about themselves (works even when the model's JSON is unusable) ----
_NOT_OBJ = r"(?!(?:you|it|that|this|them|him|her|how|what|when|the way|being with)\b)"
_BORING_A = r"(?!(?:bit|little|lot|mess|wreck|bad|good|big|huge|real|total|complete|pain|fan of that)\b)"
FACT_RX = [
    (re.compile(r"\b(?i:call me|you can call me)\s+([A-Z][\w'-]{1,20})"), "{{{{user}}}} wants to be called {0}", .9, "user"),
    (re.compile(r"\b(?i:my name(?:'s| is))\s+([A-Z][\w'-]{1,20})"), "{{{{user}}}}'s name is {0}", .9, "user"),
    (re.compile(r"\bmy birthday(?:'s| is)\s+(?:on\s+)?([^.,;!?\n]{2,30})", re.I), "{{{{user}}}}'s birthday is {0}", .85, "user"),
    (re.compile(r"\bi(?:'m| am) from\s+([^.,;!?\n]{2,40})", re.I), "{{{{user}}}} is from {0}", .6, "user"),
    (re.compile(r"\bi(?:'m| am) (\d{1,2})(?: years old)?\b(?!\s*(?:minutes?|mins?|hours?|%|percent|seconds?))", re.I), "{{{{user}}}} is {0} years old", .6, "user"),
    (re.compile(r"\bi(?:'m| am) (?:allergic to|afraid of|scared of|terrified of)\s+([^.,;!?\n]{2,40})", re.I), "{{{{user}}}} is afraid of or allergic to {0}", .75, "user"),
    (re.compile(r"\bi(?:'m| am) (an? " + _BORING_A + r"[^.,;!?\n]{3,40})", re.I), "{{{{user}}}} is {0}", .55, "user"),
    (re.compile(r"\bi work\s+((?:as|at|in|for)\s+[^.,;!?\n]{2,40})", re.I), "{{{{user}}}} works {0}", .6, "user"),
    (re.compile(r"\bi live\s+(in\s+[^.,;!?\n]{2,40})", re.I), "{{{{user}}}} lives {0}", .6, "user"),
    (re.compile(r"\bmy (brother|sister|mom|mum|mother|dad|father|dog|cat|boss|best friend|friend|wife|husband|girlfriend|boyfriend|son|daughter|roommate|ex)\s+"
                r"(?:is named|is called|named|called)\s+([A-Z][\w'-]{1,20})"), "{{{{user}}}}'s {0} is called {1}", .65, "user"),
    (re.compile(r"\bi have (?:a|an|two|three|four|\d+) ((?:\w+ ){0,2}(?:brother|sister|dog|cat|kid|son|daughter|sibling|child|children|degree|car)s?)\b", re.I), "{{{{user}}}} has {0}", .5, "user"),
    (re.compile(r"\b(?:please |pls )?(?:don't|do not|never)\s+(interrupt|touch|ignore|lie to|yell at|shout at|talk about|bring up|mention|call me)\b([^.!?\n]{0,40})", re.I),
     "{{{{user}}}} asked {{{{char}}}} not to {0} {1}", .85, "bond"),
    (re.compile(r"\bi (?:really |absolutely |totally )?(?:hate|dislike|can't stand|cannot stand|despise)\s+((?:it when|being|when)\s+[^.!?\n]{2,50})", re.I), "{{{{user}}}} dislikes {0}", .82, "user"),
    (re.compile(r"\bi (?:really |absolutely |totally )?(?:hate|dislike|can't stand|cannot stand|despise)\s+(?!(?:it when|being|when)\b)" + _NOT_OBJ + r"([^.!?\n]{2,50})", re.I), "{{{{user}}}} dislikes {0}", .55, "user"),
    (re.compile(r"\bi (?:really |absolutely |totally )?(?:love|like|enjoy|adore|prefer)\s+" + _NOT_OBJ + r"([^.!?\n]{2,50})", re.I), "{{{{user}}}} likes {0}", .5, "user"),
]
_CLAUSE = re.compile(r",\s+(?=(?:my|i|and|but)\b)|;\s+|\s+(?:and|but)\s+(?=(?:i|my|please|don't)\b)", re.I)
_TRAIL = re.compile(r"\s+(?:and|but|because|so|which|that|though|although|while|when|until|if|as)\s+.*$", re.I)
_FIRST = ((re.compile(r"\bmy\b", re.I), "{{user}}'s"), (re.compile(r"\bme\b", re.I), "{{user}}"), (re.compile(r"\bmyself\b", re.I), "{{user}}"))


def _third(text):
    """First person -> the {{user}} placeholder, so a stored fact never says 'me' or 'my'."""
    for rx, rep in _FIRST:
        text = rx.sub(rep, text)
    return text
_TRANSIENT = re.compile(r"\b(?:right now|today|tonight|at the moment|this (?:morning|evening|week)|just now|a bit|a little|kind of|sort of)\b", re.I)


def user_facts(text):
    """[(text with placeholders, importance, subject)] for the lasting things the user just said about themselves."""
    out = []
    t = str(text or "").replace("’", "'")
    t = re.sub(r"\*[^*\n]*\*", " ", t)
    for sent in re.split(r"(?<=[.!?…])\s+|\n+", t):
        for s in _CLAUSE.split(sent):
            s = s.strip()
            if len(s) < 8 or s.endswith("?") or _TRANSIENT.search(s):
                continue
            for rx, fmt, imp, subj in FACT_RX:
                m = rx.search(s)
                if m:
                    g = [_TRAIL.sub("", re.sub(r"\s+", " ", x)).strip(" ,;:-\"'") for x in m.groups()]
                    f = re.sub(r"\s+", " ", _third(fmt.format(*g).replace("{{{{", "{{").replace("}}}}", "}}"))).strip()
                    if 8 <= len(f) <= 140 and f not in [o[0] for o in out]:
                        out.append((f, imp, subj))
                    break
    return out


BOUNDARY = re.compile(r"asked .* not to|dislikes (?:it when|being|when)|hates (?:it when|being)|doesn't like being|allergic|afraid of|scared of", re.I)
IDENTITY = re.compile(r"wants to be called|name is|birthday", re.I)
BOND = re.compile(r"\b(?:relationship|together|friends?|both|between|promised|couple|dating|partner|lovers?)\b", re.I)


def classify_fact(text):
    """-> (importance, subject) for a fact the model wrote, by what kind of fact it is."""
    subj = "bond" if (BOND.search(text) or ("{{user}}" in text and "{{char}}" in text)) else "self" if text.startswith("{{char}}") else "user"
    if IDENTITY.search(text):
        return .88, subj
    if BOUNDARY.search(text):
        return .85, subj
    if re.search(r"promise|agreed to|owes|plans to|will ", text, re.I):
        return .7, subj
    if re.search(r"\bis (?:a|an) |works|lives in|from\b", text, re.I):
        return .6, subj
    return .5, subj


def fallback_episode(user_text, cats):
    """When the model gives nothing usable for an important moment: a plain note of what the user said."""
    snip = re.sub(r"\s+", " ", re.sub(r"\*[^*\n]*\*", "", str(user_text or ""))).strip()[:130]
    if not snip:
        return ""
    tag = f" ({cats[0]} moment)" if cats else ""
    return f"{{{{user}}}} said \u201c{snip}\u201d{tag}"
