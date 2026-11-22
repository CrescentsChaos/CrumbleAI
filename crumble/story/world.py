"""The world around the story: the season, the day's weather (when the story has not set one) and what weather and the time of day do to a person.

The story always wins: weather the scene has established (ambience.derive reads it from the chat) is kept. When the scene never said, the day gets
a weather of its own, chosen from the season by a fixed seed (the same chat and the same story day always give the same sky), that builds over the
day ("clouds gathering, rain by mid-afternoon") instead of flipping between messages.

    season(sim, texts)                       'winter' | 'spring' | 'summer' | 'autumn' | ''
    forecast(sim, seasn, seed)               {'now': key, 'next': (key, hours) or None, 'season': ...}
    feel(c, weather)                         how THIS person takes this weather (their likes, fears and temperament count)
    bodyclock(hour, chrono)                  what the time of day does to a body: hunger, slump, late-night looseness
Pure functions; weather keys are the ones ambience.py uses (rain storm snow fog wind hot cold clear overcast).
"""
import re
import zlib

SEASON_WORDS = [
    ("winter", r"\b(?:winter|christmas|frost\w*|december|january|february|blizzard|new year'?s)\b"),
    ("spring", r"\b(?:spring(?!\s+(?:water|roll|break))|blossoms?|sakura|april|easter)\b"),
    ("summer", r"\b(?:summer\w*|june|july|august|heat ?wave|midsummer)\b"),
    ("autumn", r"\b(?:autumn|harvest|halloween|september|october|november|falling leaves|fall foliage)\b"),
]
PLANS = {
    "winter": [[(0, "cold")], [(0, "overcast")], [(0, "snow")], [(0, "fog"), (10, "overcast")], [(0, "clear"), (15, "cold")], [(0, "overcast"), (14, "snow")]],
    "spring": [[(0, "clear")], [(0, "overcast"), (14, "rain")], [(0, "rain"), (13, "clear")], [(0, "fog"), (9, "clear")], [(0, "wind")], [(0, "clear"), (16, "overcast")]],
    "summer": [[(0, "clear")], [(0, "hot")], [(0, "clear"), (15, "storm")], [(0, "hot"), (17, "storm")], [(0, "clear")], [(0, "overcast"), (13, "clear")], [(0, "rain")]],
    "autumn": [[(0, "overcast")], [(0, "wind")], [(0, "rain")], [(0, "fog"), (10, "overcast")], [(0, "clear"), (15, "wind")], [(0, "overcast"), (15, "rain")]],
    "": [[(0, "clear")], [(0, "overcast")], [(0, "overcast"), (14, "rain")], [(0, "fog"), (10, "clear")], [(0, "wind")], [(0, "rain"), (13, "overcast")], [(0, "clear"), (16, "overcast")]],
}
BUILD = {"rain": "clouds are thickening and the air smells of rain", "storm": "the air is heavy and a storm is building", "snow": "the sky has gone low and white, snow is coming",
         "fog": "a mist is rolling in", "wind": "the wind is picking up", "hot": "the heat is climbing", "cold": "the temperature is dropping", "clear": "the sky is opening up",
         "overcast": "clouds are covering the sky"}
EFFECT = {   # mood tilt, what it looks like in the body and behaviour, what it changes about plans
    "rain": ("cosy, a little wistful or sleepy", "a hood or coat pulled tighter, wet shoes, a longing for something warm to drink, the drumming noticed in a pause", "outdoor plans get shorter, umbrellas appear, travel is slower"),
    "storm": ("jumpy and on edge, thrilled or frightened depending on the person", "a flinch at thunder, a look at the window, a louder voice to be heard, lights checked", "people stay in, travel is delayed, the power may flicker"),
    "snow": ("hushed, delighted, a little giddy", "breath clouding, stamping boots, flakes brushed off, hands in sleeves", "everything starts late and moves slowly, travel is a chore"),
    "fog": ("uneasy, muffled and inward", "squinting, staying closer to others, sounds taken for something else", "visibility is short, travel is careful and slow"),
    "wind": ("restless and a little frayed", "hair whipped about, a hand holding something down, a raised voice", "hats and scarves, loose things chased, doors that bang"),
    "hot": ("sluggish, thirsty and short of patience", "a hand fanning, sleeves rolled, a search for shade or a cold drink, slower speech", "exertion is avoided, breaks run long, light clothes"),
    "cold": ("hunched, brisk and craving warmth", "rubbing hands, blowing on fingers, a hot drink held with both hands", "layers, short trips outside, heaters on"),
    "clear": ("lighter, more energetic and more sociable", "squinting, sunglasses, a wish to be outside", "a good day to go out"),
    "overcast": ("a little flat and subdued", "lamps on early, a slow start, a sky that might break any time", ""),
}
WORD = {"rain": "rain", "rainy": "rain", "storm": "storm", "storms": "storm", "thunder": "storm", "thunderstorm": "storm", "snow": "snow", "winter": "cold",
        "fog": "fog", "mist": "fog", "heat": "hot", "summer": "hot", "hot": "hot", "sun": "clear", "sunshine": "clear", "sunny": "clear", "cold": "cold",
        "wind": "wind", "windy": "wind", "clouds": "overcast", "cloudy": "overcast", "overcast": "overcast"}
_W = r"(rain\w*|storms?|thunder\w*|snow\w*|winter|fog\w*|mist\w*|heat|summer|hot|sun(?:ny|shine)?|cold|wind\w*|clou\w+|overcast)"
LOVES = re.compile(r"(?i)\b(?:love[sd]?|likes?|enjoys?|adores?|favou?rite|fond of|cosy|cozy|thrives?|energi[sz]ed by|calmed by)\b[^.;\n]{0,32}?\b" + _W)
HATES = re.compile(r"(?i)\b(?:hates?|dislikes?|can'?t stand|loathes?|detests?|afraid of|scared of|fears?|terrified of|phobi\w+|allergic to|dreads?|misses?|struggles? (?:with|in)|suffers? (?:in|from))\b[^.;\n]{0,32}?\b" + _W)


def season(sim, texts=()):
    if sim and sim.get("season"):
        return sim["season"]
    best, at = "", -1
    # the latest mention wins, so a story that moves from autumn to winter follows it
    joined = " \n ".join(t or "" for t in texts)
    for name, rx in SEASON_WORDS:
        for m in re.finditer(rx, joined, re.I):
            if m.start() >= at:
                best, at = name, m.start()
    return best


def _seed(seed, dayn):
    return zlib.crc32(f"{seed}|{int(dayn or 0)}".encode("utf-8", "ignore"))


def forecast(sim, seasn="", seed=""):
    if not sim:
        return None
    plan = PLANS.get(seasn, PLANS[""])[_seed(seed, sim.get("dayn")) % len(PLANS.get(seasn, PLANS[""]))]
    h = sim["hour"]
    now, nxt = plan[0][1], None
    for i, (fh, key) in enumerate(plan):
        if h >= fh:
            now = key
            nxt = (plan[i + 1][1], plan[i + 1][0] - h) if i + 1 < len(plan) else None
    return {"now": now, "next": nxt if nxt and nxt[1] <= 3 else None, "season": seasn}


def trend(fc):
    if not fc or not fc.get("next"):
        return ""
    k, hrs = fc["next"]
    when = "within the hour" if hrs <= 1 else "in a couple of hours" if hrs <= 2.5 else "in about three hours"
    return f"{BUILD.get(k, 'the weather is turning')}; {k} {when}"


def prefs(c):
    blob = " ".join(str(c.get(k) or "") for k in ("weather_pref", "likes", "dislikes", "fears", "comfort", "quirks", "personality", "triggers", "backstory"))[:2400]
    love, hate = set(), set()
    for m in LOVES.finditer(blob):
        k = WORD.get(m.group(1).lower().rstrip("s") if m.group(1).lower() not in WORD else m.group(1).lower())
        if k is None:
            k = next((v for w, v in WORD.items() if m.group(1).lower().startswith(w)), None)
        if k:
            love.add(k)
    for m in HATES.finditer(blob):
        k = WORD.get(m.group(1).lower())
        if k is None:
            k = next((v for w, v in WORD.items() if m.group(1).lower().startswith(w)), None)
        if k:
            hate.add(k)
    return love - hate, hate


def feel(c, w, name="the character"):
    """How this person takes this weather. Returns (mood tilt, behaviour, plans, personal note)."""
    e = EFFECT.get(w)
    if not e:
        return None
    love, hate = prefs(c)
    note = ""
    if w in hate:
        note = f"{name} dislikes or fears this weather: it wears on them, they are tenser, shorter, and keep glancing at it"
    elif w in love:
        note = f"{name} loves this weather: it visibly lifts them, they linger in it and bring it up"
    return {"mood": e[0], "body": e[1], "plan": e[2], "note": note, "love": w in love, "hate": w in hate}


def bodyclock(hour, shift=0.0):
    """What the hour does to a body, as a short phrase (shift: hours a night owl (+) or early bird (-) is offset)."""
    h = (hour - shift * .5) % 24
    if 4 <= h < 6.5:
        return "it is barely dawn: bleary, voice rough, no patience yet for anything that needs thinking"
    if 6.5 <= h < 9:
        return "early in the day: still waking up, coffee-minded, thoughts on what the day holds"
    if 9 <= h < 11.5:
        return "mid-morning: the sharpest part of the day, brisk and focused"
    if 11.5 <= h < 13.5:
        return "around lunchtime: hungry, food on the mind, and a little easily distracted by it"
    if 13.5 <= h < 16:
        return "the afternoon slump: attention drifts, a yawn is never far, a snack or a coffee would help"
    if 16 <= h < 18:
        return "late afternoon: the day is wearing thin, a wish for it to be over, or a second wind"
    if 18 <= h < 20:
        return "dinner time: hungry, the day's tension easing, a mood for company and food"
    if 20 <= h < 22.5:
        return "evening: relaxed and open, more candid than during the day"
    if 22.5 <= h or h < 1:
        return "late: tired and softened, thoughts looser, a little more honest and a little less guarded"
    return "the small hours: should be asleep; bleary, loopy or philosophical, with very little filter and very little energy"
