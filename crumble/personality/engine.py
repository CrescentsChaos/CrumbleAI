"""The personality engine's front door. The rest of the app calls only these functions:

    settings(params)            normalise the on/off + depth options sent by the page
    prepare(c, st, hist, cfg)   before a reply: the personality block (+ end-of-prompt reminder) for the prompt
    check_reply(...)            after generation: score the reply for staying in character, maybe ask for a re-roll
    after_turn(...)             after the reply: personality-shaped mood and affection, canon, drift log
    profile_for / public        the analysed profile of a sheet (cached)
"""
import time

from ..rp.narrator import NARR_ID
from . import canon as cn
from . import directives, dynamics, stimulus, voice
from .profile import profile_for

THRESHOLD = {"light": 55, "standard": 65, "deep": 75}


def settings(p):
    p = p or {}
    depth = p.get("depth") if p.get("depth") in directives.LIMITS else "standard"
    return {"on": bool(p.get("on")), "depth": depth, "guard": bool(p.get("guard", True)),
            "dyn": bool(p.get("dyn", True)), "canon": bool(p.get("canon", True))}


def active(c, cfg):
    return bool(cfg and cfg.get("on")) and (c or {}).get("id") != NARR_ID


def _last(hist, role):
    return next((m for m in reversed(hist or []) if m.get("role") == role and (m.get("content") or "").strip()), None)


def prepare(c, st, hist, cfg):
    """-> (block, tail). Empty strings when the engine is off or has nothing to say."""
    if not active(c, cfg):
        return "", ""
    prof = profile_for(c)
    lu = _last(hist, "user")
    stim = stimulus.read((lu or {}).get("content", ""), prof)
    return directives.build(c, prof, stim, st or {}, cfg["depth"])


def check_reply(c, st, text, own, mode, cfg):
    """-> {'score','flags','retry','note'} or None when the guard is off."""
    if not active(c, cfg) or not cfg.get("guard"):
        return None
    prof = profile_for(c)
    if "fp" not in prof:
        prof["fp"] = voice.fingerprint(c)
    canon = ((st or {}).get("pers") or {}).get("canon") if cfg.get("canon") else None
    return voice.check(c, prof, text, own, mode, canon, prof["fp"], THRESHOLD[cfg["depth"]])


def _sanitize(items):
    out = []
    for f in items if isinstance(items, list) else []:
        f = str(f).strip().rstrip(".")
        if 6 < len(f) < 110:
            out.append(f)
    return out[:3]


def after_turn(c, st, j, mood, delta, hist, user, cfg, now=None):
    """Personality-shaped update after a reply. `j` is the model's parsed JSON (may carry 'self_facts').
    -> {'mood','energy','delta','pers','score','flags'}"""
    prof = profile_for(c)
    now = now or time.time()
    lu, la = _last(hist, "user"), _last(hist, "assistant")
    stim = stimulus.read((lu or {}).get("content", ""), prof)
    pers = dict(st.get("pers") or {})
    gap = (now - pers["ts"] / 1000) if pers.get("ts") else 0.0
    if cfg.get("dyn"):
        res = dynamics.advance(prof, st, mood, delta, stim, gap, now)
    else:
        res = {"mood": mood, "energy": None, "delta": delta, "pers": dict(pers, ts=int(now * 1000))}
    p = res["pers"]
    old = [x for x in (pers.get("canon") or []) if str(x).strip()]
    reply = (la or {}).get("content", "")
    score = flags = None
    if reply:
        if "fp" not in prof:
            prof["fp"] = voice.fingerprint(c)
        own = [m["content"] for m in (hist or []) if m.get("role") == "assistant" and m is not la]
        chk = voice.check(c, prof, reply, own, "story", old if cfg.get("canon") else None, prof["fp"], THRESHOLD[cfg["depth"]])
        score, flags = chk["score"], chk["flags"]
        p["drift"] = (pers.get("drift") or [])[-39:] + [{"ts": int(now * 1000), "score": score, "flags": flags[:2]}]
    else:
        p["drift"] = pers.get("drift") or []
    if cfg.get("canon"):
        p["canon"] = cn.merge(old, (cn.extract(reply) if reply else []) + _sanitize((j or {}).get("self_facts")))
    else:
        p["canon"] = old
    res.update(pers=p, score=score, flags=flags)
    return res
