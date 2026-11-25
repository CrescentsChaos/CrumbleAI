"""The story engine: a living world around the conversation. It replaces the old fight engine.

Time matters, what each character is doing right now is worked out by the model for the moment (never a fixed timetable), the weather and the hour change
how people feel, small things happen in the world, people joke and feel and do not end every line with a question. All of it is derived from the chat itself on every turn (like the identity ledger and the
story clock), with no model call, so edits, swipes and rewinds can never leave it stale.

    settings(p)                               normalise the page's options
    sky(sim, amb, texts, seed, cfg)           the weather of the moment: what the story said, or a day-long one when it said nothing
    build(...)                                -> {'block', 'compact', 'tail', 'plan', 'info'} for the prompt and for the page
    overview(...)                             the same status for the page without writing a reply (no model call)
    check(text, plan) / repair(text, plan)    notes for a retry / the last-resort fix when the reply broke the rhythm
Modules: routine (daily life), world (season, weather, body clock), humor, moment (reading the last message), endings, beats (world events), tension (conflict).
"""
import re

from ..config import CH, US
from . import beats, doing as doing_mod, endings, humor, moment, routine, tension, wildlife, world
from .. import ambience, places

DEFAULTS = {"on": True, "routines": True, "weather": "dynamic", "events": "normal", "humor": "auto", "endings": True, "wildlife": "normal", "scare": "some"}
COMMIT = {"work", "class", "shift", "commute", "exercise", "sleep", "social", "errands"}


def settings(p):
    p = p if isinstance(p, dict) else {}
    return {"on": bool(p.get("on", True)), "routines": bool(p.get("routines", True)),
            "weather": p.get("weather") if p.get("weather") in ("dynamic", "story") else "dynamic",
            "events": p.get("events") if p.get("events") in ("off", "rare", "normal", "lively") else "normal",
            "humor": p.get("humor") if p.get("humor") in ("auto", "more", "less") else "auto", "endings": bool(p.get("endings", True)),
            "wildlife": p.get("wildlife") if p.get("wildlife") in ("off", "rare", "normal", "lively") else "normal",
            "scare": p.get("scare") if p.get("scare") in ("gentle", "some", "lots") else "some"}


def hm(h):
    m = int(round((h % 24) * 12)) * 5 % 1440
    return f"{(m // 60) % 12 or 12}:{m % 60:02d} {'AM' if m // 60 < 12 else 'PM'}"


def mins_txt(n):
    n = int(n)
    return f"about {n} minutes" if n < 90 else f"about {round(n / 60)} hours"


def sky(sim, amb, texts, seed, cfg):
    """{'weather', 'src': 'story'|'dynamic', 'trend', 'season'} or None. The story's own weather always wins."""
    seasn = world.season(sim, texts) if sim is not None or texts else ""
    if (amb or {}).get("weather"):
        return {"weather": amb["weather"], "src": "story", "trend": "", "season": seasn}
    if cfg.get("weather") == "dynamic" and sim:
        fc = world.forecast(sim, seasn, seed)
        return {"weather": fc["now"], "src": "dynamic", "trend": world.trend(fc), "season": seasn}
    return {"weather": "", "src": "", "trend": "", "season": seasn}


def status(c, sim, cfg, dg=None):
    """One character's place in the day, for the prompt and the page. The model's answer for this moment (dg) wins; without one, only a routine the
    author wrote themselves is used. A timetable guessed from the job is never shown as a fact about the character."""
    if dg is not None:
        if not cfg.get("routines", True):
            return None
        return {"id": c.get("id"), "name": c.get("name") or "", "act": doing_mod.label(dg), "state": dg.get("state", "free") if dg.get("here", True) else "away",
                "free": dg.get("free", .7), "mins": 0, "next": "", "weekend": False, "own": False, "key": "doing", "here": dg.get("here", True), "ai": True}
    rt = routine.now(c, sim) if (cfg.get("routines") and sim) else None
    if not rt or not rt["own"]:
        return None
    return {"id": c.get("id"), "name": c.get("name") or "", "act": rt["label"], "state": rt["state"], "free": rt["free"], "mins": rt["mins_left"], "next": rt["next"],
            "weekend": rt["weekend"], "own": rt["own"], "key": rt["key"]}


_AT = re.compile(r"(?i)\b(?:at|by|around|before)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?(?!\w)|\b(\d{1,2}):(\d{2})\s*(am|pm)?\b")


def plans(chron, sim):
    """Plans from earlier that are close in story time: ['\"...\" (in about 20 minutes)']."""
    if not chron or not sim:
        return []
    out = []
    for it in (chron.get("items") or [])[-60:]:
        t = str(it.get("t") or "")
        if it.get("k") not in ("plan", "promise") and not re.search(r"(?i)\b(?:meet|dinner|date|appointment|deadline|class|train|flight|bus|party|call|pick (?:you|me) up)\b", t):
            continue
        for m in _AT.finditer(t):
            h = m.group(1) or m.group(4)
            mi = m.group(2) or m.group(5) or 0
            ap = (m.group(3) or m.group(6) or "").lower().replace(".", "")
            if h is None:
                continue
            hr = int(h) % 12 + (12 if ap.startswith("p") else 0) if ap else (int(h) + 12 if int(h) < 7 else int(h))
            at = hr + int(mi) / 60
            d = (at - sim["hour"]) * 60
            if -45 <= d <= 120:
                out.append(f"\"{re.sub(r'^[^:]*:\\s*', '', t)[:90]}\" ({'in ' + mins_txt(d) if d > 5 else 'right about now' if d > -10 else mins_txt(-d) + ' ago'})")
                break
    return out[:2]


def build(c, user, st, hist, sim, amb, rp, p, turn, own, mode="story", grp=None, chron=None, uskills="", ugear="", wx=None, members=None, narrator=False, loc=None, doing=None):
    cfg = settings(p)
    doing = doing if isinstance(doing, dict) else {}
    name = c.get("name") or "Character"
    kinds_msg = next((m.get("content") for m in reversed(hist or []) if m.get("role") == "user"), "")
    mo = moment.read(kinds_msg) if kinds_msg else {"kinds": [], "words": 0, "shape": ""}
    cid = c.get("id") or name
    amb = amb or {}
    horror, tender = amb.get("horror", 0), amb.get("tender", 0)
    texts = [m.get("content") or "" for m in (hist or [])]
    lvl = tension.level(texts)
    place = (amb.get("place") or {}).get("name") if amb.get("place") else ""
    period = (sim or {}).get("period", "")
    w = (wx or {}).get("weather", "")
    info = {"on": cfg["on"], "clock": (sim or {}).get("clock", ""), "period": period, "day": (sim or {}).get("day", ""), "season": (wx or {}).get("season", ""),
            "weather": w, "wsrc": (wx or {}).get("src", ""), "trend": (wx or {}).get("trend", ""), "place": place, "indoors": amb.get("indoors"), "tension": lvl,
            "beat": "", "who": [], "real": bool((sim or {}).get("real"))}
    if loc:
        info["loc"] = {"id": loc["card"]["id"], "name": loc["card"]["name"]}
    if not cfg["on"]:
        return {"block": "", "compact": "", "tail": "", "plan": None, "info": info}
    roster = [c] + [m for m in (members or []) if m.get("id") != c.get("id") and m.get("id") != "__narrator__"]
    info["who"] = [s for s in (status(m, sim, cfg, doing.get(m.get("id"))) for m in roster) if s]
    dg = doing.get(cid) if (cfg["routines"] and not narrator) else None      # what the model says they are doing right now
    rt = routine.now(c, sim) if (cfg["routines"] and sim and not narrator and dg is None) else None
    if rt and not rt["own"]:
        rt = None       # a timetable guessed from the job (asleep at night, working by day) is not a fact about this person: only one the author wrote counts
    hour = (sim or {}).get("hour")
    L, C = [], []   # full block, compact block
    sad_or_hot = "sad" in mo["kinds"] or "hostile" in mo["kinds"]

    # ---- the beat of the world (texture) or a small thing from the character's own day
    skip = sad_or_hot or tender == 2 or lvl >= 2 or "bye" in mo["kinds"]
    bt = beats.beat(turn, cid, place, amb.get("indoors") is not False, period, w, horror, cfg["events"], skip)
    sd = "" if bt or skip or not (rt or dg) else beats.seed(turn, cid, rt["key"] if rt else "custom")
    info["beat"] = bt

    # ---- the location card this chat stands in: description, atmosphere, objects, exits, secrets, residents and its own events
    lp = places.parts(loc, CH, US, turn, cfg["events"], skip or narrator, narrator, doing) if loc else None
    if lp and lp["event"]:
        bt = sd = ""            # the card's own event takes the place of a generic small thing
        info["beat"] = ""

    # ---- wildlife: a real animal from data/animals/Animals.json, met where it really lives, played over a few messages
    enc = None
    if cfg["wildlife"] != "off" and mode not in ("text", "call"):
        scen = ((grp or {}).get("scenario") or c.get("scenario") or "") + (" " + places.climate_text(loc) if loc else "")     # the location card tells the animals where they are
        per = 2 if not grp else max(2, len([m for m in (members or [])]) + 1)
        enc = wildlife.encounter(int(turn) // per, str((grp or {}).get("id") or (grp or {}).get("name") or cid), [scen] + [re.sub(r"(?s)<think>.*?(?:</think>|$)", "", t) for t in texts[-6:]],
                                 place, amb.get("indoors"), period, cfg["wildlife"], cfg["scare"])
        if enc and enc["stage"] == 0 and (sad_or_hot or tender == 2 or lvl >= 2 or "bye" in mo["kinds"]):
            enc = None          # never starts in a grieving, tender or leave-taking moment, or on top of a fight (later stages stand on their own)
    if enc:
        bt = sd = ""
        info["beat"] = ""
        info["wild"] = wildlife.info(enc)
    wl = wildlife.words(enc, CH, US, narrator) if enc else None

    if narrator:
        L.append("[The world - what you may describe]")
        if sim:
            L.append(f"It is {sim['clock']}.")
        if w:
            L.append(f"Weather: {w}" + (f" ({wx['trend']})" if (wx or {}).get("trend") else "") + ". It changes how people feel and what they do.")
        if lp:
            L.extend(places.narrator_lines(loc, turn, doing, US))
        if info["who"] and not (lp and loc.get("people")):
            L.append("What everyone is doing: " + "; ".join(f"{s['name']}: {s['act']}" for s in info["who"] if s["name"] and s.get("here", True)) + ".")
        if bt:
            L.append(f"Let this small thing happen in the world during this message (texture, nothing anyone must answer): {bt}.")
        if wl:
            L.append(wl[0])
            L.append(wl[2])
        L.append("Time moves: show it in light, hunger, tiredness, crowds opening and closing, people leaving for where their day takes them.")
        return {"block": "\n".join(L), "compact": "\n".join(L[:3]), "tail": "", "plan": None, "info": info}

    L.append("[Daily life, time and world - keep the person real]")
    L.append(f"{CH} is a person with a day, a body and moods in a world that keeps moving. Whatever the story has already established always wins.")
    if lp:
        L.extend(lp["lines"])
        C.extend(lp["compact"])
    # ---- what they are doing now and the time
    in_place = bool(loc and loc.get("card"))
    if dg is not None:
        for ln in doing_mod.lines(dg, CH, US, in_place):
            L.append(ln)
            C.append(ln)
        if sim:
            L.append(f"The hour in the body: {world.bodyclock(hour, routine.chrono(c))}. (That is a tendency of the body, not a schedule: {CH} is not bound to sleep, work or eat by the clock.)")
    elif rt:        # the author's own written routine: their words, as a usual rhythm and never a rule
        daykind = "weekend" if rt["weekend"] else "weekday"
        if rt["state"] == "asleep":
            s = (f"It is a {daykind}. By the routine the author wrote, {CH} would usually be asleep about now. Whether they are is up to the scene: if the story shows {CH} up and active, "
                 f"keep that; if {US} woke them, show it in their own way.")
        elif rt["state"] == "groggy":
            s = f"It is a {daykind}. By the author's routine {CH} is usually just up and getting ready about now: slow, not fully awake."
        else:
            s = f"It is a {daykind}. {CH}'s usual rhythm right now, from the author's routine: {rt['label']}. {STATE_SENT(rt['state'], CH)}"
        L.append(s)
        C.append(s)
        if rt["state"] != "asleep" and rt["mins_left"] <= 45 and rt["next_key"] in COMMIT and rt["next_key"] != rt["key"]:
            s2 = (f"In {mins_txt(rt['mins_left'])} {CH}'s usual day moves on to: {rt['next']}. If it comes up naturally, mention it once; people have somewhere to be.")
            L.append(s2)
            C.append(s2)
        L.append(f"The hour in the body: {world.bodyclock(hour, routine.chrono(c))}.")
    elif sim:
        L.append(f"The hour in the body: {world.bodyclock(hour)}.")
    el = (sim or {}).get("elapsed", 0)
    if el >= 1200 and sim:
        L.append(f"{human(el)} of story time passed since the last message. Let it show (a different mood, something they did, a change of place) instead of resetting.")
    # ---- weather and what it does to this person
    if w:
        f = world.feel(c, w)
        if f:
            ws = f"Weather and {CH}: it leaves them {f['mood']}; it shows as {f['body']}."
            if f["note"]:
                ws += " " + f["note"].replace("the character", CH) + "."
            if rt and rt["key"] in ("commute", "errands", "exercise", "social") and f["plan"]:
                ws += f" Plans bend to it: {f['plan']}."
            L.append(ws)
            C.append(ws)
        if (wx or {}).get("src") == "dynamic":
            L.append(f"The weather today (the scene has not mentioned it yet; keep it the same all day): {w}" + (f". {wx['trend']}" if wx.get("trend") else "") +
                     f". Work it in naturally in this reply or soon (a glance outside, what they wear, a remark), then leave it in the background.")
    if (wx or {}).get("season"):
        L.append(f"Season: {wx['season']}. It colours clothes, light, food, daylight hours and small talk.")
    # ---- inner weather
    mood = (st or {}).get("mood") or ""
    en = (st or {}).get("energy") or ""
    L.append(f"Inner weather: {CH} is {mood or 'in an ordinary mood'}" + (f" with {en} energy" if en else "") + ". Feelings carry over and shift a little at a time with what happens (a good joke lifts a sour mood; a snub lingers). Show them through behaviour and word choice, never announce them. "
             f"Let {CH} be moved by small things (amused, embarrassed, irritated, wistful, jealous, proud, tender).")
    C.append(f"{CH} is {mood or 'in an ordinary mood'}; feelings carry over between messages and show in behaviour, not announcements.")
    hp = humor.profile(c)
    if hp["level"]:
        L.append(f"{CH}'s humour: {hp['how']}.")
    pl = plans(chron, sim)
    if pl:
        L.append("Coming up, from earlier in the story: " + "; ".join(pl) + ". Notice the time against it.")
    L.append(tension.standing(CH, US))
    C.append(tension.standing(CH, US))
    # ---- what to do on this very turn (rides in the private note: the strongest place)
    T = []
    ep = endings.plan(own, mo, turn, cid, CH, US, mode) if cfg["endings"] else None
    if ep:
        T.append(ep["rule"])
    if mo["shape"]:
        T.append(mo["shape"].replace("{CH}", CH).replace("{US}", US))
    hc = humor.cue(hp, CH, US, turn, cid, mo, mood, lvl, horror, tender, cfg["humor"], tired=bool((rt and rt["state"] in ("asleep", "groggy")) or (dg and dg.get("state") == "resting")))
    if hc:
        T.append(hc)
    if wl:
        L.append(wl[0])
        L.append(wl[1])
        C.append(wl[1])
        T.append(wl[2])
    if bt:
        T.append(f"A small thing happens in the world during this reply (texture only, nothing {US} must answer): {bt}. Work it into one detail if it suits the moment.")
    elif sd:
        T.append(f"If it comes up naturally, {CH} may mention something from their own day: {sd}.")
    if lp and lp["event"]:
        T.append(lp["event"])
    return {"block": "\n".join(L), "compact": "\n".join(["[Daily life]"] + C), "tail": " ".join(T), "plan": ep, "info": info}


def human(sec):
    m = int(sec // 60)
    return f"{m} minutes" if m < 90 else f"{round(m / 60)} hours"


def STATE_SENT(state, name):
    return {"busy": f"Their attention is partly on it: {name} can talk, but in short bursts, glancing at the time, now and then interrupted.",
            "moving": f"{name} is on the move, so talk happens in passing, a little distracted by the way, the crowd and whatever they are carrying.",
            "free": f"{name} has the time and headspace to talk properly.",
            "winding": f"{name} is slowing down: quieter, softer, more candid, the day finally off their shoulders."}.get(state, "")


def check(text, plan):
    return endings.check(text, plan)


def repair(text, plan):
    return endings.repair(text, plan)


def overview(members, hist, scenario, p, clock="", start="", notes=(), seed="", loc=None, doing=None):
    """Status for the page's World panel (no model call, nothing saved)."""
    from .. import simtime
    cfg = settings(p)
    full = (scenario or "") + (" " + start if start else "")
    sim = simtime.derive(hist or [], full, notes or []) or simtime.from_clock(clock)
    amb = ambience.derive(hist or [], full, list(notes or []) + ([places.note(loc)] if loc else []), sim)
    texts = [full] + [m.get("content") or "" for m in (hist or [])[-8:]]
    wx = sky(sim, amb, texts, seed or full[:200], cfg)
    c = (members or [{}])[0]
    out = build(c, "", {}, hist or [], sim, amb, {}, p, len(hist or []), [], members=members, wx=wx, loc=loc, doing=doing)
    info = out["info"]
    info.pop("wild", None)      # the page shows an encounter on the reply that tells it, never ahead of it
    info["clock_set"] = bool(sim)
    return info
