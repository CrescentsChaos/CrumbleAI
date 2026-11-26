"""Reading a conversation for what deserves remembering. Deterministic, no model call, so it runs on every message and cannot invent anything.

Every candidate memory carries the answers a roleplay needs later:

    who      the speaker or actor ({{user}} / {{char}} / a real name)
    about    the other people it concerns
    kind     promise | plan | secret | gift | decision | event | fact | relationship | claim | feeling | body | hypothetical
    status   confirmed | uncertain (hearsay, hedged) | hypothetical (imagined, "what if", a joke)
    rsrc     where it came from, which decides who wins a conflict: user | scene | char | report
    open     a promise or plan that has not been resolved yet
    known_by who was there (empty = everyone); a whisper reaches only the people it was whispered to
    evid     the exact words it came from, so every memory can be checked against the chat

What the character does counts as much as what the user says: "*She hands over a silver locket*" is a memory.
A sentence that is imagined ("what if I kissed you?"), asked, or only reported by someone else is never stored as something that happened.
"""
import re

from ..textutil import THINK
from . import analyze, entities as en, lexicon as lx

U, C = en.U, en.C

# ---- modality: did it really happen? ----
HYPO = re.compile(r"(?i)\b(?:what if|imagine|suppose|supposing|pretend|let'?s say|hypothetically|if (?:i|you|we|he|she|they) (?:were|was|had|could|did|would)|"
                  r"if only|i wish|in (?:my|a) dream|daydream\w*|someday maybe|just kidding|kidding|jk|as a joke|joking|for fun|in theory|"
                  r"would have|could have|should have|might have|i would|you would|we would|he would|she would|they would|wouldn'?t it be|"
                  r"what would happen|play(?:ing)? (?:along|pretend)|roleplay(?:ing)? as)\b")
HEDGE = re.compile(r"(?i)\b(?:i think|i guess|i suppose|maybe|perhaps|probably|supposedly|i heard|they say|people say|rumou?r(?:s|ed)?|apparently|not sure|might|i believe|allegedly|"
                   r"it seems|looks like|i assume)\b")
REPORT = re.compile(r"(?P<src>[A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,})?|[Hh]e|[Ss]he|[Tt]hey|[Ee]veryone|[Pp]eople|[Ss]omeone|the \w+)\s+"
                    r"(?P<verb>said|says|told|tells|claims?|claimed|mentioned|swore|insists?|insisted|heard|thinks?|thought|believes?|reckons|reported|whispered|"
                    r"announced|admitted|confessed|saw|noticed)\s+(?:(?P<to>me|us|you|him|her|them|[A-Z][a-z]{2,})\s+)?(?:that\s+)?(?P<claim>.+)", re.I)
ACCUSE = re.compile(r"(?i)\b(?:lying|liar|lies|traitor|thief|cheat\w*|guilty|fake|fraud|spy|crooked|untrustworthy|betray\w*|murderer|killer)\b")
SECRET = re.compile(r"(?i)\b(?:secret\w*|don'?t tell|do not tell|don'?t (?:mention|breathe a word|say a word|speak of)|do not mention|not a word|between us|nobody knows|no one knows|never told (?:anyone|anybody)|confess\w*|keep (?:this|it) (?:quiet|secret|between us)|off the record)\b")
WHISPER = re.compile(r"(?i)\b(?:whisper\w*|leans? in|lean(?:ed|s) close|pulls? \w+ aside|quietly (?:tells?|says?|told|said)|murmurs? to|in (?:his|her|their) ear|privately)\b")
PROMISE = re.compile(r"(?i)\b(?:i|we)\s+(?:promise|swear|vow|pledge)\b|\b(?:i'?ll|i will|we'?ll|we will)\s+(?:always|never|definitely|absolutely)\b|\bcross my heart\b|\byou have my word\b|\bon my (?:life|honou?r)\b|\bi give you my word\b")
COMMIT = re.compile(r"(?i)\b(?:i'?ll|i will|we'?ll|we will|i'?m going to)\s+(?:be there|meet|come|bring|pay|return|wait|help|protect|find|fix|visit|call|write|see you|take you|show you|bring you|keep|stay|watch|get you|do it|go with)\b")
TIMECUE = re.compile(r"(?i)\b(?:tomorrow|tonight|today at|next (?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
                     r"at (?:noon|midnight|dawn|dusk|sunrise|sunset|\d{1,2}(?::\d\d)?\s*(?:am|pm|o'?clock)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)|"
                     r"by (?:friday|monday|tomorrow|midnight|noon|dawn|nightfall)|in (?:an hour|a few days|two days|three days|a week|the morning)|this (?:evening|weekend)|later tonight)\b")
MEETCUE = re.compile(r"(?i)\b(?:meet(?:ing|s)?|appointment|see you|come|arrive|go|wait|visit|pick (?:you )?up|dinner|lunch|date|leave|head|be there|rendezvous|show up|gather)\b")
GIVE = re.compile(r"(?i)\b(?P<v>gives?|gave|hands?(?: over)?|handed(?: over)?|offers?|offered|presents?|presented|passes|passed|slides|slid|tosses|tossed|buys?|bought|lends?|lent|returns|returned|"
                  r"brings?|brought|hung|hangs|fastens|clasps|places|placed|pressed|presses|slips|slipped|sends|sent|made|baked|knitted|carved|wrapped|wraps|tucks|tucked|drapes|draped|pins|pinned|ties|tied|lays|laid|puts|put|leaves)\s+"
                  r"(?:(?P<r>you|me|her|him|them|us|[A-Z][a-z]{2,})\s+)?(?P<np>(?:a|an|the|his|her|their|my|your|our|some|this|that)\s+[a-z][^.!?;\n]{2,70})")
GIVE_SP = re.compile(r"(?i)\b(?:i|we)\s+(?:got|made|bought|brought|baked|found|picked|saved|kept)\s+(?P<r>you|her|him|them)\s+(?P<np>(?:a|an|the|some|this)\s+[a-z][^.!?;\n]{2,60})")
DECIDE = re.compile(r"(?i)\b(?:(?:we|i|they)\s+(?:decided|agreed|settled|chose|have decided|made a decision)|(?:it'?s|that'?s)\s+(?:settled|decided)|(?:we|i)(?:'ll| will) (?:go with|take|do) (?:it|that|the))\b|\bdeal\b[.!]?$")
BODY = re.compile(r"(?i)\b(?:is dead|died|dies|killed|was killed|wounded|injured|(?:broke|breaks|broken) (?:his|her|my|your|their) (?:arm|leg|wrist|rib|nose|ankle|finger)|bleeding|poisoned|unconscious|"
                  r"fell ill|is sick|caught (?:a )?(?:fever|cold|plague)|is pregnant|lost (?:his|her|my|your) (?:eye|hand|arm|leg|memory|voice))\b")
EMO_WORDS = sorted({w for _, words in lx.EMOTIONS.values() for w in words.split()}, key=len, reverse=True)
FEEL = re.compile(r"(?i)\bi(?:'m| am| feel| felt| was| have been|'ve been)\s+(?:so |really |very |deeply |a bit |kind of |truly |incredibly )?(" + "|".join(EMO_WORDS) + r")\b")
STATE = re.compile(r"(?i)\b(?:is|was|are|were|has|had|owes|owed|works?|lives?|hates?|loves?|likes?|wants?|needs?|knows?|allergic|afraid|scared of|sick|dead|missing|married|pregnant|leaving|left|stole|saw|killed|betrayed|trusts?|fears?|keeps?|hid|hides?)\b")
EVENT_VERBS = {  # verb stem -> importance of a scene in which it happens
    "kiss": .82, "hug": .66, "embrace": .66, "slap": .75, "punch": .75, "hit": .65, "stab": .85, "shoot": .85, "kill": .88, "rescue": .8, "save": .78, "carry": .6, "propose": .9,
    "betray": .85, "steal": .75, "burn": .7, "marry": .9, "faint": .72, "collapse": .72, "cry": .62, "weep": .62, "sob": .62, "storm": .62, "slam": .6, "kneel": .62, "fight": .75, "duel": .8,
    "arrest": .8, "capture": .8, "escape": .78, "flee": .7, "lock": .55, "unlock": .55, "heal": .7, "bandage": .65, "dance": .6, "sing": .5, "arrive": .5, "leave": .55, "enter": .5, "cook": .45,
    "lead": .52, "walk": .5, "light": .5, "open": .5, "visit": .55, "confess": .8, "apologize": .7, "forgive": .75, "refuse": .6, "agree": .55, "reveal": .75, "discover": .7, "find": .55, "lose": .6, "win": .65, "swim": .5, "climb": .5, "drink": .45,
}
_VERB_RX = re.compile(r"\b(" + "|".join(sorted(EVENT_VERBS, key=len, reverse=True)) + r")(?:s|es|ed|d|ing)?\b", re.I)
_IRREG_EVENT = {"stole": "steal", "stolen": "steal", "fought": "fight", "fled": "flee", "found": "find", "lost": "lose", "won": "win", "left": "leave", "wept": "weep", "drank": "drink",
                "hit": "hit", "slammed": "slam", "knelt": "kneel", "swam": "swim", "struck": "hit", "froze": "freeze", "fell": "faint", "forgave": "forgive", "betrayed": "betray"}
PLACE_MOVE = re.compile(r"(?i)\b(?:leads?|led|takes?|took|walks?|walked|brings?|brought|guides?|guided|enters?|entered|steps?|stepped|goes|went|climbs?|climbed|follows?|followed|rushes|rushed|runs|ran|sneaks?|sneaked)\b[^.!?]*?\b(?:into|inside|toward|towards|to)\s+(?:the\s+)?(?:(?:old|ancient|small|big|dark|abandoned|tall|empty)\s+)?[a-z]{3,}")
CONT = re.compile(r"^(?:It|That|This|They|These|Those|He|She|And|But|Inside|There)\b")
_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
_STAR = re.compile(r"\*+([^*\n]+?)\*+")
_MENT = re.compile(r"@([\w'-]{2,})")
TAGQ = re.compile(r"(?i),\s*(?:okay|ok|right|alright|yeah|deal|yes|alright then|all right)\s*\?$")
IMPERATIVE = re.compile(r"(?i)^\W*(?:meet|come|bring|be|wait|promise|swear|remember|don'?t forget|stay|call|write|find|help)\b")
FIRST_PERSON_START = re.compile(r"(?i)^(?:i|i'm|i've|i'll|i'd|we|we're|my|me)\b")

ORDER = ("hypothetical", "promise", "secret", "gift", "plan", "decision", "body", "event", "fact", "relationship", "claim", "feeling")


def clip(s, n=150):
    s = re.sub(r"\s+", " ", str(s or "")).strip(" \"'“”*_")
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:- ") + "…"


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[*_\"“”]", "", str(s or ""))).strip().lower()


def segments(text, speaker_name=""):
    """A message -> [(mode, sentence)]; *asterisks* are narration, the rest is speech. Plain third-person prose about the speaker
    ('Mira smiles and hands him the key.') is narration too; 'Garrick is lying.' is something said."""
    out, pos = [], 0
    t = str(text or "")
    for m in _STAR.finditer(t):
        out += [("speech", s) for s in _SPLIT.split(t[pos:m.start()]) if s.strip()]
        out += [("narr", s) for s in _SPLIT.split(m.group(1)) if s.strip()]
        pos = m.end()
    out += [("speech", s) for s in _SPLIT.split(t[pos:]) if s.strip()]
    first = (speaker_name or "").split(" ")[0]
    subj = r"(?:She|He|They" + (r"|" + re.escape(first) if first else "") + r")"
    res = []
    for mode, s in out:
        s = s.strip()
        if (mode == "speech" and s and not s.startswith(('"', "“")) and not FIRST_PERSON_START.match(s)
                and re.match(r"^" + subj + r"\s+(?!is\b|was\b|has\b|had\b|will\b|can\b|would\b|should\b|could\b|isn't\b|wasn't\b)\w+(?:ed|s)\b", s)):
            mode = "narr"
        if s:
            res.append((mode, s))
    return res


def _ph(name, user, char):
    return en._ph(name, user, char)


def _third(s, speaker, other):
    """First and second person -> names, so a stored line never says 'me' or 'you' (the model must not mix the two people up)."""
    sp, ot = speaker or "someone", other or "the other person"
    subs = [(r"\bI'm\b", f"{sp} is"), (r"\bI've\b", f"{sp} has"), (r"\bI'll\b", f"{sp} will"), (r"\bI'd\b", f"{sp} would"), (r"\bI\b", sp), (r"\bmyself\b", sp),
            (r"\bmy\b", f"{sp}'s"), (r"\bmine\b", f"{sp}'s"), (r"\bme\b", sp), (r"\byou're\b", f"{ot} is"), (r"\byou'll\b", f"{ot} will"), (r"\byou've\b", f"{ot} has"),
            (r"\byour\b", f"{ot}'s"), (r"\byours\b", f"{ot}'s"), (r"\byourself\b", ot), (r"\byou\b", ot)]
    for rx, rep in subs:
        s = re.sub(rx, rep, s, flags=re.I if rx not in (r"\bI\b",) else 0)
    return s


def _pron_subject(s, speaker):
    return re.sub(r"^(?:She|He|They|It)\b", speaker, s, count=1) if speaker else s


def _when(s):
    m = TIMECUE.search(s)
    return m.group(0).lower() if m else ""


def _canon_verb(w):
    w = w.lower()
    if w in _IRREG_EVENT:
        return _IRREG_EVENT[w]
    return lx.stem(w)


def _event_score(s):
    best = (0.0, "")
    for m in _VERB_RX.finditer(s):
        v = _canon_verb(m.group(1))
        sc = EVENT_VERBS.get(m.group(1).lower().rstrip("s"), EVENT_VERBS.get(v, 0))
        if sc > best[0]:
            best = (sc, v)
    return best


class Ctx:
    def __init__(self, user, char, mem, group_names=()):
        self.user, self.char, self.mem, self.group = user, char, mem, [g for g in group_names if g]


def _addressee(s, speaker_ph, c, speaker_is_user):
    """Who a line is directed at: an @mention or a vocative if named, else the other person of the one-to-one chat."""
    m = re.search(r"@([\w'-]+)", s)
    if m:
        return _ph(en.canon(c.mem, m.group(1)), c.user, c.char)
    m = re.match(r"^\W*([A-Z][a-z]{2,}),\s", s)
    if m:
        return _ph(en.canon(c.mem, m.group(1)), c.user, c.char)
    if c.group and not speaker_is_user:
        return U
    return C if speaker_is_user else U


def _cand(kind, text, who, evid, imp, **kw):
    d = {"kind": kind, "text": text, "who": who, "evid": clip(evid, 160), "imp": imp, "status": "confirmed", "rsrc": "char", "open": False, "about": [], "when": "",
         "known_by": [], "slot": "", "obj": "", "emo": "", "layer": "episodic", "subj": "bond", "pin": False}
    d.update(kw)
    return d


def read(msgs, user="", char="", mem=None, *, start=0, group_names=(), prev=None):
    """Candidate memories in these messages. msgs: [{role, content, name?, ooc?, dyn?}]; start = the absolute index of msgs[0] in the chat.
    -> [candidate dict, each with msg = its absolute message index]"""
    mem = mem if mem is not None else {}
    en.ensure(mem)
    c = Ctx(user, char, mem, group_names)
    out = []
    for k, m in enumerate(msgs or []):
        if not isinstance(m, dict) or m.get("ooc") or (isinstance(m.get("dyn"), dict) and m["dyn"].get("quirk") in ("lie", "misunderstand")):
            continue            # out-of-character talk is not the story; a lie or a deliberate misreading is not a fact
        idx = start + k
        is_user = m.get("role") == "user"
        spk_real = user if is_user else (m.get("name") or char or "Character")
        spk = _ph(spk_real, user, char) if is_user or not m.get("name") else (_ph(m["name"], user, char))
        if not is_user and not m.get("name"):
            spk = C
        text = THINK.sub("", str(m.get("content") or "")).replace("’", "'")
        if not text.strip():
            continue
        per = []
        explicit = bool(lx.EXPLICIT_KEEP.search(text))
        segs = segments(text, spk_real)
        for si, (mode, s0) in enumerate(segs):
            nxt = segs[si + 1][1] if si + 1 < len(segs) and segs[si + 1][0] == mode else ""
            per += _sentence(s0, mode, spk, is_user, c, explicit, nxt)
        pv = (msgs[k - 1] if k > 0 else prev) if (k > 0 or prev) else None
        ctx = clip(re.sub(r"[*_]", "", THINK.sub("", str((pv or {}).get("content") or ""))), 100) if pv and not pv.get("ooc") else ""
        wm = re.search(r"(?i)(?:whisper\w*|murmur\w*|quietly (?:tells?|told|says?|said))\s+(?:to\s+)?@?([A-Z][a-z]{2,})", text) or (WHISPER.search(text) and _MENT.search(text))
        priv_to = _ph(en.canon(mem, wm.group(1)), user, char) if (wm and c.group) else ""
        for cand in per:
            cand["msg"] = idx
            cand["speaker"] = spk
            if ctx and cand["kind"] in ("gift", "event", "plan", "promise", "decision", "body", "secret", "claim"):
                cand["ctx"] = ctx
            if priv_to and priv_to != spk:
                cand["known_by"] = [spk, priv_to]               # a whisper reaches only the person it was whispered to
        per.sort(key=lambda d: (-d["imp"], ORDER.index(d["kind"]) if d["kind"] in ORDER else 99))
        hyp = [d for d in per if d["kind"] == "hypothetical"][:1]
        out += ([d for d in per if d["kind"] != "hypothetical"] + hyp)[:5]
        # who is in the chat: so a name seen once is recognised the next time it is mentioned
        en.observe(mem, text, user, char, speaker=spk_real, turn=idx, ts=m.get("ts") or 0, extra=group_names)
    return _dedupe(out)


def _dedupe(cands):
    seen, out = set(), []
    for d in cands:
        k = (d["kind"], norm(d["evid"])[:80], d["who"], d["text"][:70])
        if k in seen:
            continue
        seen.add(k)
        out.append(d)
    return out


def _sentence(s0, mode, spk, is_user, c, explicit, nxt=""):
    s = re.sub(r"\s+", " ", s0).strip()
    if len(s) < 6:
        return []
    other = _addressee(s, spk, c, is_user)
    out = []
    plain = s.strip(" \"“”")
    if plain.endswith("?") and not PROMISE.search(plain) and not TAGQ.search(plain) and not IMPERATIVE.match(plain):
        return []
    names = en.detect(plain, c.mem, c.user, c.char, speaker=spk)
    hedged = bool(HEDGE.search(plain))
    # --- imagined, joked about or hypothetical: remembered as that, never as an event ---
    if HYPO.search(plain):
        if len(plain.split()) >= 5:
            out.append(_cand("hypothetical", f"{spk} imagined or joked (not real): “{clip(plain, 120)}”", spk, plain, .2, status="hypothetical", rsrc="char" if not is_user else "user", about=names[:3]))
        return out
    third = _pron_subject(_third(plain, spk, other), spk if mode == "narr" else "")
    # --- someone else said / heard / claims something: a claim, not a fact ---
    m = REPORT.search(plain)
    if m and m.group("claim") and len(m.group("claim").split()) >= 3:
        src_raw = m.group("src")
        vague = src_raw.lower() in ("he", "she", "they", "everyone", "people", "someone")
        src = "someone" if vague and src_raw.lower() in ("someone", "everyone", "people") else "" if vague else _ph(en.canon(c.mem, src_raw), c.user, c.char)
        if src and src != spk:
            claim = _third(m.group("claim"), spk, other)
            claim = re.sub(r"^(?:he|she|they)\b", src if src != "someone" else "they", claim, count=1, flags=re.I)
            to_raw = (m.group("to") or "").lower()
            to = {"me": spk, "us": f"{spk} and {other}", "you": other}.get(to_raw, _ph(en.canon(c.mem, m.group("to")), c.user, c.char) if m.group("to") else "")
            told = f" to {to}" if to and m.group("verb").lower() in ("told", "tells", "whispered") else ""
            per = "" if to == spk else f"per {spk}, "
            out.append(_cand("claim", f"{src} said{told} ({per}second-hand, unverified): {clip(claim, 130)}", src, plain, .55, status="uncertain",
                             rsrc="report", about=[src] + [n for n in names if n != src][:3], layer="episodic"))
            return out
    # --- a secret ---
    if SECRET.search(plain):
        kb = [spk, other] if (WHISPER.search(s0) or re.search(r"(?i)between us|don'?t tell", plain)) and c.group else []
        out.append(_cand("secret", f"{spk} confided a secret to {other}: “{clip(plain, 130)}”" if not hedged else f"{spk} hinted at a secret: “{clip(plain, 130)}”", spk, plain, .86,
                         about=names[:3] + ([other] if other not in names else []), rsrc="user" if is_user else "char", known_by=kb, pin=False))
    # --- a promise ---
    if PROMISE.search(plain) or (COMMIT.search(plain) and mode == "speech" and (TIMECUE.search(plain) or MEETCUE.search(plain))):
        out.append(_cand("promise", f"{spk} promised {other}: “{clip(plain, 130)}”", spk, plain, .86, open=True, when=_when(plain), about=[other] + names[:2], rsrc="user" if is_user else "char"))
    # --- a plan or appointment ---
    elif TIMECUE.search(plain) and MEETCUE.search(plain) and not HEDGE.search(plain) and len(plain.split()) >= 5:
        out.append(_cand("plan", f"{spk} arranged: “{clip(plain, 130)}”", spk, plain, .72, open=True, when=_when(plain), about=[other] + names[:2], rsrc="user" if is_user else "char"))
    # --- a gift or a thing changing hands (the character's own actions count) ---
    gm = GIVE.search(plain) or (GIVE_SP.search(plain) if mode == "speech" else None)
    if gm and not plain.lower().startswith(("don't", "do not", "never")):
        gd = gm.groupdict()
        rcp_raw = (gd.get("r") or "").strip()
        rcp = {"you": other, "me": spk, "us": f"{spk} and {other}", "her": "", "him": "", "them": ""}.get(rcp_raw.lower(), _ph(en.canon(c.mem, rcp_raw), c.user, c.char) if rcp_raw else "")
        if not rcp:
            rcp = other if rcp_raw.lower() in ("her", "him", "them", "") and not c.group else ""
        np_ = re.sub(r"\s+", " ", gd["np"]).strip(" ,")
        np_ = re.split(r"\s+(?:and then|then|before|while|as|but|because)\s+", np_)[0]
        np_ = re.sub(r"\b(?:to|for) (you|me)\b", lambda x: other if x.group(1).lower() == "you" else spk, np_)
        if not rcp:
            tm = re.search(r"\b(?:to|for)\s+(you|me|[A-Z][a-z]{2,})\b", plain)
            if tm:
                rcp = {"you": other, "me": spk}.get(tm.group(1).lower(), _ph(en.canon(c.mem, tm.group(1)), c.user, c.char))
        verb = gd.get("v", "gave").lower().split()[0]
        out.append(_cand("gift", f"{spk} {_past_give(verb)} {rcp + ' ' if rcp else ''}{_third(np_, spk, other)}".strip() + (f" (they said: “{clip(plain, 90)}”)" if mode == "speech" else ""), spk, plain, .78,
                         about=[rcp] if rcp else [], obj=clip(np_, 60), rsrc="user" if is_user else "scene" if mode == "narr" else "char", status="uncertain" if hedged else "confirmed"))
    # --- decision / agreement ---
    if DECIDE.search(plain):
        out.append(_cand("decision", f"{spk} said (decision): “{clip(plain, 130)}”", spk, plain, .72, about=names[:2], rsrc="user" if is_user else "char"))
    # --- body: injury, sickness, death ---
    if BODY.search(plain):
        subj_txt = third if mode == "narr" else f"{spk} said: “{clip(plain, 120)}”"
        out.append(_cand("body", clip(subj_txt, 170), spk, plain, .85, about=names[:2], rsrc="scene" if mode == "narr" else "user" if is_user else "char", pin=False))
    # --- feelings ---
    fm = FEEL.search(plain)
    if fm and mode == "speech":
        grp, val = lx.emotion_group(fm.group(1))
        out.append(_cand("feeling", f"{spk} felt {fm.group(1).lower()}: “{clip(plain, 110)}”", spk, plain, .55 if abs(val) >= .6 else .4, emo=fm.group(1).lower(), layer="emotional",
                         rsrc="user" if is_user else "char"))
    # --- stable facts the speaker states about themself ---
    if mode == "speech" and FIRST_PERSON_START.match(plain) or (mode == "speech" and re.search(r"(?i)\bi(?:'m| am)\b|\bmy\b", plain)):
        for f, imp, subj in analyze.user_facts(plain):
            ftxt = f.replace(U, spk)
            out.append(_cand("fact", ftxt, spk, plain, imp, layer="semantic", subj="user" if spk == U else "self" if spk == C else "other", slot=_slot(ftxt, spk), rsrc="user" if is_user else "char",
                             status="uncertain" if hedged else "confirmed", pin=bool(analyze.IDENTITY.search(ftxt))))
    tm = re.search(r"(?i)\bi (?:just )?turned (\d{1,2})\b", plain)
    if tm and mode == "speech":
        out.append(_cand("fact", f"{spk} is {tm.group(1)} years old (said when they turned {tm.group(1)})", spk, plain, .62, layer="semantic", subj="user" if spk == U else "self" if spk == C else "other",
                         slot=f"{en._key(spk)}:age", rsrc="user" if is_user else "char"))
    # --- relationships ---
    for r in en.relations_in(plain, spk, c.user, c.char, other):
        if r["kind"] == "bond":
            out.append(_cand("relationship", f"{r['a']} is {r['b'] + chr(39) + 's' if r['b'] not in ('{{user}}', '{{char}}') else r['b'] + chr(39) + 's'} {r['rel']}" if r["rel"] not in ("married", "dating", "siblings", "brothers", "sisters", "friends", "enemies", "rivals", "partners", "lovers", "engaged", "twins", "cousins", "together", "a couple", "best friends")
                             else f"{r['a']} and {r['b']} are {r['rel']}", spk, plain, .66, layer="semantic", subj="bond", about=[r["a"], r["b"]], rel=r, slot=f"rel:{r['b']}:{r['rel']}",
                             rsrc="user" if is_user else "char", status="uncertain" if hedged else "confirmed"))
        elif r["kind"] == "end":
            out.append(_cand("relationship", f"{r['a']} and {r['b']} ended their relationship", spk, plain, .8, about=[r["a"], r["b"]], rel=r, rsrc="user" if is_user else "char"))
        else:
            out.append(_cand("event", f"{r['a']} {r['rel']} {r['b']}", spk, plain, .72, about=[r["a"], r["b"]], rel=r, rsrc="scene" if mode == "narr" else "char"))
    # --- a scene event (narration, or a strong action the speaker states) ---
    sc, verb = _event_score(plain)
    if mode == "narr" and sc < .5 and PLACE_MOVE.search(plain):
        sc = .55
    if sc >= .5 and mode == "narr" and not out:
        out.append(_cand("event", clip(third, 170), spk, plain, round(sc, 2), about=names[:3], rsrc="scene" if not is_user else "user"))
    # --- a statement about someone else ---
    named = [n for n in names if en._key(n) not in (en._key(c.user), en._key(c.char))]
    solid = any(o["kind"] in ("promise", "secret", "gift", "decision", "body", "claim", "plan") for o in out)
    if not solid and named and mode == "speech" and STATE.search(plain) and len(plain.split()) >= 3 and (not FIRST_PERSON_START.match(plain) or re.match(r"(?i)^my\s+\w+(?: \w+)?\s+[A-Z]", plain)):
        acc = bool(ACCUSE.search(plain))
        out.append(_cand("claim", f"{spk} said about {named[0]}: “{clip(plain, 130)}”", spk, plain, .55 if acc or not is_user else .6, about=named[:3],
                         status="uncertain" if (acc or hedged or not is_user) else "confirmed", rsrc="report" if acc or not is_user else "user"))
    elif not out and is_user and named and mode == "narr" and STATE.search(plain):
        out.append(_cand("event", clip(third, 160), spk, plain, .5, about=named[:3], rsrc="user"))
    if not out and mode == "speech" and not plain.endswith("?") and 4 <= len(plain.split()) <= 32 and not TRANSIENT.search(plain) and not re.match(r"(?i)^(?:thanks|thank you|please|sorry|okay|yes|no|well|oh|hmm|hey|hi|hello)\b", plain):
        sc = salience(plain, named, _skipnames(c))
        if sc >= 3.0:
            subj = "user" if spk == U else "self" if spk == C else "other"
            out.append(_cand("fact", f"{spk} said: “{clip(plain, 140)}”", spk, plain, round(min(.72, .42 + .04 * (sc - 3)), 2), layer="semantic", subj=subj, about=named[:3],
                             rsrc="user" if is_user else "char", status="uncertain" if hedged else "confirmed"))
    if not out and mode == "narr" and not plain.endswith("?") and 4 <= len(plain.split()) <= 32:
        sc = salience(plain, named, _skipnames(c))
        if sc >= 3.0:
            out.append(_cand("event", clip(third, 170), spk, plain, round(min(.7, .45 + .04 * (sc - 3)), 2), about=named[:3], rsrc="scene" if not is_user else "user"))
    if explicit and not any(o["kind"] in ("fact", "promise", "secret", "decision") for o in out):
        body = re.sub(r"(?i)^.*?\bremember(?: that| this)?[:,]?\s*", "", plain)
        if len(body.split()) >= 3:
            out.append(_cand("fact", f"{spk} asked to remember: {clip(_third(body, spk, other), 140)}", spk, plain, .93, layer="semantic", subj="user" if is_user else "self", pin=True, rsrc="user"))
    for o in out:
        if hedged and o["status"] == "confirmed" and o["kind"] in ("event", "claim", "plan", "gift"):
            o["status"] = "uncertain"
        if nxt and CONT.match(nxt.strip()) and o["kind"] in ("gift", "event", "plan", "promise", "decision", "body") and len(nxt.split()) <= 24:
            o["evid"] = clip(plain + " " + nxt.strip(), 200)         # "She presses a key into your palm. It opens the cellar door."
            if o["kind"] in ("gift", "event"):
                o["text"] = o["text"].rstrip(".") + f" ({clip(nxt.strip(), 70)})"
    return out


SPECIFIC_VERB = re.compile(r"(?i)\b(?:keep|keeps|kept|hide|hides|hid|hidden|stash\w*|taught|teach\w*|learn(?:ed|t)|fail(?:ed|s)?|pass(?:ed)?|owe[sd]?|own[sd]?|bought|sold|lost|found|born|moved|married|divorced|met|"
                           r"sav(?:ed|ing)|dream(?:ed|t|s)?|afraid|scared|hate[sd]?|love[sd]?|work(?:s|ed)?|stud(?:y|ied|ies)|liv(?:e|es|ed)|burn(?:ed|t|s)|destroy\w*|broke|broken|stole|stolen|steal\w*|scar\w*|"
                           r"reveal\w*|unroll\w*|mark(?:s|ed)?|bury|buried|carv\w*|wrote|writes|sign(?:s|ed)|inherit\w*|adopt\w*|visited|grew|raised|named|train(?:ed|s)?|cheat\w*|betray\w*|lied|forgot|wants?|plans?|planning|hopes?|wish(?:es)?|never|always)\b")
NUMWORD = re.compile(r"(?i)\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|fifty|hundred|thousand|million|twice|once|first|second|third|dozen)\b")
TRANSIENT = re.compile(r"(?i)\b(?:today|right now|later|tonight|this morning|this afternoon|at the moment|just now)\b|"
                       r"\bi(?:'m| am| feel)\s+(?:a bit |so |very |really )?(?:tired|hungry|bored|sleepy|cold|hot|fine|okay|ok|good|well|here|back)\b")
_NOTCONTENT = set("about after again against because before being could every going great little never other should something still their there these thing things those through under until where which while would".split())


def salience(sent, names=(), skip=()):
    """How specific and lasting is this sentence? Numbers, names, concrete nouns, and verbs about keeping, losing, owing, learning, being from somewhere.
    Chatter ('I had a sandwich', 'the bus was late') scores low and is not stored."""
    t = re.sub(r"\s+", " ", sent)
    sc = 0.0
    skip_ = {x.lower() for x in skip if x}
    props = {m.group(0) for m in re.finditer(r"(?<=[a-z,] )[A-Z][a-z]{2,}\b", t) if m.group(0).lower() not in en.COMMON and m.group(0).lower() not in skip_}
    first = re.match(r"^\W*([A-Z][a-z]{2,})\s+[a-z]+", t)
    if first and first.group(1).lower() not in en.COMMON and first.group(1) not in ("She", "He", "They") and first.group(1).lower() not in skip_:
        props.add(first.group(1))
    named_ = len({p_ for p_ in props | set(names) if p_.lower() not in skip_})
    verb = bool(SPECIFIC_VERB.search(t))
    poss = bool(re.search(r"(?i)\b(?:my|our|his|her|their)\s+[a-z]{3,}", t))
    dated = bool(re.search(r"(?i)\b(?:exam|test|deadline|appointment|interview|flight|wedding|birthday|funeral|trial|ceremony|festival|concert|race)\b.{0,30}\b(?:is|are|will be|starts?)\b", t))
    sc += 1.5 * min(2, named_) + (2 if verb else 0) + (1 if poss else 0) + (2 if dated else 0)
    if NUMWORD.search(t) and (named_ or verb or poss or dated):
        sc += 2                  # a number boosts a sentence that is already about something; "message number 3" alone is nothing
    sc += .5 * min(4, len([w for w in re.findall(r"[a-zA-Z]{5,}", t) if w.lower() not in _NOTCONTENT and w.lower() not in en.COMMON]))
    return sc


def _skipnames(c):
    out = set()
    for n in [c.user, c.char] + list(c.group):
        if n:
            out |= {n, n.split(" ")[0]}
    return out


def _past_give(v):
    v = v.lower()
    base = {"gives": "gave", "give": "gave", "hands": "handed", "hand": "handed", "offers": "offered", "offer": "offered", "presents": "presented", "present": "presented", "passes": "passed",
            "slides": "slid", "tosses": "tossed", "buys": "bought", "buy": "bought", "lends": "lent", "lend": "lent", "returns": "returned", "brings": "brought", "bring": "brought",
            "hangs": "hung", "fastens": "fastened", "clasps": "clasped", "places": "placed", "presses": "pressed", "slips": "slipped", "sends": "sent"}
    return base.get(v, v if v.endswith("ed") or v in ("gave", "bought", "lent", "brought", "hung", "sent", "slid", "made", "baked", "knitted", "carved", "wrapped", "handed") else v + "ed")


_SLOTS = ((r"wants to be called|'s name is|name is", "name"), (r"birthday", "birthday"), (r"years old", "age"), (r" is from ", "from"), (r" lives ", "lives"), (r" works ", "works"),
          (r"allergic|afraid of", "fear"))


def _slot(text, who):
    for rx, name in _SLOTS:
        if re.search(rx, text):
            return f"{en._key(who)}:{name}"
    m = re.search(r"'s (brother|sister|mom|mum|mother|dad|father|dog|cat|boss|best friend|friend|wife|husband|girlfriend|boyfriend|son|daughter|roommate|ex) is called", text)
    if m:
        return f"{en._key(who)}:rel:{m.group(1)}"
    return ""
