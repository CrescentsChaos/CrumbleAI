"""The conversation director: replies that vary the way a person's do.

A model left alone answers every message the same way: a medium-length reply, the same warm tone, an action, a line, a question.
The director decides, before each reply and without any model call, what is different about THIS one, from who the character is,
how they feel, what the user just did and what the last replies looked like:

    plan(...)            length band, emotional tone, and (now and then) one human quirk: interrupt, misunderstand, joke, lie or change topic.
                         Quirks follow the personality dials, never fire in a serious or tender moment, and have cooldowns.
    patterns(own)        what the last replies had in common (same opening, same shape, same ending, same length): a note to break it
    pattern_issue(t,own) the same check on a finished reply: an opening already used lately is a real repetition
    follow_up(hist, c)   what the character must remember about earlier quirks: a lie it told stays a lie it knows it told, a misreading
                         gets noticed
    initiate(...)        the character speaks first: after the user has been away, or when the chat goes quiet, with something of its own to say

Everything is deterministic for a given (chat, turn, variant), so a retry keeps the same plan and the tests can pin it down.
Pure functions on plain dicts.
"""
import hashlib
import random
import re

from .config import CH, US
from .personality import profile_for, stimulus
from .textutil import THINK, human_gap

LEVELS = {0: 0.0, 1: .12, 2: .24, 3: .38}        # chance that a reply carries a quirk at all
LEN_WORDS = {            # (story mode, text mode) word bands
    "tiny": ((3, 14), (1, 8)), "short": ((12, 38), (3, 18)), "medium": ((38, 95), (10, 38)), "long": ((95, 190), (28, 75))}
LEN_ORDER = ["tiny", "short", "medium", "long"]

TONES = {
    "warm": "warm and open", "playful": "light and playful", "teasing": "teasing, a little cheeky", "deadpan": "dry and deadpan",
    "tender": "soft and tender", "irritated": "short-tempered, a bit irritated", "curious": "curious and interested", "wry": "wry, amused at the situation",
    "excited": "excited, quick, a little breathless", "guarded": "guarded and careful", "melancholic": "quiet and a little sad",
    "flustered": "flustered and self-conscious", "blunt": "blunt and matter-of-fact", "mellow": "relaxed and unhurried",
}
MOOD_TONES = {   # mood word -> tones it favours
    "happy": ["warm", "playful", "excited"], "excited": ["excited", "playful"], "playful": ["playful", "teasing"], "amused": ["wry", "teasing", "playful"],
    "angry": ["irritated", "blunt"], "annoyed": ["irritated", "deadpan", "blunt"], "sad": ["melancholic", "tender", "guarded"], "hurt": ["guarded", "melancholic"],
    "anxious": ["guarded", "flustered"], "nervous": ["flustered", "guarded"], "embarrassed": ["flustered"], "shy": ["flustered", "guarded", "tender"],
    "affectionate": ["tender", "warm"], "loving": ["tender", "warm"], "calm": ["mellow", "warm"], "content": ["mellow", "warm"], "bored": ["deadpan", "wry", "mellow"],
    "curious": ["curious"], "neutral": ["mellow", "curious", "wry", "warm", "deadpan"], "tired": ["mellow", "deadpan", "melancholic"], "suspicious": ["guarded", "blunt"],
    "jealous": ["guarded", "irritated"], "proud": ["warm", "wry", "blunt"], "lonely": ["melancholic", "tender"],
}
STIM_TONES = {"hostile": ["irritated", "guarded", "blunt"], "kind": ["warm", "tender", "flustered"], "praise": ["flustered", "warm", "wry"],
              "vulnerable": ["tender", "warm"], "challenge": ["blunt", "teasing", "irritated"], "apology": ["mellow", "tender", "guarded"],
              "flirt": ["teasing", "flustered", "playful"], "dismissive": ["irritated", "deadpan", "guarded"]}

SERIOUS = re.compile(r"(?i)\b(?:funeral|died|dying|dead|death|suicid\w*|kill(?:ed|ing)?|blood|bleeding|emergency|ambulance|hospital|panic\w*|help me|"
                     r"i'?m scared|so scared|terrified|abuse[dr]?|assault\w*|cancer|miscarriage|overdose|crying|sobbing|heartbroken|grief|grieving)\b")
QUESTION = re.compile(r"\?\s*(?:[*_\"')\]]*)\s*$|^\W*(?:what|who|why|how|when|where|which|do you|did you|are you|can you|could you|would you|will you|is it|have you)\b", re.I)
SHORT_LOW = re.compile(r"(?i)^\W*(?:ok(?:ay)?|k|lol|lmao|haha+|yeah|yep|yes|no|nope|nah|sure|cool|nice|fine|hm+|mhm|idk|true|right|same|i see|oh|ah)\W*$")

QUIRK_COOLDOWN = {"interrupt": 4, "misunderstand": 7, "joke": 3, "lie": 10, "topic": 5}
ANY_COOLDOWN = 2          # no quirk twice within the last 2 replies of this character


def settings(p):
    p = p or {}
    try:
        lv = int(p.get("level", 2))
    except Exception:
        lv = 2
    try:
        greet = float(p.get("greet", 6))
    except Exception:
        greet = 6.0
    return {"on": bool(p.get("on", True)) and lv > 0, "level": max(0, min(3, lv)), "greet": max(0.0, min(720.0, greet))}


def rng_for(*parts):
    h = hashlib.sha256("|".join(str(x) for x in parts).encode("utf-8", "ignore")).hexdigest()
    return random.Random(int(h[:12], 16))


# ---------- reading text ----------

def _body(t):
    t = THINK.sub("", str(t or ""))
    return re.sub(r"\s+", " ", t).strip()


def _speech(t):
    return re.sub(r"\s+", " ", re.sub(r"\*[^*\n]*\*", " ", _body(t))).strip()


def _words(t):
    return re.findall(r"[\w']+", _speech(t).lower())


def len_class(text, mode="story"):
    n = len(re.findall(r"[\w']+", _body(text).replace("*", " ")))
    band = 1 if mode == "text" else 0
    for k in reversed(LEN_ORDER):
        if n >= LEN_WORDS[k][band][0]:
            return k
    return "tiny"


def shape(text):
    """A reply as a string of segments: A = action in asterisks, S = speech. '*nods.* "Fine." *leaves.*' -> 'ASA'."""
    out = []
    for m in re.finditer(r"\*[^*\n]+\*|[^*]+", _body(text)):
        seg = m.group(0)
        k = "A" if seg.startswith("*") else ("S" if re.search(r"\w", seg) else "")
        if k and (not out or out[-1] != k):
            out.append(k)
    return "".join(out)


def _all_words(t):
    return re.findall(r"[\w']+", _body(t).replace("*", " ").lower())


def opening(text, n=3):
    """The first words of a reply, actions included: '*Mira nods slowly.* ...' opens with 'mira nods slowly'."""
    return " ".join(_all_words(text)[:n])


def ends_with_question(text):
    t = re.sub(r"[*_\"”’')\]\s]+$", "", _speech(text) or _body(text))
    return t.endswith("?")


def read_user(text):
    """What the user's last message is, in the few ways that matter here."""
    t = _body(text)
    s = stimulus.tone(t)
    tags = [k for k in ("hostile", "kind", "praise", "vulnerable", "challenge", "apology", "flirt", "dismissive") if s.get(k, 0) >= .5]
    n = len(_words(t))
    return {"words": n, "tags": tags, "help": bool(re.search(r"(?i)\b(?:help|advice|what should i|should i|is it safe|how do i|need your)\b", t)), "serious": bool(SERIOUS.search(t)) or s.get("vulnerable", 0) >= .8, "question": bool(QUESTION.search(t)),
            "low": bool(SHORT_LOW.match(t)) or n <= 2, "tone": s}


# ---------- the plan ----------

def _dials(c):
    try:
        return profile_for(c)["traits"]
    except Exception:
        return {}


def _recent_dyn(hist, cid, k=12):
    """The `dyn` marks saved on this character's earlier replies (newest last): [{tone, quirk, len, init}]."""
    own = [m for m in hist if m.get("role") == "assistant" and (not cid or not m.get("cid") or m.get("cid") == cid)]
    return [m.get("dyn") if isinstance(m.get("dyn"), dict) else {} for m in own[-k:]]


def pick_length(rng, u, dials, mode, recent_classes, setting):
    """A length class for this reply: from what the user wrote, the character's talkativeness, and not the same thing three times running."""
    w = {"tiny": 1.0, "short": 3.0, "medium": 3.0, "long": 1.0}
    if u["low"]:
        w.update(tiny=4.0, short=3.5, medium=1.0, long=.1)
    elif u["words"] <= 6:
        w.update(tiny=2.0, short=4.0, medium=2.0, long=.3)
    elif u["words"] >= 40:
        w.update(tiny=.4, short=2.0, medium=4.0, long=2.5)
    elif u["words"] >= 18:
        w.update(tiny=.6, short=2.5, medium=4.0, long=1.2)
    if u["question"] and not u["low"]:
        w["tiny"] *= .6
        w["short"] *= 1.2
        w["medium"] *= 1.3
    if "vulnerable" in u["tags"] or u["serious"]:
        w.update(tiny=.3, short=1.5, medium=4.0, long=2.5)
    if "hostile" in u["tags"] or "dismissive" in u["tags"]:
        w["tiny"] *= 1.8
        w["long"] *= .4
    talk = (dials.get("verbosity", 50) + dials.get("extraversion", 50)) / 2 / 50     # .0 (very quiet) .. 2.0 (very chatty)
    w["tiny"] *= max(.3, 1.6 - .6 * talk)
    w["short"] *= max(.4, 1.3 - .3 * talk)
    w["long"] *= max(.2, .4 + .7 * talk)
    last = recent_classes[-2:]
    if len(last) == 2 and last[0] == last[1]:
        w[last[1]] *= .12                                   # twice the same already: not again
    elif last:
        w[last[-1]] *= .55
    if setting != "auto":
        return None
    keys = list(w)
    return rng.choices(keys, weights=[w[k] for k in keys])[0]


def pick_tone(rng, mood, tags, dials, recent_tones):
    w = {t: .35 for t in TONES}
    for i, t in enumerate(MOOD_TONES.get(re.sub(r"[^a-z]", "", str(mood or "neutral").lower()), MOOD_TONES["neutral"])):
        w[t] += 3.0 - .6 * i
    for tag in tags:
        for i, t in enumerate(STIM_TONES.get(tag, [])):
            w[t] += 2.6 - .5 * i
    if dials.get("humor", 50) >= 65:
        for t in ("wry", "teasing", "playful", "deadpan"):
            w[t] += .8
    if dials.get("warmth", 50) >= 65:
        for t in ("warm", "tender"):
            w[t] += .8
    if dials.get("warmth", 50) <= 30:
        for t in ("blunt", "deadpan", "guarded"):
            w[t] += .8
    if dials.get("neuroticism", 50) >= 70:
        for t in ("flustered", "guarded", "irritated"):
            w[t] += .6
    for t in recent_tones[-2:]:
        if t in w:
            w[t] *= .15                                     # not the same colour again straight away
    keys = list(w)
    return rng.choices(keys, weights=[w[k] for k in keys])[0]


def _cool(recent, quirk):
    gap = QUIRK_COOLDOWN.get(quirk, 4)
    for back, d in enumerate(reversed(recent)):
        if back < gap and d.get("quirk") == quirk:
            return False
    return True


def pick_quirk(rng, level, u, dials, c, st, recent, mode, group, hist_users):
    """-> (quirk or None, why). Each candidate has a weight from the personality and a gate from the moment."""
    if LEVELS.get(level, 0) <= 0 or u["serious"] or "vulnerable" in u["tags"]:
        return None, ""
    if any(d.get("quirk") for d in recent[-ANY_COOLDOWN:]):
        return None, ""
    imp, ext, ass, hum = (dials.get(k, 50) / 100 for k in ("impulsivity", "extraversion", "assertiveness", "humor"))
    agr, con, neu, pride, trust = (dials.get(k, 50) / 100 for k in ("agreeableness", "conscientiousness", "neuroticism", "pride", "trust"))
    aff = int(st.get("affection", 50)) if isinstance(st, dict) and "affection" in st else 50
    hostile = "hostile" in u["tags"]
    cand = {}
    if not hostile:
        cand["joke"] = .5 + 2.2 * hum
    cand["topic"] = .25 + 1.2 * imp + .8 * ext + (1.0 if u["low"] else 0) + (.5 if len(hist_users) >= 3 and all(x <= 4 for x in hist_users[-3:]) else 0)
    if u["question"] and not u["low"]:
        cand["topic"] *= .25                                # a real question gets answered first
    if u["words"] >= 25 or group:
        cand["interrupt"] = .2 + 1.4 * imp + .8 * ass
    if level >= 2 and u["words"] >= 6 and not hostile and not u["question"]:
        cand["misunderstand"] = .15 + .9 * (1 - con) + .5 * neu
    secrets = str(c.get("secrets") or "").strip()
    motive = bool(secrets) or trust < .4 or pride > .65 or "dismissive" in u["tags"] or "challenge" in u["tags"]
    if level >= 2 and motive and u["words"] >= 4 and aff < 90 and not u["help"]:
        cand["lie"] = .4 * (.1 + .9 * (1 - trust) + .6 * pride + (.6 if secrets else 0) - .5 * agr)
    cand = {k: max(0.0, v) for k, v in cand.items() if _cool(recent, k) and v > 0}
    if mode == "call":
        cand.pop("misunderstand", None)
    if not cand:
        return None, ""
    # how likely any quirk is at all grows with how much this character and this moment invite one (a deadpan wit with a long message to cut into
    # is far likelier to do something than a quiet, careful one answering a one-liner)
    if rng.random() > LEVELS[level] * max(.35, min(1.6, .25 + .22 * sum(cand.values()))):
        return None, ""
    keys = list(cand)
    q = rng.choices(keys, weights=[cand[k] for k in keys])[0]
    why = ""
    if q == "lie":
        why = ("keeping something private" if secrets else "pride" if pride > .65 and pride >= 1 - trust else "not trusting them yet")
    return q, why


QUIRK_TEXT = {
    "interrupt": ("{CH} cannot wait for {US} to finish the thought: the reply starts by cutting in, breaking off with an em dash or a quick "
                  "\"wait, wait\", reacting to the first part of what {US} said before the end of it. Then {CH} carries on."),
    "interrupt_group": ("{CH} cuts across the last speaker, who was still in the middle of a point: the reply starts by breaking in (an em dash, "
                        "a quick \"hang on\") and then says what {CH} has been itching to say."),
    "misunderstand": ("{CH} misreads one thing {US} said: takes a word or the point the wrong way, a small plausible mix-up, and answers that "
                      "version with full confidence. It is only a harmless mix-up, nothing serious. Do not point it out; leave {US} room to correct it."),
    "joke": ("{CH} makes a joke here, in {CH}'s own kind of humour{hum}. One line, and it fits what was just said; no explaining it."),
    "lie": ("{CH} tells a small, believable lie in character (an excuse, a fib about what they were doing, feeling or know) because of {why}. "
            "It must be harmless to {US}: never a lie about danger, health or anything {US} would act on. Keep it consistent with what is already established, "
            "say it with a straight face, and never announce it as a lie."),
    "topic": ("{CH} drifts away from the current thread: answers what {US} said in a few words, then turns to something else on {CH}'s mind{seed}. "
              "It should feel like a real person's tangent, not a quiz or a question."),
}


def topic_seeds(c, st, hist, chron=None, rng=None, limit=3):
    """Things the character might bring up on their own: from the sheet, what they know, plans and promises, an unanswered question."""
    seeds = []
    last = next((m for m in reversed(hist) if m.get("role") == "assistant" and (m.get("content") or "").strip()), None)
    if last and ends_with_question(last["content"]) and (not hist or hist[-1].get("role") == "assistant"):
        seeds.append("the question " + CH + " asked that never got an answer")
    for e in (chron or {}).get("items", [])[::-1]:
        if e.get("k") in ("plan", "promise") and len(seeds) < 6:
            seeds.append("something planned or promised earlier: " + re.sub(r"\{\{(?:user|char)\}\}", lambda m: US if m.group(0) == "{{user}}" else CH, e["t"])[:110])
            break
    for key in ("likes", "goals", "hobbies", "interests", "quirks"):
        v = str(c.get(key) or "").strip()
        if v:
            bits = [b.strip() for b in re.split(r"[,;\n]+", v) if 2 < len(b.strip()) < 50]
            if bits:
                seeds.append(f"{CH}'s own interest ({(rng or random).choice(bits)})")
    for f in (st or {}).get("facts", [])[-6:][::-1][:2]:
        seeds.append(f"something {US} once said about themself: {str(f)[:90]}")
    seeds.append("something small and concrete in the scene around them")
    if rng:
        rng.shuffle(seeds)
    return seeds[:limit]


def plan(c, st, hist, *, mode="story", length="auto", level=2, turn=0, key="", variant=0, kind="reply", chron=None, group=False):
    """-> {band, len, tone, quirk, block, tail, dyn} for this reply. `hist` is the in-character chat so far (the last message is the user's)."""
    level = max(0, min(3, int(level)))
    if level == 0 or kind in ("continue",):
        return {"band": None, "len": None, "tone": None, "quirk": None, "block": "", "tail": "", "dyn": {}}
    cid = c.get("id")
    last_user = hist[-1] if hist and hist[-1].get("role") == "user" else None      # a nudge answers silence, not an old message
    u = read_user((last_user or {}).get("content", ""))
    dials = _dials(c)
    rng = rng_for(key, cid, turn, variant)
    recent = _recent_dyn(hist, cid)
    own_texts = [m["content"] for m in hist if m.get("role") == "assistant" and (not group or m.get("cid") == cid)][-6:]
    rcls = [len_class(t, mode) for t in own_texts]
    ln = pick_length(rng, u, dials, mode, rcls, length)
    tone = pick_tone(rng, (st or {}).get("mood"), u["tags"], dials, [d.get("tone") for d in recent if d.get("tone")])
    users = [len(_words(m.get("content"))) for m in hist if m.get("role") == "user"]
    quirk, why = (None, "") if kind not in ("reply", "nudge") else pick_quirk(rng, level, u, dials, c, st, recent, mode, group, users)
    seed = ""
    if quirk == "topic":
        s = topic_seeds(c, st, hist, chron, rng, 2)
        seed = " (for instance: " + "; ".join(s) + ")" if s else ""
    hum = str(c.get("humor") or "").strip()
    text = QUIRK_TEXT["interrupt_group" if quirk == "interrupt" and group else quirk] if quirk else ""
    text = text.replace("{hum}", f" ({hum[:70]})" if hum else "").replace("{why}", why or "pride").replace("{seed}", seed)
    band = None
    if ln:
        band = LEN_WORDS[ln][1 if mode == "text" else 0]
    pats = patterns(own_texts, mode)
    block_parts = [f"This reply's emotional tone: {TONES[tone]}. Let it show in the word choice and rhythm, not in a label."]
    if ln:
        block_parts.append({"tiny": "This reply is tiny: a few words, a reaction or a single line.", "short": "This reply is short and to the point.",
                            "medium": "This reply has some body to it: a few sentences.", "long": "This reply has room to breathe: let it run, as long as it stays interesting."}[ln])
    if text:
        block_parts.append(text)
    if pats["note"]:
        block_parts.append(pats["note"])
    fu = follow_up(hist, c, mode)
    if fu:
        block_parts.append(fu)
    tail = (text + " ") if text else ""
    return {"band": band, "len": ln, "tone": tone, "quirk": quirk, "block": "[Conversation dynamics]\n" + "\n".join(block_parts),
            "tail": tail.strip(), "dyn": {"tone": tone, "quirk": quirk, "len": ln}}


# ---------- not repeating itself ----------

def patterns(own, mode="story"):
    """What the last few replies had in common. -> {"note": str, "open": [...], "shape": str, "q": bool}"""
    own = [t for t in own if _body(t)][-4:]
    out = {"note": "", "open": [], "shape": "", "q": False}
    if len(own) < 2:
        return out
    notes = []
    shapes = [shape(t) for t in own[-3:]]
    if len(shapes) >= 2 and len(set(shapes[-2:])) == 1 and shapes[-1]:
        sh = shapes[-1]
        desc = {"A": "an action", "S": "plain speech", "AS": "an action then speech", "SA": "speech then an action", "ASA": "an action, speech, then an action"}.get(sh, "the same shape")
        notes.append(f"Your last replies were all built the same way ({desc}). Build this one differently: change what it starts with and how it is put together.")
        out["shape"] = sh
    firsts = [opening(t, 2) for t in own[-3:] if opening(t, 2)]
    if len(firsts) >= 2 and firsts[-1] == firsts[-2]:
        out["open"] = [firsts[-1]]
    if len(own) >= 2 and all(ends_with_question(t) for t in own[-2:]):
        notes.append("Your last two replies ended on a question. This one does not.")
        out["q"] = True
    classes = [len_class(t, mode) for t in own[-3:]]
    if len(classes) == 3 and len(set(classes)) == 1:
        notes.append(f"Your last three replies were about the same length ({classes[0]}); this one is clearly different.")
    emo = [bool(re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", t)) for t in own[-3:]]
    if len(emo) == 3 and all(emo):
        notes.append("You used an emoji in each of your last replies; skip them this time.")
    out["note"] = " ".join(notes)
    return out


def pattern_issue(text, own, mode="story"):
    """Is this finished reply the same pattern as the recent ones? -> "pattern_open" (an opening already used) or None.
    Only openings are a retry-worthy mistake; shape, ending and length are steered by the plan's notes."""
    own = [t for t in own if _body(t)][-3:]
    o = _all_words(text)[:4]
    if len(o) < 3:
        return None
    for t in own:
        w = _all_words(t)[:4]
        if len(w) >= 3 and w[:3] == o[:3] and len(set(o[:3])) > 1:
            return "pattern_open"
    return None


# ---------- remembering what it did ----------

def follow_up(hist, c, mode="story"):
    """Notes about the character's own earlier quirks: a lie it told is still a lie it knows it told, a misreading may be noticed."""
    cid, notes = c.get("id"), []
    own = [m for m in hist if m.get("role") == "assistant" and (not cid or not m.get("cid") or m.get("cid") == cid)]
    for m in own[-30:]:
        d = m.get("dyn") if isinstance(m.get("dyn"), dict) else {}
        if d.get("quirk") == "lie":
            gist = re.sub(r"\s+", " ", _speech(m.get("content")))[:130]
            notes.append(f"Earlier, {CH} told {US} a small lie (\"{gist}\"). It was not true and {CH} knows it. Keep it straight: do not contradict the story you told, and do not "
                         f"suddenly confess unless it comes out or {CH} would crack.")
            break
    if own and isinstance(own[-1].get("dyn"), dict) and own[-1]["dyn"].get("quirk") == "misunderstand":
        notes.append(f"Your last reply misread what {US} said. If {US} corrected you, own the mix-up in {CH}'s own way (embarrassed, laughing it off, deflecting); "
                     f"if not, {CH} may catch it on their own now.")
    return " ".join(notes)


def lie_messages(hist):
    """Indexes of the character's replies that are marked as lies, so memory never records them as true."""
    return [i for i, m in enumerate(hist) if isinstance(m.get("dyn"), dict) and m["dyn"].get("quirk") == "lie"]


# ---------- the character speaks first ----------

def initiate(reason, c, st, hist, *, gap_s=0, key="", turn=0, chron=None, mode="story", variant=0):
    """-> {tail, how, dyn}. reason: 'return' (the user has been away) or 'idle' (the chat went quiet)."""
    rng = rng_for(key, c.get("id"), turn, reason, variant)
    g = human_gap(gap_s) or "a while"
    prev = [m.get("dyn", {}).get("init") for m in hist if m.get("role") == "assistant" and isinstance(m.get("dyn"), dict)]
    seeds = topic_seeds(c, st, hist, chron, rng, 3)
    how_all = {
        "return": ["greets them the way they would after being apart: a reaction to the time that passed", "picks up what was left hanging",
                   "has something to tell them that happened while they were away", "carries on as if no time passed, with a small remark"],
        "idle": ["follows up on the last thing said", "has a new thought and shares it", "reacts to the silence in their own way", "changes the subject to something of their own"],
    }.get(reason, ["says something natural"])
    pool = [h for h in how_all if h not in prev[-2:]] or how_all
    how = rng.choice(pool)
    seed_txt = f" Something {CH} could bring up: {seeds[0]}." if seeds else ""
    if reason == "return":
        tail = (f"({US} has come back after {g}. {CH} speaks first and {how}. Make it specific to {CH}, to this story and to the time of day; "
                f"no generic \"how are you\" or \"how can I help\".{seed_txt} Write only {CH}'s message.)")
    else:
        tail = (f"({US} has not replied for {g}. {CH} {how}, the way this person would. A short message is fine. Do not scold {US} or ask whether they are still there.{seed_txt} "
                f"Write only {CH}'s message.)")
    return {"tail": tail, "how": how, "dyn": {"init": how, "reason": reason}}
