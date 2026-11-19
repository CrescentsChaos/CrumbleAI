"""An instant read on how a message will land, so the page can react the moment the user sends it.

No model call: it reuses the personality engine's tone reader and mood dynamics, so a proud character bristles at an
insult and a gentle one is touched by kindness, exactly as the real tracker will shape it a few seconds later.
The page shows this as a provisional reaction and replaces it with the tracker's answer when that arrives.
Nothing here is saved."""
import time

from .config import EMO
from .personality import dynamics, profile_for, stimulus

WHY = (("triggers", "a sore spot"), ("boundary", "crossing a line"), ("hostile", "harsh words"), ("dismissive", "being brushed off"),
       ("apology", "an apology"), ("praise", "praise"), ("kind", "kind words"), ("vulnerable", "opening up"), ("flirt", "flirting"),
       ("comforts", "something comforting"), ("challenge", "a challenge"))


def _neutral():
    return {"temper": {"react": 1.0, "warm": 1.0, "hurt": 1.0, "forgive": .5, "tau": 3600.0, "base_v": 0.0, "base_a": 0.0}, "kw": {}}


def peek(c, st, text):
    """-> {'quiet': True} when nothing in the message would move them, else {'mood','emoji','energy','delta','tags','why'}."""
    st = st if isinstance(st, dict) else {}
    try:
        prof = profile_for(c)
    except Exception:
        prof = None
    stim = stimulus.read(text, prof)
    tags = list(stim.get("tags") or [])
    hit = bool(stim.get("triggers") or stim.get("boundary"))
    why = next((w for k, w in WHY if stim.get(k) and (stim[k] if isinstance(stim[k], list) else stim[k] >= .5)), "")
    if not tags and not hit and not stim.get("comforts"):
        return {"quiet": True}
    raw = (2 * stim["kind"] + 1.5 * stim["praise"] + 1.5 * stim["apology"] + .6 * stim["vulnerable"] + .5 * stim["flirt"]
           - 3 * stim["hostile"] - 1.5 * stim["dismissive"] - (1.5 if hit else 0))
    raw = max(-5.0, min(5.0, raw))
    T = (prof or _neutral())["temper"]
    if hit:
        want = "hurt" if T["hurt"] > 1.25 else "angry"
    elif stim["hostile"] >= .6:
        want = "angry" if stim["hostile"] >= .85 and T["react"] >= 1 else "hurt" if T["hurt"] > 1.25 else "annoyed"
    elif stim["dismissive"] >= .5:
        want = "annoyed"
    elif stim["apology"] >= .6:
        want = "relaxed"
    elif stim["flirt"] >= .6 and stim["kind"] < .6:
        want = "flustered"
    elif stim["praise"] >= .6:
        want = "proud"
    elif stim["kind"] >= .5:
        want = "happy"
    elif stim["vulnerable"] >= .5:
        want = "thoughtful"
    elif stim.get("comforts"):
        want = "relaxed"
    else:
        want = ""
    try:
        res = dynamics.advance(prof or _neutral(), {"mood": st.get("mood") or "neutral", "pers": dict(st.get("pers") or {})}, want, raw, stim, 0.0, time.time())
    except Exception:
        return {"quiet": True}
    mood = res["mood"]
    return {"mood": mood, "emoji": EMO.get(mood, "🙂"), "energy": res["energy"], "delta": int(res["delta"]), "tags": tags[:3], "why": why}
