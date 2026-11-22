"""Who speaks next in a group chat."""
import random
import re

from ..config import STOPW
from .mentions import at_all, find_ids
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


PACE = {"quiet": (.55, (1, 1, 2)), "natural": (1.0, (1, 2, 2, 3)), "lively": (1.5, (2, 3, 3, 4))}


def plan_next(g, members, hist, spoke, cap, n, user, o):
    """Decide who speaks next (or nobody). Mentions get an answer, chatty characters speak more, and the talk winds down on its own."""
    pm, caps = PACE.get(g.get("pace"), PACE["natural"])
    by_id = {c["id"]: c for c in members}
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
    res = lambda i, why, p=False: {"next": i, "why": why, "by": by, "cap": cap, "pass": p}
    if g.get("narrator") and o.get("fx") and n == 0 and NARR_ID not in spoke:
        return res(NARR_ID, "narrate")
    for i in forced:
        if i not in spoke and i in by_id:
            return res(i, "mention")
    for i in o.get("acting") or []:
        if i in by_id and i not in spoke:
            return res(i, "react")
    for i in aforced:
        if i not in spoke and i in by_id and len(talked) < cap:
            return res(i, "mention")
    if len(talked) >= cap:
        return {"next": None, "cap": cap}
    cands = [i for i in by_id if i not in spoke and (by_user or i != lastc)]
    if not cands:
        return {"next": None, "cap": cap}
    aff = o.get("aff") or {}
    scored = []
    for i in cands:
        c = by_id[i]
        s = .2 + .55 * talk_of(c, bool(o.get("pers"))) + (.5 if i in named else 0) + (.15 if likes_hit(c, text) else 0) + (int(aff.get(i, 50)) - 50) / 250
        if ment and not allf:
            s *= .3   # the user spoke to someone else: the rest mostly stay out of it
        s = s * .7 ** len(talked) + random.uniform(0, .25)
        scored.append((s, i))
    scored.sort(reverse=True)
    must = (by_user or keep) and not talked
    for s, i in scored:
        if random.random() < min(.95, s * pm):
            return res(i, "named" if i in named else "chat", not must)
    if must:
        i = scored[0][1]
        return res(i, "open" if keep and not by_user else "chat")
    return {"next": None, "cap": cap}
