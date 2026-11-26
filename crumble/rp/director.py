"""Who speaks next in a group chat."""
import random
import re

from ..config import STOPW
from .mentions import at_all, find_ids
from . import circle as circ
from .narrator import NARR_ID


def talk_of(c, pers=False):
    """How chatty a character is in a group, 0..1: from the Talkativeness field, else guessed from the sheet
    (or, with the personality engine on, from the analysed traits)."""
    t = (c.get("talk") or "").lower()
    if pers and not t.strip():
        from ..personality import profile_for
        tr = profile_for(c)["traits"]
        return max(.15, min(.9, .15 + .75 * (.6 * tr["extraversion"] + .4 * tr["verbosity"]) / 100))
    m = re.search(r"\d+", t)
    if m:
        return max(0, min(100, int(m[0]))) / 100
    if re.search(r"quiet|silent|reserved|shy|laconic|terse|few words", t):
        return .25
    if re.search(r"chatty|loud|talkative|gossip|talks a lot|never shuts|excitable", t):
        return .85
    blob = " ".join((c.get(k) or "") for k in ("personality", "description", "quirks", "texting")).lower()
    lo = len(re.findall(r"\b(quiet|shy|reserved|introvert\w*|stoic|laconic|taciturn|withdrawn|aloof|few words|soft-spoken)\b", blob))
    hi = len(re.findall(r"\b(chatty|talkative|outgoing|extrovert\w*|loud|bubbly|boisterous|gossip\w*|rambl\w*|energetic|social butterfly)\b", blob))
    return max(.15, min(.9, .5 + .15 * (hi - lo)))


def likes_hit(c, text):
    mine = set(re.findall(r"[a-z]{5,}", " ".join((c.get(k) or "") for k in ("likes", "goals", "occupation", "skills", "fears")).lower())) - STOPW
    return bool(mine & set(re.findall(r"[a-z]{5,}", text.lower())))


PACE = {"quiet": (.55, (1, 1, 1, 2)), "natural": (1.0, (1, 1, 2, 2, 3)), "lively": (1.5, (2, 2, 3, 4))}


def _thread(hist, members_ids):
    """The side conversation going on right now: the two characters who have been answering each other, and how long. -> (a, b, turns) or None."""
    ids = []
    for m in reversed(hist):
        if m.get("role") != "assistant" or not m.get("cid") or m.get("cid") not in members_ids:
            break
        ids.append(m["cid"])
    if len(ids) < 2 or ids[0] == ids[1]:
        return None
    a, b, n = ids[0], ids[1], 0
    for k, i in enumerate(ids):
        if i != (a if k % 2 == 0 else b):
            break
        n += 1
    return (b, a, n) if n >= 2 else None


def plan_next(g, members, hist, spoke, cap, n, user, o):
    """Decide who speaks next (or nobody). Mentions get an answer, chatty characters speak more, and the talk winds down on its own.
    With a circle (how the characters feel about each other) the rest of the room follows the relationships: rivals interrupt and
    disagree, the jealous cut in, allies back each other up, two people can drift into a side conversation, and a character the
    moment has nothing to do with stays out of it."""
    pm, caps = PACE.get(g.get("pace"), PACE["natural"])
    by_id = {c["id"]: c for c in members}
    cc = circ.clean(o.get("circle"), list(by_id)) if o.get("circle") else None
    affs = {str(k): v for k, v in (o.get("aff") or {}).items()}
    last = hist[-1] if hist else None
    by_user = bool(last) and last.get("role") == "user"
    text, lastc = str((last or {}).get("content") or ""), (last or {}).get("cid")
    by = user if by_user else str((last or {}).get("name") or "Someone")
    cap = cap or random.choice(caps)
    lu = next((m for m in reversed(hist) if m.get("role") == "user"), None)
    utext = str((lu or {}).get("content") or "") if (by_user or spoke) else ""   # what the user said that started this round
    ment, named = (find_ids(utext, members, True) if utext else []), find_ids(text, members, False)
    allf = bool(utext) and at_all(utext)
    forced = [i for i in (random.sample(list(by_id), len(by_id)) if allf else ment) if i != lastc]
    aforced = [] if by_user else [i for i in find_ids(text, members, True) if i != lastc]   # one character called out another
    talked = [i for i in spoke if i != NARR_ID]
    keep = bool(o.get("keep"))
    if utext:
        cap = max(cap, min(6, len(forced)))

    def res(i, why, p=False, to=None, about=None):
        r = {"next": i, "why": why, "by": by, "cap": cap, "pass": p}
        if to and to in by_id:
            r["to"], r["to_name"] = to, by_id[to].get("name")
        if about and about in by_id:
            r["about"] = by_id[about].get("name")
        return r

    def can(i, limit=1):
        return i in by_id and spoke.count(i) < limit

    reply_to = lastc if (lastc and lastc in by_id and not by_user) else None
    if g.get("narrator") and o.get("fx") and n == 0 and NARR_ID not in spoke:
        return res(NARR_ID, "narrate")
    for i in forced:
        if can(i):
            return res(i, "mention", to="")
    for i in o.get("acting") or []:
        if can(i):
            return res(i, "react")
    for i in aforced:
        if can(i) and len(talked) < cap:
            return res(i, "mention", to=lastc)
    th = _thread(hist, set(by_id)) if (cc and not by_user and not forced) else None
    if cc and reply_to and not by_user:
        # an interruption: someone who cannot let what was just said stand, or who is jealous of the speaker
        if len(talked) < cap + 1:
            for i in random.sample(list(by_id), len(by_id)):
                if i == reply_to or i in spoke or i == NARR_ID:
                    continue
                p = circ.pull(cc, i, reply_to)
                heat = max(p["x"] - 50, (p["j"] - 35) * 1.1)
                if heat > 0 and random.random() < min(.6, .12 + heat / 90) * (.6 + talk_of(by_id[i], bool(o.get("pers")))):
                    return res(i, "jealous" if p["j"] >= 40 and p["j"] * 1.1 >= p["x"] - 15 else "interrupt", to=reply_to, about=reply_to)
        # a side conversation carries on for a few turns between the two of them
        if th and th[2] < 4 and len(talked) < cap + 2:
            nxt = th[0] if lastc == th[1] else th[1]
            if can(nxt, 2) and random.random() < .8 - .15 * th[2]:
                return res(nxt, "thread", to=lastc)
    if len(talked) >= cap:
        return {"next": None, "cap": cap}
    cands = [i for i in by_id if can(i) and (by_user or i != lastc)]
    if not cands:
        return {"next": None, "cap": cap}
    scored = []
    for i in cands:
        c = by_id[i]
        rel = 0.0
        if cc and reply_to:
            p = circ.pull(cc, i, reply_to)
            rel = abs(p["f"] - 50) / 140 + p["x"] / 160 + (.15 if p["k"] not in ("auto",) else 0)
        base = .12 + .5 * talk_of(c, bool(o.get("pers"))) + (.5 if i in named else 0) + (.15 if likes_hit(c, text) else 0) + rel + (int(affs.get(i, 50)) - 50) / 250
        s = base
        if ment and not allf:
            s *= .3   # the user spoke to someone else: the rest mostly stay out of it
        if th and i not in (th[0], th[1]) and i not in named:
            s *= .35  # two people are talking: the rest let them
        if talked and not (i in named or likes_hit(c, text) or rel > .25):
            s *= .45  # someone already answered and nothing here is about this one: they do not pile on
        s = s * .7 ** len(talked) + random.uniform(0, .22)
        scored.append((s, i))
    scored.sort(reverse=True)
    must = (by_user or keep) and not talked
    for s, i in scored:
        if random.random() < min(.95, s * pm):
            why, to, about = "named" if i in named else "chat", reply_to, None
            if cc and reply_to:
                p = circ.pull(cc, i, reply_to)
                if th and i not in (th[0], th[1]) and not named:
                    why, to = "branch", ("user" if random.random() < .5 else None)
                    to = None if to == "user" else to
                elif p["x"] >= 35 and p["f"] < 60:
                    why = "disagree"
                elif p["k"] in ("ally", "friend", "family", "romance") and p["f"] >= 62 and p["t"] >= 55 and p["x"] < 30 and not by_user and random.random() < .5:
                    why = "back"
                elif (int(affs.get(i, 50)) - int(affs.get(reply_to, 50))) >= 35 or (int(affs.get(reply_to, 50)) - int(affs.get(i, 50))) >= 35:
                    why = "disagree" if not by_user else why
            return res(i, why, not must and why in ("chat", "named", "branch"), to=to, about=about)
    if must:
        i = scored[0][1]
        return res(i, "open" if keep and not by_user else "chat", to=reply_to)
    return {"next": None, "cap": cap}
