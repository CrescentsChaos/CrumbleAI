"""How a personality moves. The model proposes a mood and an affection change after each reply; this module bounds
and shapes them so the same character reacts the same way to the same thing: thin-skinned characters swing hard
and hold grudges, steady ones stay level, guarded ones warm up slowly, and moods drift back to the character's
resting temperament as time passes."""
import math
import time

from . import lexicon as lx

STEP = .8          # base distance the mood may travel in one exchange (valence/arousal units), scaled by reactivity


def _d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def nearest(v, a):
    return min(lx.PALETTE, key=lambda m: _d2((v, a), lx.MOOD_VA[m]))


def shape_affection(T, p, raw, stim):
    """-> integer change to apply. Fractions are carried to the next exchange so small nudges still add up."""
    w, h, fg = T["warm"], T["hurt"], T["forgive"]
    g = p.get("grudge", 0.0)
    hit = bool(stim.get("triggers") or stim.get("boundary"))
    hostile = stim.get("hostile", 0)
    d = float(raw)
    if d > 0:
        d *= w * (1 - .6 * g * (1 - fg))       # trust is repaired slowly while a grudge lasts
    elif d < 0:
        d *= h
    if hostile >= .6:
        d = min(d, -2 * h)                      # insults always land, more so on the thin-skinned
    elif hit:
        d = min(d, -1 * h)
    if stim.get("kind", 0) >= .6 and hostile < .3 and not hit and d > -1.5:
        d = max(d, .5 * w)                      # kindness is noticed even if the model missed it
    if stim.get("apology", 0) >= .6 and not hit and hostile < .3:
        d = max(d, 2 * fg)
    d = max(-6.0, min(6.0, d))
    tot = d + p.get("frac", 0.0)
    ap = int(tot)
    p["frac"] = round(tot - ap, 3)
    return ap


def advance(prof, st, llm_mood, raw_delta, stim, gap_s=0.0, now=None):
    """One exchange. Returns {'mood','energy','delta','pers'}; `pers` is the new personality state to store."""
    T = prof["temper"]
    p = dict(st.get("pers") or {})
    prev = str(st.get("mood") or "neutral")
    va = p.get("va")
    if not va or p.get("mood") != prev:          # first time, or the user set the mood by hand: start from what is shown
        va = list(lx.MOOD_VA.get(prev, (0.0, 0.0)))
    v, a = va
    if gap_s and gap_s > 0:                       # time heals: drift to the resting temperament
        k = 1 - math.exp(-gap_s / T["tau"])
        v += (T["base_v"] - v) * k
        a += (T["base_a"] - a) * k
        p["grudge"] = p.get("grudge", 0.0) * math.exp(-gap_s / (T["tau"] * 3))
    known = llm_mood in lx.MOOD_VA
    tv, ta = lx.MOOD_VA[llm_mood] if known else (v, a)
    hostile, kind = stim.get("hostile", 0), stim.get("kind", 0)
    hit = bool(stim.get("triggers") or stim.get("boundary"))
    if hostile >= .6:
        tv, ta = min(tv, v - .30), max(ta, a + .15)
    elif kind >= .6 and hostile < .3:
        tv = max(tv, v + .20)
    if hit:
        tv, ta = min(tv, v - .35), max(ta, a + .25)
    if stim.get("comforts") and v < 0:
        tv = max(tv, v + .25)
    lim = STEP * T["react"] * (1.5 if (hit or hostile >= .6 or kind >= .8) else 1.0)
    dv, da = tv - v, ta - a
    dist = math.hypot(dv, da)
    if dist > lim:
        v, a = v + dv * lim / dist, a + da * lim / dist
    else:
        v, a = tv, ta
    v, a = max(-1.0, min(1.0, v)), max(-1.0, min(1.0, a))
    if known and dist <= lim * 1.25:
        mood = llm_mood                          # the model's word is where we ended up: keep its nuance
    elif not known and dist < .05:
        mood = prev
    else:
        mood = nearest(v, a)
    delta = shape_affection(T, p, raw_delta, stim)
    fg = T["forgive"]
    gr = p.get("grudge", 0.0) + .22 * hostile + (.15 if hit else 0) + .06 * stim.get("dismissive", 0)
    if stim.get("apology", 0) >= .6:
        gr -= .3 * fg
    p["grudge"] = round(max(0.0, min(1.0, gr * (1 - .06 * fg))), 3)
    p.update(va=[round(v, 3), round(a, 3)], mood=mood, ts=int((now or time.time()) * 1000), n=int(p.get("n", 0)) + 1)
    energy = "high" if a > .35 else "low" if a < -.25 else "medium"
    return {"mood": mood, "energy": energy, "delta": delta, "pers": p}
