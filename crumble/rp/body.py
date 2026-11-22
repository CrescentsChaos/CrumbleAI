"""Bodies that remember. Wounds, sickness, tiredness and death persist across scenes and feel real in the writing.

    rp["body"][id] = {"inj": [{k, p, s, h, care}], "ill": [{k, s, h, care}], "tired": 0-100, "dead": False,
                      "died": {"how", "turn"} | None, "stash": {...} | None, "rev": 0, "n": 0}

    k kind, p body part, s severity 1 (nagging) .. 4 (critical), h story-hours since it happened, care = someone treated it.

Nothing heals by magic or by pressing a button: wounds and illness age with the story's own time (every exchange is a few minutes; "three
days later" or a night's sleep is more), heal faster when treated and rested, and the serious ones need real care. A body at the edge bleeds out.
DEATH is real: a dead character does not speak, act or think, their mood and bond are set aside (kept only so a resurrection can bring
them back), and only a revive action (or the author) undoes it.

Pure functions on plain dicts. No randomness anywhere.
"""
import copy
import re

PARTS = ("left arm", "right arm", "left leg", "right leg", "ribs", "shoulder", "side", "head", "hand", "knee", "back", "thigh")
SEV_TXT = {1: "minor", 2: "painful", 3: "serious", 4: "critical"}
STEP_H = {1: 24, 2: 96, 3: 300, 4: 700}       # story-hours for a wound to ease by one level, untreated (halved when treated)
ILL_STEP_H = {1: 60, 2: 150, 3: 330, 4: 700}
PER_EXCHANGE_H = .12                           # one message is a few minutes of story
BLEED_H = .9                                   # a critical bleed with no care ends a life in under an hour of story time
FRESH_H = .6                                   # a wound this recent is "fresh": raw pain, shock

KIND_BY_WEAPON = {"blade": "gash", "heavy": "crushing blow", "unarmed": "bruising", "gun": "gunshot wound", "bow": "arrow wound",
                  "fire": "burn", "ice": "frostbite", "lightning": "electrical burn", "poison": "poisoning", "arcane": "magical wound",
                  "magic": "magical wound", "throw": "puncture", "claws": "slash", "": "wound"}
BREAKS = {"crushing blow": "fracture", "bruising": "bruise"}


def blank():
    return {"inj": [], "ill": [], "tired": 0, "dead": False, "died": None, "stash": None, "rev": 0, "n": 0, "ko": False}


def get(rp, cid):
    b = rp.setdefault("body", {}).setdefault(str(cid), blank())
    for k, v in blank().items():
        b.setdefault(k, v)
    return b


def peek(rp, cid):
    return ((rp or {}).get("body") or {}).get(str(cid)) or blank()


def is_dead(rp, cid):
    return bool(peek(rp, cid).get("dead"))


def dead_ids(rp):
    return [k for k, v in ((rp or {}).get("body") or {}).items() if isinstance(v, dict) and v.get("dead")]


# ---------------------------------------------------------------- wounds and illness
def add_injury(b, kind, part=None, sev=2, care=False):
    """Add a wound; a second wound on the same spot makes the first one worse instead of piling up."""
    sev = max(1, min(4, int(sev)))
    if not part:
        part = PARTS[b["n"] % len(PARTS)]
    b["n"] += 1
    for i in b["inj"]:
        if i["p"] == part:
            i["s"] = min(4, max(i["s"], sev) + (1 if i["s"] >= 2 and sev >= 2 else 0))
            i["k"], i["h"], i["care"] = kind, 0.0, False
            return i
    inj = {"k": kind, "p": part, "s": sev, "h": 0.0, "care": bool(care)}
    b["inj"].append(inj)
    if len(b["inj"]) > 7:
        b["inj"].sort(key=lambda x: -x["s"])
        del b["inj"][7:]
    return inj


def add_illness(b, name, sev=2):
    sev = max(1, min(4, int(sev)))
    for i in b["ill"]:
        if i["k"] == name:
            i["s"] = max(i["s"], sev)
            return i
    ill = {"k": name, "s": sev, "h": 0.0, "care": False}
    b["ill"].append(ill)
    return ill


def burden(b):
    """How much of the body's strength is lost to wounds and sickness (0..0.9)."""
    return max(0.0, min(.9, .09 * sum(i["s"] for i in b["inj"]) + .06 * sum(i["s"] for i in b["ill"]) + .002 * b.get("tired", 0)))


def vitality(b):
    return 1.0 - burden(b)


def penalty(b):
    """What the body can no longer do well: attack, guard, speed, and 'all' for head wounds, fever and exhaustion."""
    p = {"atk": 0, "guard": 0, "speed": 0, "all": 0}
    for i in b["inj"]:
        s, part = i["s"], i["p"]
        if "arm" in part or "hand" in part or "shoulder" in part:
            p["atk"] += s
        elif "leg" in part or "knee" in part or "thigh" in part:
            p["speed"] += s
            p["guard"] += max(0, s - 1)
        elif part == "head":
            p["all"] += s
        else:
            p["atk"] += s // 2
            p["speed"] += s // 2
    for i in b["ill"]:
        p["all"] += i["s"]
    p["all"] += b.get("tired", 0) // 30
    return {k: min(8, v) for k, v in p.items()}


def helpless(b):
    """Unconscious or bleeding out: cannot defend themselves."""
    return bool(b.get("ko")) or bleeding(b) is not None


def bleeding(b):
    return next((i for i in b["inj"] if i["k"] == "bleeding" and i["s"] >= 4 and not i.get("care")), None)


def tick(b, hours, rested=False, name="They"):
    """Let story time pass. Returns events: {"ev": healed|eased|worse|collapse|died, ...}."""
    ev = []
    if b.get("dead"):
        return ev
    mult = 1.5 if rested else 1.0
    if b.get("ko") and not bleeding(b):
        b["ko"] = False
    for i in list(b["inj"]):
        i["h"] = round(i.get("h", 0) + hours, 3)
        if i["k"] == "bleeding" and i["s"] >= 4 and not i.get("care") and i["h"] >= BLEED_H:
            ev.append({"ev": "died", "how": "bled out from their wounds"})
            return ev
        need = STEP_H[i["s"]] / (2 if i.get("care") else 1) / mult
        if i["s"] >= 4 and not i.get("care") and i["k"] != "bleeding":
            continue      # a critical wound does not ease by itself: it needs treatment
        while i["h"] >= need and i["s"] > 0:
            i["s"] -= 1
            i["h"] -= need
            if i["s"] == 0:
                ev.append({"ev": "healed", "k": i["k"], "p": i["p"]})
                break
            ev.append({"ev": "eased", "k": i["k"], "p": i["p"], "s": i["s"]})
            need = STEP_H[i["s"]] / (2 if i.get("care") else 1) / mult
    b["inj"] = [i for i in b["inj"] if i["s"] > 0]
    for i in list(b["ill"]):
        i["h"] = round(i.get("h", 0) + hours, 3)
        need = ILL_STEP_H[i["s"]] / (2 if i.get("care") else 1) / mult
        if i["s"] >= 3 and not i.get("care") and i["h"] >= need * 1.6:
            i["s"] = min(4, i["s"] + 1)
            i["h"] = 0.0
            ev.append({"ev": "worse", "k": i["k"]})
            if i["s"] == 4 and i.get("late"):
                ev.append({"ev": "died", "how": f"succumbed to {i['k']}"})
                return ev
            i["late"] = i["s"] == 4
        elif i["h"] >= need and (i.get("care") or i["s"] <= 2):
            i["s"] -= 1
            i["h"] = 0.0
            ev.append({"ev": "healed" if i["s"] == 0 else "eased", "k": i["k"], "ill": 1})
    b["ill"] = [i for i in b["ill"] if i["s"] > 0]
    b["tired"] = max(0, int(b.get("tired", 0) - (hours * (9 if rested else 3))))
    return ev


def treat(b, power=1):
    """Someone tends the body: bleeding stops, serious wounds are set and dressed, a fever is nursed. Returns what was done."""
    done = []
    b["ko"] = False
    bl = bleeding(b)
    if bl:
        bl["care"], bl["s"], bl["k"] = True, 3, "stabilised wound"
        done.append("stopped the bleeding")
    for i in b["inj"]:
        if not i.get("care") and i["s"] >= 2:
            i["care"] = True
            done.append(f"dressed the {i['k']} on the {i['p']}")
            if power < 3:
                break
    for i in b["ill"]:
        if not i.get("care") and i["s"] >= 2:
            i["care"] = True
            done.append(f"nursed the {i['k']}")
            break
    if power >= 4:
        for i in b["inj"]:
            i["s"] = max(1, i["s"] - 1)
        for i in b["ill"]:
            i["s"] = max(1, i["s"] - 1)
    return done


def down(b, lethal=False):
    """Someone is brought to zero. Lethal intent (or a savage overkill) kills; otherwise they go down bleeding and need help within the hour."""
    if lethal:
        b["dead"], b["died"] = True, {"how": "was killed", "turn": 0}
        return "dead"
    inj = add_injury(b, "bleeding", "side" if b["n"] % 2 else "ribs", 4)
    inj["care"] = False
    b["ko"] = True
    return "down"


# ---------------------------------------------------------------- death and return
def kill(rp, cid, how="was killed", turn=0, aff=None, mood=None):
    """Mark dead. The bond and mood are set aside (not deleted): only a resurrection can give them back."""
    b = get(rp, cid)
    if b["dead"] and b.get("stash"):
        return b
    st = {"aff": aff, "mood": mood}
    for k in ("rom", "rel", "intim"):
        if (rp.get(k) or {}).get(cid) is not None:
            st[k] = copy.deepcopy(rp[k].pop(cid))
    b.update(dead=True, died={"how": how, "turn": turn}, stash=st)
    b["inj"], b["ill"] = [i for i in b["inj"] if i["k"] != "bleeding"], []
    return b


def revive(rp, cid, frail=3, full=False):
    """Bring someone back: bond and mood return exactly as they were, but the body is a fresh wreck unless the power is great."""
    b = get(rp, cid)
    if not b["dead"]:
        return None
    st = b.get("stash") or {}
    for k in ("rom", "rel", "intim"):
        if st.get(k) is not None:
            rp.setdefault(k, {})[cid] = st[k]
    b.update(dead=False, died=None, stash=None, rev=b.get("rev", 0) + 1, tired=70 if not full else 25)
    b["inj"], b["ill"] = [], []
    if not full:
        add_injury(b, "deathly weakness", "ribs", max(1, min(4, frail))).update(care=True)
    return {"aff": st.get("aff"), "mood": st.get("mood")}


# ---------------------------------------------------------------- words for the model and the page
def cond_word(b):
    if b.get("dead"):
        return "dead"
    s = sum(i["s"] for i in b["inj"]) + sum(i["s"] for i in b["ill"])
    top = max([i["s"] for i in b["inj"]] + [i["s"] for i in b["ill"]] + [0])
    return "critical" if top >= 4 else "badly hurt" if top == 3 or s >= 6 else "hurt" if top == 2 or s >= 3 else "bruised" if s else ("worn out" if b.get("tired", 0) >= 60 else "healthy")


def _inj_text(i, you):
    my = "the"
    s, k, p = i["s"], i["k"], i["p"]
    fresh = i.get("h", 0) < FRESH_H
    if s == 1:
        base = f"a minor {k} on {my} {p}: a nagging ache they mostly push through" + ("" if not fresh else ", still stinging")
    elif s == 2:
        base = f"a painful {k} on {my} {p}: it hurts to use, they favour it, wince when it is touched or jolted"
    elif s == 3:
        base = f"a serious {k} on {my} {p}: sharp, constant pain; it will not take weight or strength properly; they need rest and help" + ("; it is still bleeding" if i["k"] in ("gash", "gunshot wound", "arrow wound", "puncture", "slash", "wound") and fresh and not i.get("care") else "")
    else:
        base = f"a critical {k} on {my} {p}: agony, dizziness, grey skin and cold sweat; they can barely stay upright, their words come faint and broken, they may black out"
    if i.get("care") and s < 4:
        base += " (bandaged and tended)"
    return base


def _ill_text(i):
    s, k = i["s"], i["k"]
    return {1: f"a mild {k}: sniffling or queasy, tired, a little off", 2: f"a real {k}: fever chills, aching, a rasp in the voice, short temper, low energy",
            3: f"a bad {k}: hot and shaking, weak, dizzy, coughing or sick, they want to lie down and cannot concentrate",
            4: f"a dangerous {k}: delirious or barely conscious, burning up, fighting for breath; they need a healer now"}[s]


def describe(b, you=False):
    """Plain sentences for the prompt, strongest first. Empty when the body is fine."""
    L = [_inj_text(i, you) for i in sorted(b["inj"], key=lambda x: -x["s"])] + [_ill_text(i) for i in sorted(b["ill"], key=lambda x: -x["s"])]
    if b.get("tired", 0) >= 50:
        L.append("bone-tired: slow reactions, heavy limbs, short patience")
    return L


def guidance(b, name, user, you=False, speaker=True):
    """The [Body] block: how this body must be written. Pain changes speech, movement, mood, what they will agree to do."""
    L = describe(b, you)
    if not L:
        return ""
    who = user if you else name
    s = f"[Body: {who}]\n{who} is hurt or unwell: " + "; ".join(L[:4]) + "."
    if speaker and not you:
        s += (f"\nMake it felt, not announced: pain shows in breath, pauses, clipped or shaky speech, a flinch, a limp, a hand pressed to the wound, sweat, "
              f"sitting down heavily, losing the thread of a sentence. {name} does NOT shrug it off and does NOT act at full strength: they refuse or struggle with anything "
              f"the injury forbids, may snap or go quiet from pain, and want rest, water, a bandage or a healer. Never heal them by narration; it takes time and care.")
    elif you:
        s += f"\n{name} notices: they react with concern or awareness in their own way (offering help, going gentle, staring at the wound), and treat {who} as someone hurt."
    return s


def cond_phrase(b):
    L = describe(b)
    return "; ".join(L[:2]) if L else "unhurt"


def summary(b):
    return {"word": cond_word(b), "dead": bool(b.get("dead")), "inj": [dict(i) for i in b["inj"]], "ill": [dict(i) for i in b["ill"]], "tired": b.get("tired", 0)}


# ---------------------------------------------------------------- story time and narrated events
_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "few": 3, "several": 4, "couple": 2}
_UNIT = {"minute": 1 / 60, "hour": 1, "day": 24, "night": 8, "week": 168, "month": 720}
_TS = re.compile(r"(?i)\b(\d+|an?|one|two|three|four|five|six|seven|eight|nine|ten|twelve|few|several|couple(?: of)?)\s+(minute|hour|day|night|week|month)s?\s+(?:later|pass(?:es|ed)?|go(?:es)? by|of (?:rest|sleep|recovery)|(?:of )?rest(?:ing)?|(?:in|of) bed)")
_FOR = re.compile(r"(?i)\b(?:rest\w*|sleep\w*|recover\w*|wait\w*|heal\w*|recuperat\w*|convalesc\w*)\s+(?:for\s+)?(\d+|an?|one|two|three|four|five|six|seven|eight|nine|ten|twelve|few|several|couple(?: of)?)\s+(minute|hour|day|night|week|month)s?\b")
_SLEEP = re.compile(r"(?i)\b(?:sleeps?|slept|sleeping|rests?|resting|naps?)\b[^.!?\n]{0,30}\b(?:night|until (?:morning|dawn)|through|long rest|for hours)|\blong rest\b|\bfalls? asleep\b|\bsleep(?:s)? it off\b")
_SHORT = re.compile(r"(?i)\bshort rest\b|\bcatch(?:es)? (?:a |their |his |her )?breath\b|\brests? (?:for )?a (?:moment|while|bit)\b")


def skip_hours(text):
    """How much story time does this text skip? ('three days later', 'sleeps through the night', 'a long rest')"""
    t, h = text or "", 0.0
    for m in list(_TS.finditer(t)) + list(_FOR.finditer(t)):
        n = _NUM.get(re.sub(r"\s*of$", "", m.group(1).lower()), None)
        n = n if n is not None else int(m.group(1))
        h += min(n, 400) * _UNIT[m.group(2).lower()]
    if _SLEEP.search(t):
        h = max(h, 8.0)
    elif _SHORT.search(t):
        h = max(h, 1.0)
    return min(h, 24 * 365)


_PART_RX = r"(left arm|right arm|arm|left leg|right leg|leg|shoulder|ribs?|hand|wrist|ankle|knee|head|side|back|chest|face|jaw|thigh|foot|hip|stomach|abdomen|torso|neck)"
_INJ = re.compile(r"(?i)\b(?:(cuts?|cut|slashe?s?|slashed|stabs?|stabbed|slices?|sliced|pierces?|pierced|impales?|impaled|shoots?|shot|grazes?|grazed|burns?|burned|burnt|scorch\w*|breaks?|broke|broken|fractur\w+|snaps?|snapped|twists?|twisted|sprain\w*|bruis\w+|bites?|bit|bitten|claws?|clawed|maul\w*|crush\w*|batter\w*|clubs?|clubbed|gash\w*|wound\w*)\b)")
_NEG = re.compile(r"(?i)\b(?:miss(?:es|ed)?|dodg\w+|barely|fails?|failed|without|almost|nearly|can'?t|cannot|won'?t|would|could|might|if|unless|unharmed|unscathed|spares?|spared|avoid\w*|no |not |never|rather than|instead)\b")
_BIG = re.compile(r"(?i)\b(?:deep|severe\w*|savage\w*|brutal\w*|badly|shatter\w*|horrific|nasty|gaping|agonis\w+|mortal\w*|grievous\w*)\b")
_SMALL = re.compile(r"(?i)\b(?:graze\w*|scratch\w*|nick\w*|minor|slight\w*|light(?:ly)?|small|shallow|faint)\b")
_ILL = re.compile(r"(?i)\b(?:catch(?:es)?|caught|came down with|comes down with|develop(?:s|ed)?|contract(?:s|ed)?|suffer(?:s|ing)? from|falls? ill with|has|have|had|is running|running)\s+(?:a |an |the )?(?:(?:nasty|bad|severe|terrible|mild|slight|raging|high)\s+)?(cold|flu|fever|infection|plague|virus|pneumonia|food poisoning|poisoning|migraine|stomach bug|fever|blood poisoning|sepsis|concussion)\b")
_SICK = re.compile(r"(?i)\b(?:is|are|was|looks?|feels?|grows?|turns?)\s+(?:very |really |terribly |suddenly |quite )?(sick|ill|feverish|nauseous|delirious)\b")
_DEATH = r"(?:dies|died|is dead|was killed|has died|lies dead|draws? (?:his|her|their|a) last breath|breathes? (?:his|her|their) last|takes? (?:his|her|their) last breath|falls? lifeless|goes? (?:limp|still) forever|is no more|has no pulse|stops breathing for good|(?:is|lies) lifeless|bleeds? out)"
_QUOTE = re.compile(r'[“"][^”"]*[”"]')
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")


def _narr(text):
    t = re.sub(r"\*\*", "", text or "")
    t = _QUOTE.sub(" ", t)
    return [s.strip(" *_") for s in _SENT.split(t) if s.strip(" *_")]


def observe(text, members, user="", you_is_user=True):
    """Read what a piece of narration says happened to bodies. Returns [{"id", "what": injury|illness|death, ...}] (dialogue is ignored).
    Conservative on purpose: negations, hypotheticals and near-misses are skipped."""
    out = []
    names = [(c["id"], re.compile(r"(?<![\w@])(?:%s)(?![\w])" % "|".join(re.escape(x) for x in dict.fromkeys([n, n.split()[0]]) if len(x) >= 2), re.I))
             for c in members for n in [(c.get("name") or "").strip()] if len(n) >= 2]
    for s in _narr(text):
        who = [cid for cid, rx in names if rx.search(s)]
        you = bool(re.search(r"(?i)\byou(?:r|rs|rself)?\b", s)) and you_is_user
        for cid in who:
            rx = dict(names)[cid]
            if re.search(r"(?i)(?:^|[^\w])%s(?:'s)?\s+%s" % (rx.pattern, _DEATH), s) or re.search(r"(?i)\b%s\b[^.]{0,40}\b(?:lifeless body|corpse)\b" % rx.pattern, s):
                if not _NEG.search(s):
                    out.append({"id": cid, "what": "death", "how": "died"})
                    continue
        if not who and not you:
            continue
        subject = who[:1] or (["user"] if you else [])
        if len(who) > 1 and not you:
            continue    # two characters in one sentence: whose wound? do not guess
        if _NEG.search(s):
            continue
        m = _INJ.search(s)
        if m and (re.search(_PART_RX, s, re.I) or re.search(r"(?i)\b(?:wounded|injured|bleeding|hurt)\b", s)):
            part = (re.search(_PART_RX, s, re.I) or [None, None])[1]
            part = {"arm": "left arm", "leg": "right leg", "chest": "ribs", "stomach": "side", "abdomen": "side", "torso": "ribs", "wrist": "hand",
                    "ankle": "knee", "face": "head", "jaw": "head", "neck": "head", "hip": "thigh", "foot": "knee", "rib": "ribs"}.get((part or "").lower(), (part or "").lower()) or None
            if part and part not in PARTS:
                part = None
            verb = m.group(1).lower()
            kind = ("burn" if re.match(r"burn|scorch", verb) else "fracture" if re.match(r"break|broke|broken|fractur|snap", verb) else "sprain" if re.match(r"twist|sprain", verb)
                    else "gunshot wound" if re.match(r"shoot|shot", verb) else "bite" if re.match(r"bit", verb) else "bruise" if re.match(r"bruis|crush|batter|club", verb) else "gash")
            sev = 3 if _BIG.search(s) else 1 if _SMALL.search(s) else 2
            out.append({"id": subject[0], "what": "injury", "kind": kind, "part": part, "sev": sev})
            continue
        m = _ILL.search(s)
        if m:
            out.append({"id": subject[0], "what": "illness", "kind": m.group(1).lower(), "sev": 3 if _BIG.search(s) else 1 if _SMALL.search(s) else 2})
            continue
        m = _SICK.search(s)
        if m:
            out.append({"id": subject[0], "what": "illness", "kind": "sickness", "sev": 2})
    seen, uniq = set(), []
    for o in out:
        key = (o["id"], o["what"], o.get("kind"), o.get("part"))
        if key not in seen:
            seen.add(key)
            uniq.append(o)
    return uniq
