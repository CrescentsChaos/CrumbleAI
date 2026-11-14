"""Turns a character sheet into a stable personality profile. Pure functions, no model calls:
the same sheet always gives the same profile."""
import hashlib
import math
import re

from ..config import STOPW
from . import lexicon as lx

# field -> how much a trait word found there counts
SCAN = {"traits": 2.0, "personality": 1.0, "flaws": .9, "quirks": .8, "humor": .8, "values": .5, "speech": .6,
        "texting": .6, "vocab": .6, "mood_speech": .4, "body_language": .5, "description": .5}
HASHED = tuple(SCAN) + ("triggers", "boundaries", "fears", "dislikes", "likes", "comfort", "goals", "reactions",
                        "consistency", "mes_example", "name")
EXTRA_STOP = set("when someone people being anything about very really feel feeling has get gets makes make into "
                 "from them they their there then than will would could should only also much more most some "
                 "such what which while where who whom whose been were does done doing".split())
_KV = re.compile(r"\b([A-Za-z][A-Za-z-]{0,16})\b\s*[:=]?\s*(\d{1,3}|very high|very low|high|low|medium|mid|moderate)\b", re.I)
_KV_REV = re.compile(r"\b(very high|very low|high|low|medium|moderate)\s+([A-Za-z][A-Za-z-]{0,16})\b", re.I)
_cache = {}


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def parse_override(text):
    """'O 70 C 40, warmth: high, sarcastic and guarded' -> ({trait: value}, leftover free text)."""
    found, spans = {}, []

    def take(key, val, m):
        t = lx.ALIASES.get(key.lower())
        if not t or (len(key) == 1 and not key.isupper()):
            return
        v = lx.LEVELS.get(val.lower()) if not val.isdigit() else clamp(int(val), 0, 100)
        if v is not None:
            found[t] = v
            spans.append(m.span())

    for m in _KV.finditer(text or ""):
        take(m.group(1), m.group(2), m)
    for m in _KV_REV.finditer(text or ""):
        take(m.group(2), m.group(1), m)
    rest = text or ""
    for a, b in sorted(spans, reverse=True):
        rest = rest[:a] + " " + rest[b:]
    return found, rest


def scan(text, weight, net, ev):
    """Add evidence from one field. net[trait] += signed weight; ev[trait] collects (word, sign)."""
    low = (text or "").lower().replace("’", "'")
    if not low.strip() or weight <= 0:
        return
    seen = {}
    for t in lx.TRAITS:
        for sign, rx in ((1, lx.UP_RX[t]), (-1, lx.DOWN_RX[t])):
            for m in rx.finditer(low):
                pre = low[max(0, m.start() - 30):m.start()]
                w = weight
                if lx.NEGATORS.search(pre):
                    sign_, w = -sign, w * .7
                else:
                    sign_ = sign
                if lx.BOOST.search(pre):
                    w *= 1.5
                elif lx.HEDGE.search(pre):
                    w *= .6
                key = (t, m.group(0), sign_)
                seen[key] = seen.get(key, 0) + 1
                n = seen[key]
                if n > 3:
                    continue
                net[t] += sign_ * w * (1 if n == 1 else .3)
                if (m.group(0), sign_) not in ev[t]:
                    ev[t].append((m.group(0), sign_))


def stem(w):
    for suf in ("ingly", "ness", "ment", "ing", "ied", "ies", "ed", "es", "ly", "er", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            break
    return w[:-1] if len(w) > 3 and w.endswith("e") else w


def stems(text):
    return {stem(w) for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in STOPW and w not in EXTRA_STOP}


def keywords(text, limit=24):
    """A list field ('being ignored, loud chewing; betrayal') -> [{'text','stems','need'}]."""
    out = []
    for part in re.split(r"[,;\n•]|\band\b|\bor\b|[()]", text or "", flags=re.I):
        part = part.strip(" .-–—'\"")
        s = stems(part)
        if len(part) >= 3 and s:
            need = len(s) if len(s) <= 2 else math.ceil(len(s) * .6)
            out.append({"text": part[:60], "stems": sorted(s), "need": need})
        if len(out) >= limit:
            break
    return out


def rules(text):
    """The Consistency field: lines starting with never/don't/avoid are 'never' rules, the rest 'always' rules."""
    never, always = [], []
    for ln in re.split(r"[\n;]|(?<=[.!?])\s+", text or ""):
        ln = ln.strip(" -•*.")
        if len(ln) < 3:
            continue
        (never if re.match(r"(?:never|don'?t|do not|doesn'?t|does not|won'?t|avoid|no |not )", ln, re.I) else always).append(ln[:140])
    return {"never": never[:12], "always": always[:12]}


def _hash(c):
    raw = "\x1f".join(str(c.get(k) or "") for k in HASHED)
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:12]


def temperament(t):
    """How this personality moves: the numbers the dynamics module runs on."""
    N, E, A, C = t["neuroticism"], t["extraversion"], t["agreeableness"], t["conscientiousness"]
    ex, pr, tr, im = t["expressiveness"], t["pride"], t["trust"], t["impulsivity"]
    return {
        "react": round(clamp(1 + .012 * (N - 50) + .006 * (ex - 50) - .004 * (C - 50), .55, 1.6), 3),
        "tau": round(3600 * clamp(1.5 + 4 * N / 100 + 1.5 * (pr - 50) / 50 - 1 * (A - 50) / 50, .5, 10), 1),
        "base_v": round(clamp((A - 50) / 150 + (E - 50) / 150 - (N - 50) / 120, -.5, .5), 3),
        "base_a": round(clamp((E - 50) / 150 + (N - 50) / 300 + (im - 50) / 300, -.5, .5), 3),
        "warm": round(clamp(1 + .012 * (A - 50) + .008 * (E - 50) + .008 * (tr - 50) - .005 * (pr - 50), .45, 1.6), 3),
        "hurt": round(clamp(1 + .011 * (N - 50) + .008 * (pr - 50) - .009 * (A - 50), .5, 1.7), 3),
        "forgive": round(clamp(.5 + .008 * (A - 50) - .006 * (pr - 50) - .003 * (N - 50), .15, .95), 3),
    }


def summary(t, n=5):
    far = sorted(((abs(t[k] - 50), k) for k in lx.TRAITS if abs(t[k] - 50) >= 18), reverse=True)[:n]
    return ", ".join(lx.ADJ[k][0 if t[k] >= 50 else 1] for _, k in far)


def derive(c):
    ov, rest = parse_override(c.get("traits") or "")
    net = {k: 0.0 for k in lx.TRAITS}
    ev = {k: [] for k in lx.TRAITS}
    for field, w in SCAN.items():
        scan(rest if field == "traits" else c.get(field) or "", w, net, ev)
    hum = (c.get("humor") or "").strip()
    if len(hum) >= 10 and net["humor"] >= 0 and not ev["humor"]:
        net["humor"] += .8        # an author who bothered to describe the humour has a funny character
    direct = {k: 50 + 45 * math.tanh(.55 * net[k]) for k in lx.TRAITS}
    t, src = {}, {}
    for k in lx.BIG5:
        t[k] = direct[k]
    for k in lx.AXES:
        t[k] = direct[k] + sum(co * (t[b] - 50) for b, co in lx.CROSS[k].items())
    for k in lx.TRAITS:
        t[k] = int(round(clamp(t[k], 0, 100)))
        src[k] = "sheet" if ev[k] else ("derived" if abs(t[k] - 50) >= 6 else "default")
    for k, v in ov.items():
        t[k], src[k] = int(v), "set"
    # the five broad traits changed by an override should flow into the axes that were only derived
    if any(k in ov for k in lx.BIG5):
        for k in lx.AXES:
            if src[k] != "set" and not ev[k]:
                t[k] = int(round(clamp(50 + sum(co * (t[b] - 50) for b, co in lx.CROSS[k].items()), 0, 100)))
                src[k] = "derived" if abs(t[k] - 50) >= 6 else "default"
    evidence = {k: [w for w, _ in ev[k]][:4] for k in lx.TRAITS if ev[k]}
    kw = {k: keywords(c.get(f)) for k, f in (("triggers", "triggers"), ("boundary", "boundaries"), ("fears", "fears"),
                                              ("dislikes", "dislikes"), ("comforts", "comfort"), ("likes", "likes"))}
    texting = f"{c.get('texting') or ''} {c.get('vocab') or ''}".lower()
    return {
        "hash": _hash(c), "traits": t, "src": src, "evidence": evidence, "summary": summary(t),
        "temper": temperament(t), "kw": kw, "rules": rules(c.get("consistency")),
        "reactions": (c.get("reactions") or "").strip()[:600],
        "voice": {"emoji": bool(re.search(r"emoji", texting)) and not re.search(r"no emoji|never.{0,12}emoji|without emoji", texting),
                  "no_emoji": bool(re.search(r"no emoji|never.{0,12}emoji|without emoji", texting)),
                  "lowercase": bool(re.search(r"all lowercase|lowercase|no caps|never capitali[sz]es", texting))},
        "evidence_total": sum(len(v) for v in ev.values()) + len(ov),
    }


def profile_for(c):
    """Cached profile for a sheet (re-derived when any relevant field changes)."""
    key = (c.get("id") or c.get("name") or "?", _hash(c))
    if key not in _cache:
        if len(_cache) > 96:
            _cache.clear()
        _cache[key] = derive(c)
    return _cache[key]


def public(p):
    """What the editor and Memory tab show."""
    return {"traits": [{"k": k, "label": lx.LABEL[k], "v": p["traits"][k], "src": p["src"][k],
                        "ev": p["evidence"].get(k, [])} for k in lx.TRAITS],
            "summary": p["summary"], "temper": p["temper"], "rules": p["rules"],
            "triggers": [x["text"] for x in p["kw"]["triggers"] + p["kw"]["boundary"]][:8],
            "comforts": [x["text"] for x in p["kw"]["comforts"]][:8], "hash": p["hash"]}
