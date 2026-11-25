"""What people are doing right now: made up by the model from who they are and what is going on, never read off a timetable.

A fixed day (asleep at night, working 9 to 5) is wrong for most characters: a vigilante is out at night, a night-shift nurse is asleep at noon, a
king may be pacing the battlements at 3 AM. So the activity is generated for the moment, from the character sheet, the place, the weather and
hour, what the story has already shown and what the character was doing a little while ago. The same call decides who is at a place at all
(residents live or turn up there; they are not always in) and how each one reacts to the visitor walking in (nobody has to be friendly).

    ask(people, ...)                 -> the one message sent to the model (JSON out)
    parse(text, ids)                 -> {id: item}, items cleaned and bounded
    lines(item, CH, US)              -> the prompt lines for one character
    roster_lines(items, names, US)   -> who is here and who is not, for a place scene
    key(...)                         -> when the cached answer is still good (the page keeps it in the chat, so swipes and rewinds stay stable)

Item: {id, here, doing, state, free, stance, away, wants}. Nothing here calls the model itself: the server does, the page keeps the answer.
"""
import re
import zlib

STATES = {"free": .8, "busy": .3, "moving": .55, "resting": .12, "tense": .4}     # state -> how free to talk (0 .. 1)
HELD = 20            # turns an answer is kept before it is asked again
SPAN = 3.0           # story hours an answer is kept before it is asked again (what someone is doing does not change every few minutes)


def _s(x, n):
    return re.sub(r"\s+", " ", str(x or "")).strip()[:n]


def _bool(x, default=True):
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        return x.strip().lower() not in ("false", "no", "0", "away", "elsewhere", "out")
    return default if x is None else bool(x)


def clean(d, cid=""):
    """One item from whatever the model wrote (anything missing gets a calm default; nothing here asserts a schedule)."""
    d = d if isinstance(d, dict) else {}
    st = _s(d.get("state"), 12).lower()
    st = st if st in STATES else "free"
    here = _bool(d.get("here"), True)
    out = {"id": _s(d.get("id") or cid, 60), "here": here, "doing": _s(d.get("doing"), 200), "state": st, "free": STATES[st],
           "stance": _s(d.get("stance"), 220), "away": _s(d.get("away"), 160), "wants": _s(d.get("wants"), 160)}
    if not here:
        out["state"], out["free"] = "free", 0.0
    return out


def clean_map(x):
    """The page's {id: item} for what each person is doing right now, cleaned: the page is trusted with nothing but short plain text."""
    return {str(i): clean(d, str(i)) for i, d in list(x.items())[:16]} if isinstance(x, dict) else {}


def parse(text, ids):
    """{id: item} for the ids asked about. Accepts {"people": [...]}, a bare list, or {id: {...}}; unknown ids are dropped."""
    from ..textutil import loose_json
    ids = [str(i) for i in ids]
    try:
        data = loose_json(text)
    except Exception:
        return {}
    rows = data.get("people") if isinstance(data, dict) else data
    if rows is None and isinstance(data, dict):
        rows = [dict(v, id=k) for k, v in data.items() if isinstance(v, dict)]
    out = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        i = _s(r.get("id"), 60)
        if i not in ids:        # the model may write the name instead of the id
            i = next((x for x in ids if _s(r.get("name"), 60) and _s(r.get("name"), 60).lower() == x.lower()), i)
        if i in ids and i not in out:
            out[i] = clean(r, i)
    return out


def sheet(c, limit=450):
    """The part of a character sheet that tells the model who they are (no private fields, no model-written extras)."""
    bits = []
    for k, lab in (("occupation", "job"), ("description", ""), ("personality", "personality"), ("backstory", "background"), ("goals", "wants"),
                   ("flaws", "flaws"), ("routine", "the author's note on their usual rhythm (a hint, not a rule)")):
        v = _s(c.get(k), 240)
        if v:
            bits.append((f"{lab}: " if lab else "") + v)
    return _s("; ".join(bits), limit)


def ask(people, place=None, sim=None, weather="", recent=(), scene="", prev=None, visitor="the visitor", arriving=False, setting=""):
    """The message for the model. people: [character dicts]. place: a place card or None. recent: the last few lines of the story."""
    when = (sim or {}).get("clock") or "an unknown time"
    where = ""
    if place:
        where = (f"PLACE: {place['name']}" + (f" ({place['biome']})" if place.get("biome") else "") + f". {_s(place.get('description'), 400)} "
                 f"{_s(place.get('atmosphere'), 200)}").strip()
    elif setting:       # no place card, but the story has a place: it is where everybody is
        where = f"PLACE: {_s(setting, 80)}."
    rows = []
    for c in people:
        pv = (prev or {}).get(c.get("id")) or {}
        was = f" A little while ago: {pv['doing']}." if pv.get("doing") else ""
        rows.append(f"- id {c.get('id')}, {c.get('name')}: {sheet(c)}{was}")
    rules = [
        "You are the world simulator for a roleplay. For each person below decide what they are doing RIGHT NOW"
        + (", and whether they are at the place at all." if place else "."),
        "Decide from who they are, what the story has already shown, the hour and the weather. There is no timetable: nobody sleeps because it is night, "
        "nobody works because it is day. Night-shift workers, vigilantes, soldiers on watch, insomniacs, scholars, thieves, monsters and the sleepless are "
        "up and busy when it suits them; ordinary people may be asleep, or may not be. Pick the specific, characteristic thing, not the most generic one, "
        "and do not give everyone the same kind of activity.",
        "Anything the story or the scene already established about a person wins over your guess.",
    ]
    if place:
        rules.append("People who live or work at the place are often there, but not always: some are out, on an errand, on a job, asleep elsewhere, or simply "
                     "not around. It is fine if only one person is here, or nobody. Say where an absent person is instead in \"away\".")
    if place or setting:
        rules.append("Everyone who is here is at PLACE, so what they are doing has to be something that can happen THERE. Never set an activity in another location "
                     "(a home, an apartment, a shop, a bedroom) unless that is what PLACE is. If a person would be somewhere else, they are not here: set here=false and say "
                     "where they are in \"away\". 'A little while ago' may describe another place the story has since left: do not carry it over unless it still fits PLACE.")
    rules.append(f"\"stance\" is how this person reacts to {visitor} turning up or speaking to them, in one short sentence, true to their temperament and to what "
                 "they are doing: they might ignore them, size them up, be curt, wary, amused, hostile, shy, bored, curious or genuinely warm. They are NOT service "
                 "staff and NOT an assistant: nobody asks how they can help unless that is literally their job, and even then they talk like a real person.")
    if arriving:
        rules.append(f"{visitor} has just arrived; say what each person is in the middle of and whether they have noticed.")
    fmt = ('Reply with ONLY a JSON object: {"people":[{"id":"<id>","here":true|false,"doing":"<what they are doing now, present tense, under 25 words>",'
           '"state":"free|busy|moving|resting|tense","stance":"<reaction to the visitor>","away":"<where they are instead, only if not here>",'
           '"wants":"<optional: what they would like right now, under 12 words>"}]} with one entry per person, in the same order.')
    ctx = [f"TIME: {when}."]
    if weather:
        ctx.append(f"WEATHER: {_s(weather, 80)}.")
    if where:
        ctx.append(where)
    if scene:
        ctx.append(f"SCENE NOTE: {_s(scene, 300)}")
    if recent:
        ctx.append("WHAT HAS HAPPENED LATELY:\n" + "\n".join(f"  {_s(x, 200)}" for x in list(recent)[-4:]))
    return "\n".join(rules) + "\n\n" + "\n".join(ctx) + "\n\nPEOPLE:\n" + "\n".join(rows) + "\n\n" + fmt


def key(place_id, sim, turn, scene=""):
    """A cache key: the same place, the same stretch of story time and the same scene note mean the answer still stands."""
    h = (sim or {}).get("hour")
    slot = f"{int(float(h) // SPAN)}" if h is not None else "x"
    d = (sim or {}).get("dayn")
    return f"{place_id or '-'}|{d if d is not None else '-'}|{slot}|{zlib.crc32(scene.encode()) % 9973 if scene else 0}"


def stale(entry, place_id, sim, turn, scene=""):
    """True when the page should ask again: no answer yet, a new stretch of time, another place, a changed scene note, or a long time in turns."""
    if not entry:
        return True
    if entry.get("key") != key(place_id, sim, turn, scene):
        return True
    return turn - int(entry.get("turn") or 0) >= HELD


# ---------------------------------------------------------------- for the prompt

def lines(it, CH, US, in_place=False):
    """The prompt lines for one character: what they are doing and how they carry themselves, as a fact of the scene (not a rule to announce)."""
    if not it or not it.get("here", True):
        return []
    out = []
    if it.get("doing"):
        out.append(f"Right now {CH} is: {it['doing']}. This is what {CH} was doing when {US} came along; the story's own facts still win, and "
                   f"{CH} does not have to drop everything for {US}.")
    st = it.get("state")
    if st == "resting":
        out.append(f"{CH} is resting or half-asleep: slow, short, maybe annoyed to be bothered, or glad of the company, as {CH} would be.")
    elif st == "busy":
        out.append(f"{CH}'s attention is partly on what they are doing: they can talk, in short bursts, without stopping their work.")
    elif st == "moving":
        out.append(f"{CH} is on the move and talks in passing.")
    elif st == "tense":
        out.append(f"{CH} is alert and on edge, not relaxed.")
    if it.get("stance"):
        out.append(f"How {CH} meets {US}: {it['stance']} Stay with that until something in the scene changes it; being friendly is not the default.")
    if in_place:
        out.append(f"{CH} has a life here and their own business. {CH} does not greet {US} like staff and does not offer help, ask what {US} wants "
                   f"or what brings {US} here unless it fits who {CH} is.")
    if it.get("wants"):
        out.append(f"{CH} would quite like: {it['wants']}.")
    return out


def roster_lines(items, names, US):
    """For a place scene: who is around and what each is doing, and who is not. items: {id: item}, names: {id: name}."""
    here = [f"{names.get(i, i)}: {it['doing'] or 'around'}" for i, it in items.items() if it.get("here")]
    gone = [f"{names.get(i, i)} ({it['away']})" if it.get("away") else names.get(i, i) for i, it in items.items() if not it.get("here")]
    out = []
    if here:
        out.append("Here right now (each in the middle of their own business): " + "; ".join(here) + ".")
    else:
        out.append(f"Nobody who belongs here is around at the moment. {US} may be alone in the place.")
    if gone:
        out.append("Not here at the moment (they cannot speak or act in the scene; do not bring them in unless the story clearly does): " + "; ".join(gone) + ".")
    return out


def label(it):
    """The short phrase the page shows next to a name."""
    if not it:
        return ""
    if not it.get("here", True):
        return it.get("away") or "not here"
    return it.get("doing") or ""


def fallback(ids, seed="", place=True):
    """When the model gives nothing usable: no invented activity. In a place, about half of the cast is in (never nobody while someone lives there),
    chosen from the seed so the same visit gives the same answer; the rest are simply not around."""
    ids = list(ids)
    if not place:
        return {i: clean({"id": i, "here": True}, i) for i in ids}
    order = sorted(ids, key=lambda i: zlib.crc32(f"{seed}:{i}".encode()))
    n = max(1, (len(ids) + 1) // 2) if ids else 0
    here = set(order[:n])
    return {i: clean({"id": i, "here": i in here}, i) for i in ids}


def pick(ids, seed, limit):
    """At most `limit` people to ask about, rotating with the seed so a big cast all gets a turn over a long visit; the rest are left alone."""
    ids = list(dict.fromkeys(ids))
    if len(ids) <= limit:
        return ids
    return sorted(ids, key=lambda i: zlib.crc32(f"{seed}:{i}".encode()))[:limit]
