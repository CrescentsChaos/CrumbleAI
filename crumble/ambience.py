"""Environmental awareness. The scene has a place, weather, light and a mood, and they stay true until the story changes them.

Like the identity ledger and the story clock, everything is DERIVED from the whole chat every turn (scenario, messages, the
author's setting notes), so edits, swipes and rewinds can never leave it stale.

    derive(messages, scenario='', notes=(), sim=None) -> dict, always (fields may be empty):
        place   {'name','indoors','sense'} or None      weather 'rain' | 'storm' | 'snow' | 'fog' | 'wind' | 'hot' | 'cold' | 'clear' | 'overcast' | ''
        indoors bool | None      horror 0-2 (0 none, 1 uneasy, 2 full horror)      tender 0-2 (0 none, 1 warm, 2 intimate)
    block(amb, char, user, sim)   the prompt block: what is true about the scene and how to make it felt (sound, smell, touch, light)
    env_note(text, amb, sim)      a retry note when a reply breaks the scene (rain indoors, sunshine in a storm, jokes in a horror beat) else ''
    boost(amb)                    how much extra room (x1.0-1.3) the reply gets so atmosphere is not squeezed out by the word limit
Pure functions, no imports from the rest of the package. The intimacy CEILING (fade/suggestive/moderate/explicit) is set elsewhere
and always wins; this module only makes whatever is written feel physical, grounded and emotionally real."""
import re

# (name, regex, indoors, what you hear / smell / feel / see there)
PLACES = [
    ("the library", r"library|reading room|bookshelves", True, "hush, pages turning, a distant cough, soft footsteps on carpet; old paper and floor polish; the hum of strip lights"),
    ("the classroom", r"classroom|lecture hall|lecture theat|seminar room", True, "chairs scraping, chalk or marker squeak, murmuring; whiteboard marker and floor wax; hard seats"),
    ("the university campus", r"campus|quad\b|courtyard", False, "students passing, bikes, distant bells; cut grass, coffee carts; open sky overhead"),
    ("the bedroom", r"bedroom|\bhis room\b|\bher room\b|\bmy room\b|\byour room\b", True, "a quiet room, fabric rustling, the building settling; clean sheets, skin and soap; lamplight or window light"),
    ("the kitchen", r"kitchen", True, "kettle, fridge hum, cutlery; coffee, toast, something on the stove; warm tiles"),
    ("the living room", r"living room|lounge|sofa|couch", True, "a TV murmuring or silence, cushions shifting; the faint smell of a lived-in home; soft light"),
    ("the bathroom", r"bathroom|shower room", True, "water in pipes, echo off tile; steam, soap; damp warmth"),
    ("the café", r"caf[eé]|coffee shop|coffee house", True, "milk steamers, cups clinking, low chatter; roasted coffee, sugar; warm bright windows"),
    ("the apartment", r"apartment|flat\b|dorm\b|dormitory", True, "thin walls, pipes, neighbours; stale air, laundry; a small cramped space"),
    ("the hallway", r"hallway|corridor|stairwell|staircase", True, "echoing footsteps, doors, a buzzing light; disinfectant, dust; narrow walls"),
    ("the basement", r"basement|cellar|crypt", True, "dripping water, a boiler groaning, silence pressing in; damp concrete, mould; cold, low ceiling, little light"),
    ("the attic", r"attic|loft\b", True, "wood creaking, wind in the eaves, scurrying; dust, old cardboard; stuffy heat or draughts"),
    ("the old house", r"haunted house|abandoned house|old house|mansion|manor|asylum|hospital ward", True, "floorboards groaning, doors shifting on their own, wind in the walls; mould, cold dust; flat cold air, deep shadows"),
    ("the cabin", r"cabin|cottage|hut\b", True, "a fire crackling or silence, timber ticking, wind and rain on the roof; woodsmoke, damp wool; draughty corners"),
    ("the car", r"\bcar\b|\btaxi\b|\bcab\b|backseat|passenger seat", True, "engine hum, tyres on the road, indicator ticking; upholstery, air freshener; close, enclosed space"),
    ("the train", r"\btrain\b|subway|metro\b|\bbus\b", True, "rails rhythm, announcements, doors hissing; metal and people; sway and vibration"),
    ("the street", r"\bstreet\b|sidewalk|pavement|crosswalk|alley", False, "traffic, footsteps, voices from windows; exhaust, food stalls; wind between buildings"),
    ("the park", r"\bpark\b|garden|bench\b|playground", False, "birds, leaves, distant children; cut grass, earth; open air"),
    ("the forest", r"forest|woods\b|woodland|trail\b|\bpath through", False, "branches creaking, leaves, something small moving unseen; pine, damp earth; uneven ground, filtered light"),
    ("the beach", r"beach|shore\b|seaside|\bdock\b|pier\b", False, "waves, gulls, wind; salt, seaweed; sand underfoot"),
    ("the rooftop", r"rooftop|roof\b|balcony|terrace", False, "wind, the city far below; cold metal rails; open sky"),
    ("the graveyard", r"graveyard|cemetery|tomb|mausoleum", False, "wind through stone, a distant bird, nothing else; wet earth, old stone; uneven ground, mist"),
    ("the restaurant", r"restaurant|diner\b|bar\b|pub\b|canteen|cafeteria", True, "cutlery, chatter, a kitchen clatter; food, spice, beer; crowded warmth"),
    ("the shop", r"shop\b|store\b|supermarket|mall\b|market\b", True, "tills beeping, music, trolleys; packaging, bakery; harsh lights"),
    ("the gym", r"\bgym\b|sports hall|pool\b", True, "weights clanking, shoes squeaking; rubber, chlorine; heat and effort"),
]
OUTSIDE = re.compile(r"(?i)\b(?:step(?:s|ped|ping)?|walk(?:s|ed|ing)?|head(?:s|ed|ing)?|go(?:es)?|went|run(?:s|ning)?|ran)\s+(?:back\s+)?(?:out(?:side)?|into the (?:rain|snow|storm|cold|night|fog))\b|\bout\s+the\s+door\b")
INSIDE = re.compile(r"(?i)\b(?:step(?:s|ped)?|come|came|duck(?:s|ed)?|run(?:s)?|ran|go(?:es)?|went|get(?:s)?|got)\s+(?:back\s+)?(?:inside|indoors)\b|\binto the (?:house|building|shelter|shop|café|cafe)\b")

# (key, regex, outdoors guidance, indoors guidance)
WEATHER = [
    ("storm", r"thunder|lightning|\bstorm(?:y|ing|s)?\b|\bgale\b|tempest",
     "thunder arrives AFTER the lightning, close ones crack and rattle the chest; wind slaps rain sideways, umbrellas fail, everyone is soaked through, voices are shouted, light is green-grey",
     "thunder rattles the windows, lightning flashes white across walls, rain drums hard on the roof, lights may flicker, the power can fail"),
    ("rain", r"\brain(?:ing|s|ed|y)?\b|drizzl\w*|downpour|\bwet weather\b",
     "rain on skin, cold drops down the collar, hair and clothes darkening and clinging, wet shoes squelching, puddles and splashing tyres, the smell of wet earth and tarmac, everything muted by the hiss of rain",
     "rain ticking on glass and roof, a steady soft drumming under the quiet, streaked windows, a damp coat by the door, a cosier, closer-feeling room, gloomy light"),
    ("snow", r"\bsnow(?:ing|s|y|fall|flakes?)?\b|blizzard|flurr\w*|\bsleet\b",
     "a muffled hush, crunching footsteps, breath clouding, numb fingers and a red nose, flakes catching in hair and lashes, bright pale light",
     "window glow on white, a muffled hush outside, cold seeping from the glass, warmth of heating and blankets"),
    ("fog", r"\bfog(?:gy)?\b|\bmist(?:y)?\b|\bhaze\b",
     "visibility a few metres, shapes appearing late, sounds carrying oddly and seeming to come from the wrong place, damp on skin, sodden cold, everything greyed and flat",
     "pale blank windows, the world outside gone, sounds from outside strangely close"),
    ("wind", r"\bwindy\b|\bgusts?\b|\bbreezy\b|strong wind",
     "hair and clothes whipped about, flapping fabric, eyes watering, hard to be heard, loose things clattering",
     "wind pressing at the walls, a whistle at a window gap, doors that shudder, a draught"),
    ("hot", r"heat\s?wave|scorching|sweltering|\bhumid\b|blistering heat|baking hot",
     "heavy air, sweat on the back of the neck, squinting in glare, sticky clothes, seeking shade and water, slowed movement and short tempers",
     "stuffy air, sticky skin, fans whirring, a glass sweating on the table, windows open, drowsiness"),
    ("cold", r"\bfreezing\b|\bfrost(?:y|ed)?\b|bitter cold|icy wind|\bchilly\b",
     "stiff fingers, breath fogging, shivers, hunched shoulders, hands tucked in sleeves, cheeks stinging",
     "cold floors and glass, hands round a warm mug, layers, a heater ticking"),
    ("clear", r"\bsunny\b|sunshine|clear sky|cloudless|blue sky|bright sun|sun(?:light)? streaming",
     "warm sun on the skin, squinting, shadows sharp and short, heat on pavement, a bright high sky",
     "bright light across the floor, dust in sunbeams, the room warm, the curtains glowing"),
    ("overcast", r"overcast|cloudy|grey sky|gray sky|grey light|gloomy sky",
     "flat grey light, no shadows, a damp-smelling stillness, a sky that might break at any time",
     "flat grey light at the windows, lamps on in the daytime, a subdued mood"),
]
WEATHER_STOP = re.compile(r"(?i)\b(?:rain|storm|snow(?:fall)?|fog|mist|wind|sleet|drizzle)\s+(?:has\s+|had\s+)?(?:stops|stopped|ceases|ceased|cleared|clears|lets?\s+up|let\s+up|eases|eased|passes|passed)\b|"
                          r"\bsky\s+(?:clears|cleared)\b|\bclouds\s+(?:part|parted|break|broke)\b|\bsun\s+(?:comes|came|breaks|broke)\s+out\b|\bno\s+longer\s+(?:raining|snowing)\b")
NEG = re.compile(r"(?i)(?:\bno|\bnot|n't|\bwithout|\bnever|\bhoping for|\bif it|\bwish(?:ed)? it)\W+(?:\w+\W+){0,2}$")

HORROR2 = r"horror|ghost|haunt\w*|corpse|killer|monster|demon|scream\w*|blood\w*|eerie|dread|terror|lurk\w*|creepy|slaughter|undead|zombie|possess\w*|stalk\w*|something\s+(?:is\s+)?(?:watching|behind|following)"
HORROR1 = r"shadows?|flicker\w*|creak\w*|whisper\w*|abandoned|darkness|pitch[- ]black|afraid|scared|trembl\w*|cold sweat|dead\b|silence|goosebumps|chill\w*|knock\w*|footsteps"
TENDER2 = r"kiss\w*|caress\w*|embrac\w*|cuddl\w*|lips|nuzzl\w*|undress\w*|bed\b|lap\b|pulled? (?:her|him|me|you) close|naked|breathless"
TENDER1 = r"hug\w*|blush\w*|heartbeat|pulse|touch\w*|fingers|lean\w*\s+(?:in|closer)|closer|warmth|cheek|waist|neck|whisper\w*|love\b|hold\w*\s+(?:her|his|your|my)\s+hand|eye contact|gaze\w*"
RECENT = 8


def _strip(t):
    return re.sub(r"<think>.*?(?:</think>|$)", "", t or "", flags=re.S)


def _weather_events(text):
    """[(pos, key)] in order; 'clear' is also the result of a stop phrase."""
    ev = []
    for key, rx, *_ in WEATHER:
        for m in re.finditer(rx, text, re.I):
            if NEG.search(text[max(0, m.start() - 24):m.start()]):
                continue
            ev.append((m.start(), key))
    for m in WEATHER_STOP.finditer(text):
        ev.append((m.start(), "clear"))
    return sorted(ev)


def _score(text, strong, weak):
    return 2 * len(re.findall(strong, text, re.I)) + len(re.findall(weak, text, re.I))


def derive(messages, scenario="", notes=(), sim=None):
    texts = [("scenario", _strip(scenario))] + [(m.get("role"), _strip(m.get("content"))) for m in (messages or []) if (m.get("content") or "").strip()]
    texts += [("note", n.get("text", "")) for n in (notes or []) if n.get("kind") in ("setting", "direct", "correct") or not n.get("kind")]
    place, indoors, weather = None, None, ""
    for _, t in texts:
        marks = []
        for name, rx, ind, sense in PLACES:
            for m in re.finditer(rx, t, re.I):
                marks.append((m.start(), "place", (name, ind, sense)))
        for m in OUTSIDE.finditer(t):
            marks.append((m.start(), "out", None))
        for m in INSIDE.finditer(t):
            marks.append((m.start(), "in", None))
        for pos, key in _weather_events(t):
            marks.append((pos, "weather", key))
        for _, kind, val in sorted(marks, key=lambda x: x[0]):
            if kind == "place":
                place, indoors = {"name": val[0], "indoors": val[1], "sense": val[2]}, val[1]
            elif kind == "out":
                indoors = False
            elif kind == "in":
                indoors = True
            else:
                weather = val
    # mood from the most recent messages (later = heavier), plus genre words in the scenario
    recent = [t for r, t in texts if r in ("user", "assistant")][-RECENT:]
    sc = _strip(scenario)
    h = sum((i + 1) / len(recent) * _score(t, HORROR2, HORROR1) for i, t in enumerate(recent)) if recent else 0
    h += 3 * len(re.findall(r"horror|haunt|creepy|ghost|slasher|supernatural thriller", sc, re.I))
    tn = sum((i + 1) / len(recent) * _score(t, TENDER2, TENDER1) for i, t in enumerate(recent)) if recent else 0
    tn += 2 * len(re.findall(r"romance|romantic|lovers|dating|couple", sc, re.I))
    return {"place": place, "indoors": indoors, "weather": weather,
            "horror": 2 if h >= 4 else 1 if h >= 2 else 0, "tender": 2 if tn >= 5 else 1 if tn >= 2.5 else 0,
            "night": bool(sim and sim.get("night"))}


def boost(amb):
    """Room for atmosphere: a horror beat or a tender one is not squeezed into the same two lines as small talk."""
    return 1.3 if (amb.get("horror") == 2 or amb.get("tender") == 2) else 1.15 if (amb.get("horror") or amb.get("tender")) else 1.0


def block(amb, char="the character", user="the other person", sim=None):
    L = ["[Environment - keep it real and consistent]"]
    L.append("Whatever the scene has established (place, weather, light, temperature, objects, who is around, what anyone is wearing or injured by) stays true until the story changes it. "
             "Nothing appears or vanishes without a reason: no rain that comes and goes between messages, no extra people, no lights that change by themselves.")
    p, w, ind = amb.get("place"), amb.get("weather"), amb.get("indoors")
    if p:
        L.append(f"Place: {p['name']} ({'indoors' if ind else 'outdoors'}). What belongs here - hear, smell, feel, see: {p['sense']}. "
                 f"Pick one or two of these per reply, vary them, and fold them into what {char} does and notices; never list them.")
    if w:
        g = next((x for x in WEATHER if x[0] == w), None)
        if g:
            if ind is False or (ind is None and not p):
                L.append(f"Weather: {w}. Outdoors it is felt in the body: {g[2]}.")
            else:
                L.append(f"Weather: {w}, outside. {char} is indoors, so the weather is heard and seen, not felt on the skin: {g[3]}. "
                         f"Nobody is wet or windblown unless they just came in from it.")
            L.append("Weather has physics: it follows its own logic, it does not change on a whim, and it affects what people say, wear, want and do.")
    if sim:
        L.append("Light follows the story clock: " + ("sunlight, shadows and open shops by day." if sim.get("daytime") else "darkness and artificial light, quiet streets and tired people at night." if sim.get("night") else "low light, long shadows, lamps coming on."))
    if amb.get("horror"):
        full = amb["horror"] == 2
        L.append(f"TONE - {'HORROR' if full else 'UNEASE'}. The scene must be genuinely frightening, so write dread, not spectacle: "
                 "slow the pace and shorten the sentences; use silence, the sound that stops, a smell that does not belong, a cold spot, something moved that was not touched, a light that flickers; "
                 "show the threat late, partly and never explain it; let small wrong details accumulate before anything happens. "
                 f"{char} reacts like a real frightened person with a body (pulse in the ears, dry mouth, cold sweat, shallow breath, trembling hands, freezing or bolting) and does not calm down or crack jokes at once "
                 f"unless that is {char}'s own way of coping, and then it should sound brittle. Do not break the mood with cheerful or comic asides, and do not let {char} suddenly feel safe without cause."
                 + (" Darkness is real: flashlight beams show only a circle, edges stay black, sounds seem to come from every direction." if amb.get("night") else ""))
    if amb.get("tender"):
        deep = amb["tender"] == 2
        L.append(f"TONE - {'INTIMACY' if deep else 'WARMTH AND CLOSENESS'}. Make closeness feel real and unhurried: anchor it in the body and the senses (warmth of skin, breath, heartbeat, the weight of a hand, the pause before a touch, "
                 "eyes that look away and come back), in hesitation and small vulnerable details, and in the setting itself (the rain on the window, the quiet room, the risk of being interrupted). "
                 f"{char} reacts as {char} specifically would, at the pace the relationship and the other person's signals allow; consent and mutual pacing are visible, nothing is rushed or one-sided. "
                 f"Write {char}'s side only and leave {user} room to answer. How explicit it may become is set by the intimacy ceiling above, and it always wins; if the ceiling is lower, imply and cut away gracefully instead.")
    return "\n".join(L)


_INDOOR_BODY = re.compile(r"(?i)\b(?:soaked|drenched|rain\s+(?:soaks?|drenches|lashes|stings|pelts)|rain(?:drops?)?\s+(?:on|run|trickle|fall|hit|sting)\w*|snowflakes?\s+(?:land|settle|melt)\w*|wind\s+(?:whips?|tugs?|tears?)\w*|wet\s+hair\s+from\s+the\s+rain)\b")
_SUN = re.compile(r"(?i)\b(?:sun(?:light)?\s+(?:streams?|pours?|warms?|blazes?|shines?)|bright\s+sun|blue\s+sky|cloudless|clear\s+sky|sunny)\b")
_RAIN = re.compile(r"(?i)\b(?:rain(?:ing|s|drops?)?|drizzl\w+|downpour|thunder|lightning|snow(?:ing|flakes?)?|sleet)\b")
_JOKY = re.compile(r"(?i)\b(?:giggl\w+|cheerful(?:ly)?|bubbly|chirp(?:s|ed|y)|skips?\s+happily|grins?\s+brightly|beams?|squeals?\s+with\s+delight)\b")
_COLD_DOM = re.compile(r"(?i)\b(?:sweat(?:ing)?\s+in\s+the\s+heat|baking\s+sun|scorching)\b")


def env_note(text, amb, sim=None):
    """'' when the reply fits the scene, else a correction for a retry. Conservative: only clear contradictions."""
    if not text or not amb:
        return ""
    w, ind = amb.get("weather"), amb.get("indoors")
    plain = re.sub(r"\*([^*]+)\*", r"\1", text)
    if w in ("rain", "storm", "snow") and _SUN.search(plain) and not WEATHER_STOP.search(plain):
        return f"The weather in this scene is {w}. Do not write sunshine, blue sky or clear weather unless the story clearly changes it."
    if w == "clear" and _RAIN.search(plain) and not re.search(r"(?i)\b(?:starts?|began|begins|beginning)\s+to\s+(?:rain|snow|drizzle)|clouds?\s+(?:roll|gather|build)", plain):
        return "It is clear weather in this scene. Do not add rain, snow or thunder out of nowhere; if the weather should turn, show it building first (clouds, wind, a change in the air)."
    if ind is True and w in ("rain", "storm", "snow") and _INDOOR_BODY.search(plain) and not re.search(r"(?i)\b(?:just\s+came|came\s+in|comes\s+in|stepp?(?:ed|s)\s+in|dripping\s+from)\b", plain):
        return f"The characters are indoors, so the {w} is heard and seen through windows and walls, not felt on their skin. Keep them dry unless they just came in from it."
    if amb.get("horror") == 2 and len(_JOKY.findall(plain)) >= 1:
        return "This is a horror scene. Remove cheerful, bubbly or giggling wording; keep the tension, the fear in the body and the dread."
    return ""
