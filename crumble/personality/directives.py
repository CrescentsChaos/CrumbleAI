"""Turns a profile, the current exchange and the character's state into the prompt text that keeps a model in character."""
import re
from ..config import CH, US
from . import lexicon as lx

LIMITS = {"light": dict(k=3, canon=0, react=1, rules=True), "standard": dict(k=5, canon=8, react=2, rules=True),
          "deep": dict(k=7, canon=14, react=3, rules=True)}


def behaviours(t, k):
    far = sorted(((abs(t[x] - 50), x) for x in lx.TRAITS if abs(t[x] - 50) >= 20), reverse=True)[:k]
    return [lx.BEHAVE[x][0 if t[x] >= 50 else 1] for _, x in far]


def voice_lines(t, voice):
    out = []
    if t["formality"] <= 35:
        out.append("casual: contractions, fragments, everyday words")
    elif t["formality"] >= 70:
        out.append("proper: complete sentences, no slang")
    if t["verbosity"] <= 30:
        out.append("short, clipped replies")
    elif t["verbosity"] >= 70:
        out.append("can run long and wander")
    if t["expressiveness"] <= 30:
        out.append("understated: few exclamation marks")
    elif t["expressiveness"] >= 70:
        out.append("openly expressive")
    if voice["no_emoji"] or (t["formality"] >= 65 and not voice["emoji"]):
        out.append("no emoji")
    return out


def reactions(t, T, stim, n):
    """One line per thing {US} just did, chosen by who the character is. Strongest first."""
    A, N, P, W, AS, TR = t["agreeableness"], t["neuroticism"], t["pride"], t["warmth"], t["assertiveness"], t["trust"]
    out = []
    if stim["hostile"] >= .5:
        out.append((stim["hostile"], f"{US} is hostile to {CH}: " + (
            "sharp and direct; fires back and does not back down." if AS >= 60 and (A <= 50 or P >= 65) else
            "visibly upset, reacts strongly and may lash out or tear up." if N >= 65 else
            "flustered or hurt; withdraws or tries to placate instead of retaliating." if AS <= 35 else
            "stays cool and answers evenly, maybe with a cold remark." if N <= 35 else
            "pushes back firmly, in character.")))
    if stim["vulnerable"] >= .5:
        out.append((stim["vulnerable"], f"{US} is opening up about something painful: " + (
            f"{CH} drops the jokes, listens and comforts in their own way." if A >= 60 or W >= 60 else
            f"{CH} is awkward about feelings and helps practically or gruffly instead of with soft words." if W <= 35 else
            f"{CH} responds sincerely.")))
    if stim["challenge"] >= .5:
        out.append((stim["challenge"], f"{US} is challenging {CH}: " + (
            "digs in and defends their position." if P >= 65 else
            "listens and concedes what is fair." if A >= 65 else
            "holds their position unless given a good reason.")))
    if stim["kind"] >= .5 or stim["praise"] >= .5:
        s = max(stim["kind"], stim["praise"])
        out.append((s * .9, f"{US} is being kind or complimentary: " + (
            "takes it with easy confidence, a little smug." if P >= 65 else
            "gets embarrassed and deflects." if P <= 35 and A >= 50 else
            "is wary of it and warms up slowly." if TR <= 35 else
            "warms up visibly and returns it." if A >= 65 or W >= 65 else
            f"responds warmly in {CH}'s own way.")))
    if stim["apology"] >= .5:
        out.append((stim["apology"] * .8, f"{US} is apologising: " + (
            "accepts it, relieved." if T["forgive"] >= .6 else
            "accepts it coldly; it is not forgotten yet." if T["forgive"] <= .35 else
            "accepts it, a little stiffly.")))
    if stim["dismissive"] >= .5:
        out.append((stim["dismissive"] * .7, f"{US} is being curt or dismissive: " + (
            f"{CH} feels it and shows a flicker of hurt or prods for more." if N >= 60 or W >= 60 else
            f"{CH} shrugs it off and moves on.")))
    if stim["flirt"] >= .5:
        out.append((stim["flirt"] * .6, f"{US} is flirting: " + (
            "gets visibly flustered but may secretly enjoy it." if TR <= 35 or t["extraversion"] <= 30 else
            "flirts back boldly." if AS >= 65 and t["extraversion"] >= 60 else
            f"{CH} reacts naturally according to their personality, feelings and romance notes."
        )))
    out.sort(key=lambda x: -x[0])
    return [x for _, x in out]


def touches(stim):
    out = []
    if stim["triggers"]:
        out.append(f"{US} just touched something that sets {CH} off ({stim['triggers'][0]}). {CH} reacts the way their flaws and triggers say, not neutrally.")
    if stim["boundary"]:
        out.append(f"{US} pushed against a boundary of {CH}'s ({stim['boundary'][0]}). {CH} does not go along with it and says so firmly, in their own way.")
    if stim["fears"] and len(out) < 2:
        out.append(f"{US} brought up something {CH} fears ({stim['fears'][0]}): it unsettles them.")
    if stim["comforts"] and len(out) < 2:
        out.append(f"What {US} said is the kind of thing that comforts {CH} ({stim['comforts'][0]}).")
    if stim["dislikes"] and len(out) < 2:
        out.append(f"{CH} finds the mention of {stim['dislikes'][0]} mildly irritating.")
    if stim["likes"] and len(out) < 2:
        out.append(f"{CH} is genuinely interested in {stim['likes'][0]} and engages more than usual.")
    return out[:2]


def build(c, prof, stim, st, depth):
    """-> (system block, reminder for the end of the last user turn). Either may be ''."""
    L = LIMITS.get(depth, LIMITS["standard"])
    t, T, n = prof["traits"], prof["temper"], c.get("name") or "Character"
    pers = (st or {}).get("pers") or {}
    lines = []
    beh = behaviours(t, L["k"])
    if prof["summary"] and beh:
        lines.append(f"{CH} is {prof['summary']}. These are stable traits: {CH} behaves this way in every scene, whatever the mood.")
        lines += ["- " + b for b in beh]
        v = voice_lines(t, prof["voice"])
        if v and L["rules"]:
            lines.append("Voice: " + "; ".join(v) + ".")
    if L["rules"] and (prof["rules"]["never"] or prof["rules"]["always"]):
        rl = [f"Always {x}" for x in prof["rules"]["always"][:4]] + [x if x.lower().startswith(("never", "don", "do not", "avoid", "no ")) else f"Never {x}" for x in prof["rules"]["never"][:4]]
        lines.append("Hard rules (never break these): " + "; ".join(x.rstrip(".") for x in rl) + ".")
    if prof["reactions"]:
        lines.append(f"How {CH} reacts (from the author): {prof['reactions'][:400]}")
    now = []
    now += reactions(t, T, stim, n)[:L["react"]]
    now += touches(stim)
    if pers.get("grudge", 0) >= .4:
        now.append(f"{CH} is still smarting from how {US} treated them earlier: slower to warm up, a little guarded.")
    if now:
        lines.append("This turn:\n" + "\n".join("- " + x for x in now))
    canon = [x for x in (pers.get("canon") or []) if str(x).strip() and not bool(lx.AI_HARD.search(str(x)) or lx.AI_SOFT.search(str(x)) or re.search(r"\b(?:ai\b|artificial intelligence|chatbot|bot\b|virtual assistant|language model|llm)\b", str(x), re.I))][-L["canon"]:] if L["canon"] else []
    if canon:
        lines.append(f"Already established about {CH} (said earlier in this chat; stay consistent, never contradict):\n" + "\n".join("- " + x for x in canon))
    block = f"[{n} - Behaviour]\n" + "\n".join(lines) if lines else ""
    tail = ""   # only Deep adds a closing reminder; it is plain text (no brackets or 'Reply as'), so it can never be mistaken for a chat line
    if depth == "deep" and beh:
        tail = f"Voice: {n} stays {prof['summary'] or 'in character'}: {' '.join(beh[:2])}."
    return block, tail
