"""Who is who: names, name corrections, genders and relations. Pure functions, no model calls.

Everything here reads what was actually written (the sheet, the persona, the user's own messages), so it can
be re-derived from the chat at any time and stays correct when messages are edited, deleted or rewound."""
import re

from .common import first_name, norm, sentences, speech_only

FEMALE_REL = set("sister mom mum mother mommy mama aunt aunty grandmother grandma granny wife girlfriend daughter niece stepmother stepmom "
                 "stepsister fiancee queen princess waitress actress".split())
MALE_REL = set("brother dad father daddy papa uncle grandfather grandpa husband boyfriend son nephew stepfather stepdad stepbrother "
               "fiance king prince".split())
NEUTRAL_REL = set("friend bestfriend bff boss roommate ex cousin neighbor neighbour teacher coworker colleague dog cat pet partner bully rival "
                  "enemy sibling kid child mentor classmate crush manager landlord doctor therapist twin parent grandparent".split())
RELS = sorted(FEMALE_REL | MALE_REL | NEUTRAL_REL | {"best friend", "step mom", "step dad"}, key=len, reverse=True)
REL_ALT = "|".join(re.escape(r) for r in RELS)
NOT_NAMES = set(("i the a an and but so well oh hey hi hello yes no yeah okay ok please thanks thank what why how when where who which that this "
                 "it he she they we you my your our his her their if then maybe just sure monday tuesday wednesday thursday friday saturday "
                 "sunday january february march april may june july august september october november december mr mrs ms dr sorry fine good "
                 "tired happy sad angry hungry bored lost late ready back here there home okay alright nervous scared afraid glad curious "
                 "confused serious busy free single married alone done new old").split())
PRON = {"f": "she/her", "m": "he/him", "n": "they/them"}
_NAME = r"([A-Z][a-z][\w'-]{1,20})"


def rel_gender(rel):
    r = re.sub(r"[^a-z]", "", str(rel or "").lower()).rstrip("s") if str(rel or "").lower().endswith("friends") else re.sub(r"[^a-z]", "", str(rel or "").lower())
    return "f" if r in FEMALE_REL else "m" if r in MALE_REL else None


def parse_gender(text):
    """'Female (She/her)' -> 'f'; 'he/him' -> 'm'; 'non-binary' -> 'n'; unknown -> None. The earliest clear word wins."""
    t = norm(text).lower()
    if not t.strip():
        return None
    best = None
    for g, rx in (("n", r"\b(?:non-?binary|enby|genderqueer|they/them|agender|genderfluid)\b"),
                  ("f", r"\b(?:she/her|she|her|hers|female|woman|girl|lady|feminine|f)\b"),
                  ("m", r"\b(?:he/him|he|him|his|male|man|boy|guy|dude|masculine|m)\b")):
        m = re.search(rx, t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), g)
    return best[1] if best else None


def guess_gender(text):
    """Gender from running prose (a description): majority of she/her vs he/him, only when it is clear."""
    t = norm(text).lower()
    f, m = len(re.findall(r"\b(?:she|her|hers|herself)\b", t)), len(re.findall(r"\b(?:he|him|his|himself)\b", t))
    return "f" if f >= m + 2 else "m" if m >= f + 2 else None


_SELF_G = [
    (re.compile(r"\bI(?:'m| am)\s+(?!not\b)(?:an? )?(?:\d{1,2}[- ]years?[- ]old )?(?:young |little |grown |trans )?(girl|woman|female|lady)\b", re.I), "f"),
    (re.compile(r"\bI(?:'m| am)\s+(?!not\b)(?:an? )?(?:\d{1,2}[- ]years?[- ]old )?(?:young |little |grown |trans )?(guy|man|boy|male|dude)\b", re.I), "m"),
    (re.compile(r"\bI(?:'m| am)\s+(?!not\b)(?:an? )?(non-?binary|enby|genderqueer)\b", re.I), "n"),
    (re.compile(r"\bas an? (woman|girl|female|lady)\b", re.I), "f"),
    (re.compile(r"\bas an? (man|boy|guy|male)\b", re.I), "m"),
    (re.compile(r"\bmy pronouns are (she|he|they)\b", re.I), None),
    (re.compile(r"\b(?:i go by|use) (she|he|they)/", re.I), None),
]


def self_gender(text):
    """Does the user state their own gender in this message? -> 'f'/'m'/'n'/None"""
    t = speech_only(text)
    for rx, g in _SELF_G:
        m = rx.search(t)
        if m:
            return g or {"she": "f", "he": "m", "they": "n"}[m.group(1).lower()]
    return None


def _cap(n):
    n = (n or "").strip(" .,!?'\"")
    return n if n and n.lower() not in NOT_NAMES and n[0].isupper() else ""


_STATE = re.compile(r"\b(?i:my name(?:'s| is)|call me|you can call me|i go by|they call me|everyone calls me)\s+" + _NAME)
_IM = re.compile(r"(?:^|[.!?,]\s*|\b(?i:hi|hello|hey)\b[,!.]?\s*)(?i:i'm|i am)\s+" + _NAME + r"\b(?!\s*(?:not|a|an|the|so|very|too|going|just|really|feeling|from|here))")
_FIX_TO = re.compile(r"\b(?i:no|nope|actually|wrong|it'?s|its)\b[,.!]?\s+(?i:it'?s|its|i'?m|i am|my name(?:'s| is)|call me)\s+" + _NAME)
_ITS_NOT = re.compile(r"\b(?i:it'?s|its|i'?m|i am|my name(?:'s| is)|call me)\s+" + _NAME + r"\s*,?\s*(?i:not)\s+[A-Z]")
_NOT = [re.compile(p) for p in (
    r"\b(?i:my name(?:'s| is)(?: not| isn't)|i(?:'m| am) not called|don't call me|do not call me|stop calling me|not called)\s+" + _NAME,
    r"\b(?i:my name(?:'s| is)|it'?s|i'?m|i am|call me)\s+[A-Z][\w'-]+\s*,?\s*(?i:not)\s+" + _NAME,
    r"\b(?i:i'?m|i am) not " + _NAME,
    r"\b[Nn]ot " + _NAME + r"\s*,\s*(?i:it'?s|i'?m|i am|my name(?:'s| is)|call me)\s+[A-Z]",
)]
_YOUR = re.compile(r"\b(?i:your name(?:'s| is)|you(?:'re| are) (?:called|named)|you(?:'re| are))\s+" + _NAME + r"(?:\s*,?\s*(?i:not)\s+" + _NAME + r")?")
_YOUR_NOT = re.compile(r"\b(?i:your name(?:'s| is)(?: not| isn't)|you(?:'re| are) not(?: called)?)\s+" + _NAME)


def user_names(msgs):
    """msgs = [user message text, oldest first]. -> (name the user last asked for / stated, {names the user said are NOT theirs})
    'My name is Crescent, not Cres' -> ('Crescent', {'Cres'}); a later statement of a name takes it off the not-list."""
    name, wrong = "", set()
    for raw in msgs:
        t = speech_only(raw)
        for sent in sentences(t) or [t]:
            for rx in _NOT:
                for m in rx.finditer(sent):
                    n = _cap(m.group(1))
                    if n:
                        wrong.add(n)
            for rx in (_STATE, _FIX_TO, _ITS_NOT, _IM):
                m = rx.search(sent)
                if m:
                    n = _cap(m.group(1))
                    if n and n.lower() not in {w.lower() for w in wrong}:
                        name = n
                        break
    wrong = {w for w in wrong if w.lower() != name.lower()}
    return name, wrong


def char_names_said(msgs, real):
    """What the user says the CHARACTER is called. -> (names the user wrongly used for them, names the user said are not theirs).
    The character's real name always comes from the sheet; a different name from the user is a slip to correct in character."""
    slip, no = set(), set()
    real_l = {real.lower(), first_name(real).lower()}
    for raw in msgs:
        t = speech_only(raw)
        for m in _YOUR_NOT.finditer(t):
            n = _cap(m.group(1))
            if n:
                no.add(n)
        for m in _YOUR.finditer(t):
            n = _cap(m.group(1))
            if n and n.lower() not in real_l and not re.match(r"(?i)you(?:'re| are)\s+" + re.escape(n) + r"\b(?=\s+(?:a|an|the)\b)", m.group(0)):
                slip.add(n)
            if m.group(2) and _cap(m.group(2)):
                no.add(_cap(m.group(2)))
    return {s for s in slip if s.lower() not in real_l}, {n for n in no if n.lower() not in real_l}


_REL1 = re.compile(r"\b(?i:my)\s+((?i:" + REL_ALT + r"))(?i:'s name (?:is|was)|(?: is| was) (?:named|called)| (?:named|called)| name is| name was|,)\s+" + _NAME)
_REL2 = re.compile(r"\b(?i:my)\s+((?i:" + REL_ALT + r"))\s+" + _NAME)
_REL3 = re.compile(r"\b" + _NAME + r" (?i:is|was) (?i:my)\s+(?:\w+ )?((?i:" + REL_ALT + r"))\b")


def relations_in(text):
    """The user's own relations introduced in one message. -> [(name, relation)]"""
    t = speech_only(text)
    out = []
    for rx, ni, ri in ((_REL1, 2, 1), (_REL2, 2, 1), (_REL3, 1, 2)):
        for m in rx.finditer(t):
            n, rel = _cap(m.group(ni)), m.group(ri).lower()
            if n and n[0].isupper() and not any(o[0].lower() == n.lower() for o in out):
                out.append((n, rel))
    return out


def sheet_people(c):
    """People the character's own sheet lists under Relationships ('Uncle: Jeb. Bestfriends: Lenny, Julia.'). -> [(name, relation)]"""
    out = []
    t = norm((c or {}).get("relationships"))
    for seg in re.split(r"[.;\n]+", t):
        m = re.match(r"\s*([A-Za-z][A-Za-z' -]{1,30}?)\s*:\s*(.+)", seg)
        if m:
            rel = re.sub(r"s$", "", m.group(1).strip().lower()) if m.group(1).strip().lower().endswith(("friends", "siblings", "parents")) else m.group(1).strip().lower()
            for n in re.split(r",|\band\b|&", m.group(2)):
                n = re.sub(r"\(.*?\)", "", n).strip()
                if re.fullmatch(r"[A-Z][\w'-]+(?: [A-Z][\w'-]+)?", n) and n.lower() not in NOT_NAMES:
                    out.append((n, rel))
            continue
        for n, rel in re.findall(r"([A-Z][\w'-]+)\s*(?:\(|-|–)\s*([A-Za-z' ]{2,25})\)?", seg):
            if n.lower() not in NOT_NAMES:
                out.append((n, rel.strip().lower()))
    return out
