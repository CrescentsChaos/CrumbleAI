"""Wildlife: real animals from data/animals/Animals.json turn up where they really live, and every encounter is a small story.

The scene's habitat is read from the scenario and the latest messages (jungle, swamp, desert, mountain, cave, shore, open sea, river, lake, city
street, a basement...), so a black bear never wanders into a coral reef and a shark never turns up on dry land. From the animals that fit the
place, the hour (day or night animals) and how common each one is, one is chosen and an encounter is played out over a few messages:

    awe     a quiet, beautiful or strange sighting
    fun     something charming, comic or mischievous
    tense   warning signs, a stand-off, a close call
    terror  real fear: the animal is a genuine danger and the scene feels it

Like the rest of the story engine it is DERIVED (no model call, nothing saved): the same chat position always gives the same animal and the same
stage, so swipes and rewinds keep their encounter, and an encounter holds still while it plays out (it is chosen from stable things only, never
from the scene's own rising fear). It never starts in a tender or grieving moment and never piles onto a fight that is already going on.

    load()                                            the usable animal records (cached)
    sprite_name(name)                                 'White's Bat' -> 'white_s_bat.png'
    sprite_url(name)                                  '/animals/sprites/white_s_bat.png' if that file exists, else ''
    habitats(texts, place, indoors)                   {'Jungle': 2.0, ...} what the scene looks like
    encounter(turn, seed, ...)                        -> dict or None: the animal, the mood, the stage and the words for the prompt
Pure functions apart from the cached file read.
"""
import json
import re
import zlib
from pathlib import Path

from ..config import ROOT

DATA = ROOT / "data" / "animals" / "Animals.json"
SPRITES = ROOT / "data" / "animals" / "sprites"

RARITY = {"Common": 10.0, "Uncommon": 6.0, "Rare": 3.0, "Epic": 1.2, "Legendary": .3, "Mythical": .5}
MEAT = {"Carnivore", "Piscivore", "Omnivore", "Scavenger", "Sanguivore"}
AQUATIC_CLASSES = {"Fish", "Cnidarian", "Echinoderm"}
WATER_ONLY = {"Ocean", "Coral Reef", "Deep Sea", "Kelp Forest", "Frozen Ocean", "Lake", "River"}
SEA_HABS = {"Ocean", "Coral Reef", "Deep Sea", "Kelp Forest", "Frozen Ocean"}
INDOOR_OK_CLASSES = {"Mammal", "Insect", "Arachnid", "Reptile", "Bird", "Amphibian"}

REGION_WORDS = {   # where an animal is from (read from its name and description) / where the scene is (read from the story)
    "australia": r"australi\w*|tasmani\w*|outback|sydney|melbourne|queensland|new zealand|kangaroo|wombat|aussie",
    "africa": r"africa\w*|madagascar|sahara|kenya|tanzania|serengeti|nigeria|egypt\w*|congo|namibia|kalahari|botswana|zambia|cape\b",
    "asia": r"asia\w*|india\w*|china|chinese|japan\w*|siberia\w*|himalaya\w*|sumatra\w*|borneo|bornean|thailand|vietnam\w*|nepal|bangladesh|dhaka|indonesia\w*|philippin\w*|malay\w*|korea\w*",
    "n_america": r"north america\w*|america(?:n)?\b|canad\w*|alaska\w*|texas|california\w*|florida|united states|\bUSA?\b|mexic\w*|yellowstone|appalachian|rocky mountains",
    "s_america": r"south america\w*|amazon\w*|brazil\w*|peru\w*|andes|andean|patagonia\w*|argentin\w*|galapagos|chile\w*|colombia\w*",
    "europe": r"europe\w*|eurasian|british|england|scotland|ireland|france|french|germany|german|iberian|mediterranean|alps|alpine|norway|norwegian|sweden|swedish|finland|italy|spain",
}
REGION_RX = {k: re.compile(r"(?i)\b(?:" + v + r")") for k, v in REGION_WORDS.items()}
MOODS = ("awe", "fun", "tense", "terror")
DURATION = {"awe": 2, "fun": 2, "tense": 3, "terror": 4}
EVERY = {"off": 0, "rare": 16, "normal": 10, "lively": 6}
CHANCE = {"rare": 70, "normal": 75, "lively": 85}     # percent of the slots that really have an encounter

PREHISTORIC = re.compile(r"(?i)\b(?:prehistoric|dinosaurs?|jurassic|cretaceous|ice age|pleistocene|lost world|time[- ]travel\w*|paleolithic|stone age)\b")
NOT_REAL = re.compile(r"(?i)\bthe\b|unnamed|\bpet\b")
DOMESTIC = re.compile(r"(?i)\b(?:domestic|breed|pet|companion|household|farm|livestock|dairy|poultry|draft)\b")
CETACEAN = re.compile(r"(?i)\b(?:whale|dolphin|porpoise|narwhal|orca|beluga)\b")
SNAKE = re.compile(r"(?i)\b(?:snake|viper|cobra|mamba|python|boa|anaconda|rattlesnake|adder|krait|taipan|racer|cottonmouth|copperhead|asp)\b")
CROC = re.compile(r"(?i)\b(?:crocodile|alligator|caiman|gharial)\b")
SHARK = re.compile(r"(?i)\bshark\b")
SWARM = re.compile(r"(?i)\b(?:wasp|hornet|bees?|yellow ?jacket|fire ant|bullet ant|army ant|driver ant|killer bee)\b")
BIGBIRD = re.compile(r"(?i)\b(?:cassowary|ostrich|emu)\b")
VENOM = re.compile(r"(?i)\b(?:venom\w*|poison\w*|toxi\w*|neurotox\w*|sting\w*)\b")
LETHAL = re.compile(r"(?i)\b(?:deadl\w+|lethal|fatal\w*|kills?|man-?eaters?|most dangerous|most feared|highly venomous|most venomous|dangerous to (?:humans|people)|feared)\b")
DANGER_NAME = re.compile(r"(?i)widow|recluse|funnel-?web|wandering spider|bark scorpion|deathstalker|fat-?tailed|redback|banana spider|box jelly|blue-ringed|stonefish|cone snail")
AGGR = re.compile(r"(?i)\b(?:aggressive|territorial|ferocious|attack\w*|charg\w*|defensive|fierce|apex predator|ambush\w*)\b")

# ---- where things are: scene words -> habitats of the database (weight)
ENV = [
    (r"jungle|rainforest|rain forest|amazon\b|tropical forest|canopy|vines hang", {"Jungle": 3, "Rainforest": 3}),
    (r"swamp|bayou|marsh|\bbog\b|everglades|wetlands?|fen\b|quagmire", {"Swamp": 3, "Wetlands": 3, "River": .5}),
    (r"mangrove", {"Mangrove": 4, "Swamp": 1}),
    (r"desert|\bdunes?\b|oasis|sahara|badlands|mesa\b|canyon|wasteland|arid|cactus|cacti", {"Desert": 4}),
    (r"savann?ah|safari|serengeti|veld|veldt|acacia", {"Savanna": 4, "Plains": 1}),
    (r"plains|prairie|meadow|pasture|ranch|steppe|grassland|farm(?:land|yard)?\b|\bfields?\b|\bbarn\b", {"Plains": 3, "Savanna": .5}),
    (r"mountain|alpine|\bcliffs?\b|\bridge\b|summit|\bpeak\b|highlands?|mountain pass|\bcrag\b|scree|foothills?", {"Mountain": 4}),
    (r"tundra|arctic|polar|glacier|ice ?sheet|permafrost|frozen (?:wastes?|plain)|snowfield", {"Tundra": 3, "Polar": 3}),
    (r"taiga|boreal|pine forest|snowy forest|northern forest|spruce|fir trees", {"Taiga": 4}),
    (r"redwoods?|sequoias?|giant trees|towering trees", {"Redwoods": 4}),
    (r"forest|\bwoods\b|woodland|\btrail\b|hiking|\bhike\b|wilderness|campsite|camping|campfire|undergrowth|clearing in the trees", {"Taiga": 2, "Redwoods": 1.5, "Mountain": 1, "Jungle": .6}),
    (r"cave\b|caves\b|cavern|grotto|\bmines?\b|mineshaft|underground|catacombs?", {"Cave": 4}),
    (r"volcano|volcanic|\blava\b|crater", {"Volcano": 4}),
    (r"beach|seashore|\bshore\b|seaside|coast(?:al|line)?|\btide\b|tide ?pools?|harbou?r|\bdock\b|\bpier\b|\bcove\b|lighthouse|sea ?cliffs?", {"Coastal": 4}),
    (r"open (?:sea|ocean|water)|\bocean\b|at sea|on the sea|\bship\b|sailing|sailboat|\bboat\b|scuba|snorkel\w*|\bdiving\b|underwater|\bsubmarine\b|\bfishing trawler\b|\bwhaling\b", {"Ocean": 4, "Coastal": .6}),
    (r"coral|\breef\b", {"Coral Reef": 4, "Ocean": 1}),
    (r"kelp", {"Kelp Forest": 4, "Ocean": 1}),
    (r"deep sea|abyss\w*|the deep\b|trench|bathyal|hadal", {"Deep Sea": 4, "Ocean": .5}),
    (r"ice floe|pack ice|icebreaker|frozen sea|frozen ocean", {"Frozen Ocean": 4, "Polar": 1}),
    (r"\brivers?\b|riverbank|\bstream\b|\bcreek\b|rapids|waterfall|canoe|kayak|\bbrook\b|\bravine\b", {"River": 4}),
    (r"\blake\b|\bponds?\b|lagoon|reservoir|lakeshore|lakeside", {"Lake": 4}),
]
ENV = [(re.compile(r"(?i)\b(?:" + p + r")" if not p.startswith(r"\b") else r"(?i)" + p), w) for p, w in ENV]
WATERY = re.compile(r"(?i)\b(?:swim\w*|wade[sd]?|wading|surf\w*|dive[sd]?|diving|boat|ship|paddl\w*|snorkel\w*|kayak\w*|canoe\w*|raft\w*|fishing|fish(?:es)? for|in the water|into the water|knee[- ]deep|waist[- ]deep|treading water|overboard|underwater|scuba|sail\w*|rowing)\b")
PLACE_HAB = {   # ambience place -> habitats (weight)
    "the street": {"Urban": 4}, "the park": {"Urban": 4, "Plains": .4}, "the rooftop": {"Urban": 4}, "the university campus": {"Urban": 4},
    "the graveyard": {"Urban": 3, "Cave": .3}, "the beach": {"Coastal": 4}, "the forest": {"Taiga": 2, "Redwoods": 1.5, "Mountain": 1, "Jungle": .6},
    "the cabin": {"Taiga": 2, "Redwoods": 1, "Mountain": 1.5}, "the shop": {"Urban": 3}, "the restaurant": {"Urban": 3},
    "the café": {"Urban": 3}, "the car": {"Urban": 2}, "the train": {"Urban": 2}, "the garage": {"Urban": 3},
}
WILD_INSIDE = {"the basement": {"Cave": 1.5, "Urban": 2}, "the attic": {"Cave": 1.5, "Urban": 2}, "the old house": {"Cave": 1.5, "Urban": 2},
               "the cabin": {"Urban": 2, "Cave": .5}}
DARK_SCENE = re.compile(r"(?i)\b(?:haunt\w*|horror|nightmare|survival|abandoned|apocalyp\w*|zombie\w*|creepy|eerie|sinister|ominous|dread|hunted|lost in|stranded|expedition|wilderness)\b")
NIGHT = {"night", "late at night"}
DAYPART = {"early morning", "morning", "midday", "afternoon"}

# ---- how an animal behaves, by kind (the model knows each species; this keeps it honest)
BEHAVIOR = {
    "Mammal": "mammals read people: they freeze, test the air, back off, bluff, or (if cornered, protecting young or food, or startled at close range) act fast and hard",
    "Bird": "birds watch from a perch, alarm-call, scatter together, dive-bomb a nest-robber, and steal anything unattended that looks like food",
    "Reptile": "reptiles are patient and economical: they hold still, hiss, gape or flatten, and strike or snap only when cornered, stepped on or very close",
    "Amphibian": "amphibians are slow, damp and wary; the real danger is almost never the bite but what is on their skin",
    "Fish": "in the water everything is fast and silent: shapes at the edge of sight, a bump, a change in the current, then very little warning",
    "Insect": "insects are about numbers, sound and surprise: a drone, a sting, a swarm that follows",
    "Arachnid": "arachnids hide in shoes, folds, crevices and shadow, and bite defensively when pressed or surprised",
    "Crustacean": "claws, scuttling and the sudden sideways speed of something that does not care how big you are",
    "Mollusk": "slow and strange; a thing to marvel at or step in carelessly",
    "Cnidarian": "drifting, barely visible, and in contact before anyone notices",
    "Echinoderm": "slow, spined and unbothered, a hazard only for bare feet",
}
TIER_TXT = {
    1: "harmless to people: the story is wonder, comedy or charm, never real injury",
    2: "usually avoids people but can bite, scratch, peck, sting or knock someone over if provoked, crowded or cornered; a real startle, rarely a real injury",
    3: "genuinely dangerous: a bite, strike or charge could cause serious injury; it usually gives warnings first, and the right response matters",
    4: "a top-tier danger: it could kill a person if things go wrong, and everyone in the scene knows it",
}
GOOD = {   # (mood, phase index) -> what this stage of the encounter does. {a} is the animal, {CH} and {US} are filled in by the caller.
    "awe": ["The first sign of {a}: a movement, a sound, a shape that makes everyone stop. Let the moment be quiet and a little unreal; people notice details (size, colour, how it moves, how little it cares about them).",
            "{a} is fully in view and goes about its own business. Let {CH} react as this person really would (delight, hushed wonder, a whispered fact, a want to get closer that is held back). End on a feeling or an image, not on a question."],
    "fun": ["{a} shows up and is immediately a character: curious, bold or mischievous. Play it light and specific to the species (what it wants, what it steals, how it behaves).",
            "{a} causes a small, funny, human-sized problem and leaves {CH} laughing, flustered or outwitted. Keep it warm and let it resolve; nothing dark."],
    "tense": ["The first sign: something is off. A sound stops, a smell, a track, a glint of eyes, the hair rising on an arm. {a} is only suspected or glimpsed, not confirmed. Keep it unnerving and restrained.",
              "{a} is confirmed and close enough to matter. It is watching, circling, blocking the way or standing its ground, and it behaves as this species really does (posture, warning, bluff). {CH} has to choose: freeze, back away slowly, make noise, protect someone. Stay in the person's fear.",
              "The stand-off breaks without a catastrophe: {a} withdraws, bluffs and stops short, or something else draws it off. The adrenaline crash comes: shaking hands, a laugh that is not funny, the realisation of how close it was."],
    "terror": ["The first sign is wrong in a way the body understands before the mind does: sudden silence, a smell, drag marks, a sound from the dark that is too big, a shape that does not belong. Do not name {a} yet if the scene can keep it hidden; build dread with senses.",
               "{a} is revealed, closer than anyone wants, and it is clearly a predator or a danger. Show its real size, speed and behaviour (how this species actually hunts or defends) in vivid, physical detail. Fear should be specific: the dry mouth, the heartbeat in the ears, the stupid thought that surfaces.",
               "{a} acts, fast and credibly: a charge, a strike, a lunge, a rush from the water, a bite at close range. It happens in seconds, confusingly and loudly. A real injury is possible if the animal's real behaviour and the characters' choices lead there, but do not kill anyone out of nowhere, and leave the outcome partly open for {US}'s next move.",
               "The aftermath: {a} retreats, is driven off, or is only barely avoided; it may still be near. The body pays now: shaking, nausea, laughing or crying, blood or dirt on hands, the need to get somewhere safe. Show the cost and the relief; the story decides what the characters do next."],
}
ALONE = ("This is happening to {CH} personally and right now, not in the distance. Other animals, weather and terrain follow the place the story is in; "
         "if this species would not normally live in the story's region, make it plausible in one detail (an escaped animal, a stowaway, a stray, a flood) or keep it brief.")
INDOOR_NOTE = "It is indoors, so it got in somehow (a gap, an open window, a vent, a box); it is cornered and frightened by walls and light, which is when animals are least predictable."

_CACHE = {"key": None, "recs": [], "by": {}}


def _h(*a):
    return zlib.crc32("|".join(str(x) for x in a).encode("utf-8", "ignore"))


def sprite_name(name):
    """'American Black Bear' -> 'american_black_bear.png', "White's Bat" -> 'white_s_bat.png', 'Long-tailed Cat' -> 'long_tailed_cat.png'."""
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_") + ".png"


def sprite_url(name):
    f = sprite_name(name)
    try:
        return f"/animals/sprites/{f}" if (SPRITES / f).is_file() else ""
    except OSError:
        return ""


def tier(a):
    """1 harmless, 2 can hurt if provoked, 3 genuinely dangerous, 4 could kill. From class, diet, size, weight and the description's own words."""
    name, cls, diet, w = a["name"], a["class"], a["diet"], float(a["weight"] or 0)
    desc = a["description"]
    venom, lethal, aggr = bool(VENOM.search(desc)), bool(LETHAL.search(desc)), bool(AGGR.search(desc))
    if CETACEAN.search(name):
        return 1                                    # whales and dolphins are awe, not terror
    t = 1
    if CROC.search(name):
        t = 4 if w >= 150 else 3
    elif SNAKE.search(name) and cls == "Reptile":
        t = 3 if venom or lethal or w >= 40 else 2 if w >= 1.0 else 1       # a 30 cm burrowing snake is not a threat
    elif SHARK.search(name) and diet in MEAT:
        t = 4 if w >= 150 else 3 if w >= 20 else 2 if w >= 5 else 1
    elif cls in ("Mammal", "Reptile") and diet in MEAT:
        t = 4 if w >= 150 else 3 if w >= 30 else 2 if w >= 5 else 1
        if t >= 2 and DOMESTIC.search(desc) and w < 25:
            t = 1
    elif cls == "Mammal" and diet not in MEAT:
        t = 3 if w >= 250 else 2 if w >= 100 else 1
    elif cls == "Fish" and diet in MEAT:
        t = 4 if w >= 150 else 3 if w >= 30 else 2 if (venom or aggr) and w >= 1 else 1
    elif cls == "Arachnid":
        t = 3 if lethal or (venom and (aggr or DANGER_NAME.search(name))) or DANGER_NAME.search(name) else 2 if venom or "scorpion" in name.lower() else 1
    elif cls == "Insect":
        t = 3 if re.search(r"(?i)giant hornet|killer bee|army ant|driver ant", name) else 2 if SWARM.search(name) else 1
    elif cls == "Bird":
        t = 3 if BIGBIRD.search(name) and w >= 40 else 2 if (aggr and w >= 3) or BIGBIRD.search(name) or re.search(r"(?i)swan|goose|eagle|owl|hawk|falcon", name) and w >= 1 else 1
    elif cls in ("Crustacean", "Cnidarian", "Mollusk"):
        t = 3 if (venom and lethal) or DANGER_NAME.search(name) else 2 if venom or lethal else 1
    if t < 4 and venom and lethal and cls not in ("Insect", "Bird"):
        t = max(t, 3)
    return t


def load():
    """The usable records, each with its habitats, tier and sprite file. Cached until the file changes."""
    try:
        key = (str(DATA), DATA.stat().st_mtime_ns)
    except OSError:
        return []
    if _CACHE["key"] == key:
        return _CACHE["recs"]
    try:
        raw = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = []
    recs, by = [], {}
    for a in raw if isinstance(raw, list) else []:
        if not isinstance(a, dict) or not str(a.get("name") or "").strip():
            continue
        habs = [x.strip() for x in str(a.get("habitat") or "").split(",") if x.strip()]
        if not habs or NOT_REAL.search(str(a["name"]).replace("The ", "", 1) if str(a["name"]).startswith("The ") else str(a["name"])):
            continue
        r = {"name": str(a["name"]).strip(), "sci": str(a.get("scientific_name") or ""), "class": str(a.get("class") or ""), "diet": str(a.get("diet") or ""),
             "active": str(a.get("active_time") or "any"), "rarity": str(a.get("rarity") or "Common"), "size": float(a.get("size") or 0),
             "weight": float(a.get("weight") or 0), "description": str(a.get("description") or ""), "drops": str(a.get("drops") or ""), "habs": habs}
        tag = f"{r['name']} {r['description'][:160]}"
        r["region"] = {k for k, rx in REGION_RX.items() if rx.search(tag)}
        r["tier"] = tier(r)
        r["w"] = RARITY.get(r["rarity"], 3.0)
        r["aq"] = r["class"] in AQUATIC_CLASSES or set(habs) <= WATER_ONLY
        r["prehistoric"] = r["rarity"] == "Mythical"
        recs.append(r)
        for hb in habs:
            by.setdefault(hb, []).append(r)
    _CACHE.update(key=key, recs=recs, by=by)
    return recs


def habitats(texts, place="", indoors=None):
    """{habitat: weight}: what the scene looks like, read from the scenario (first text) and the newest messages (counted double)."""
    texts = [t or "" for t in texts]
    recent = " \n".join(texts[-3:])
    older = " \n".join(texts[:-3])
    out = {}
    for rx, w in ENV:
        n = len(rx.findall(recent)) * 2 + len(rx.findall(older))
        if n:
            for hb, v in w.items():
                out[hb] = out.get(hb, 0) + v * min(n, 4)
    if not out and place:
        for hb, v in (PLACE_HAB.get(place) or {}).items():
            out[hb] = v
    return out


def _alive_at(rec, period):
    if not period:
        return True
    if rec["active"] == "day" and period in NIGHT:
        return False
    if rec["active"] == "night" and period in DAYPART:
        return False
    return True


def _share(hb):
    """A big habitat (Jungle has ~1000 animals) must not drown a small one just by head count: each habitat gets a weight of its own."""
    n = len(_CACHE["by"].get(hb) or [1])
    return min(3.0, max(.15, 120.0 / n))


def scene_regions(text):
    """The regions the story names (a country, a city, a continent). Empty if it names none."""
    return {k for k, rx in REGION_RX.items() if rx.search(text or "")}


_POOLS = {}


def pool(habs, period="", indoors=False, place="", watery=False, prehistoric=False, text=""):
    """[(record, weight)]: the animals that fit this place, this hour and this way of being there (memoised: it only depends on these)."""
    load()
    key = (_CACHE["key"], tuple(sorted(habs.items())), period, bool(indoors), place, bool(watery), bool(prehistoric), tuple(sorted(scene_regions(text))))
    if key not in _POOLS:
        if len(_POOLS) > 256:
            _POOLS.clear()
        _POOLS[key] = _pool(habs, period, indoors, place, watery, prehistoric, text)
    return _POOLS[key]


def _pool(habs, period, indoors, place, watery, prehistoric, text):
    load()
    by = _CACHE["by"]
    best = {}
    regions = scene_regions(text)

    def home(r):      # an animal from somewhere else is far less likely where the story names a region
        return 1.0 if not regions or not r["region"] or (r["region"] & regions) else .06
    if indoors:
        want = dict(WILD_INSIDE.get(place) or {"Urban": 2})
        for hb, v in want.items():
            for r in by.get(hb, []):
                if r["class"] in INDOOR_OK_CLASSES and r["weight"] <= 12 and not r["prehistoric"] and _alive_at(r, period) and not r["aq"]:
                    best[r["name"]] = (r, max(best.get(r["name"], (r, 0))[1], v * r["w"] * _share(hb) * home(r)))
        return list(best.values())
    for hb, v in habs.items():
        for r in by.get(hb, []):
            if r["prehistoric"] and not prehistoric:
                continue
            if r["aq"] and not watery:
                continue                                   # fish and jellyfish are met only when someone is in or on the water
            if set(r["habs"]) <= SEA_HABS and hb not in SEA_HABS:
                continue                                   # open-sea animals are never on the beach or the river bank
            if not _alive_at(r, period):
                continue
            wt = v * r["w"] * _share(hb) * home(r) * (.6 if r["prehistoric"] else 1)
            if wt > best.get(r["name"], (r, 0))[1]:
                best[r["name"]] = (r, wt)
    return list(best.values())


def _pick(items, *key):
    if not items:
        return None
    total = sum(w for _, w in items)
    x = (_h(*key) % 1000003) / 1000003 * total
    for r, w in items:
        x -= w
        if x <= 0:
            return r
    return items[-1][0]


def _mood(seed, slot, dark, scare, scary_scene):
    base = {"awe": 28.0, "fun": 27.0, "tense": 25.0, "terror": 20.0}
    if scare == "gentle":
        base.update(tense=8.0, terror=0.0)
    elif scare == "lots":
        base.update(awe=18.0, fun=14.0, tense=32.0, terror=36.0)
    if dark:
        base.update(tense=base["tense"] * 1.5, terror=base["terror"] * 1.5, fun=base["fun"] * .6)
    if scary_scene:
        base.update(tense=base["tense"] * 1.6, terror=base["terror"] * 2.2, fun=base["fun"] * .4)
    tot = sum(base.values())
    x = (_h(seed, slot, "mood") % 100003) / 100003 * tot
    for m in MOODS:
        x -= base[m]
        if x <= 0:
            return m
    return "awe"


def _fit(items, mood):
    if mood == "terror":      # the big hunters first: a bear, a big cat, a crocodile, a shark; venom and swarms are the rarer fright
        return [(r, w * (3.0 if r["weight"] >= 20 and r["class"] in ("Mammal", "Reptile", "Fish") else 1.0) * (1.0 if r["diet"] in MEAT else .3)) for r, w in items if r["tier"] >= 3]
    if mood == "tense":
        return [(r, w * (1.0 if r["diet"] in MEAT or r["tier"] >= 3 else .6)) for r, w in items if r["tier"] >= 2]
    if mood == "fun":
        return [(r, w * (1.0 if r["class"] in ("Mammal", "Bird") else .5)) for r, w in items if r["tier"] <= 2]
    return [(r, w * (1 + (r["rarity"] in ("Rare", "Epic", "Legendary")) + (r["size"] >= 2) * .5)) for r, w in items if r["tier"] <= 2 or r["size"] >= 3]


def schedule(step, seed, every, dur_of):
    """(slot, start_step) for the slot holding `step`; dur_of(slot) is how long that slot's encounter lasts. Pure."""
    slot = step // every
    return slot, slot * every + _h(seed, slot, "k") % max(1, every - dur_of(slot) + 1)


def facts(r):
    sz = f"about {r['size']:.1f} m long" if r["size"] >= 1 else f"about {max(1, round(r['size'] * 100))} cm long"
    wt = f"{r['weight']:.0f} kg" if r["weight"] >= 10 else f"{r['weight']:.1f} kg" if r["weight"] >= .1 else f"{r['weight'] * 1000:.0f} g"
    d = re.split(r"(?<=[.!?])\s+", r["description"].strip())
    return f"{r['name']} ({r['sci']}), {r['class'].lower()}, {r['diet'].lower()}, {sz}, {wt}. " + " ".join(d[:2])


def encounter(step, seed, texts, place="", indoors=None, period="", setting="normal", scare="some", prehistoric=None, narrator=False):
    """The encounter for this step of the chat, or None.
    texts: [scenario, ...newest messages]. Returns {'animal': record, 'mood', 'stage' (0-based), 'of', 'habitat', 'indoors', 'watery'} or None."""
    every = EVERY.get(setting, 10)
    if not every or not load():
        return None
    scene = " \n".join(t or "" for t in texts)
    pre = bool(PREHISTORIC.search(scene)) if prehistoric is None else prehistoric
    inside = indoors is True                        # indoors only small intruders come (a cat, a rat, a spider, a bat, a snake that got in)
    habs = {} if inside else habitats(texts, place, indoors)
    if not inside and not habs:
        return None
    watery = bool(WATERY.search(" ".join(texts[-3:]))) or bool(set(habs) & SEA_HABS)
    items = pool(habs, period, inside, place, watery, pre, scene)
    if not items:
        return None
    dark = period in NIGHT
    scary_scene = bool(DARK_SCENE.search(texts[0] if texts else ""))
    slot0 = step // every
    chance_pct = CHANCE.get(setting, 75)
    if _h(seed, slot0, "on") % 100 >= chance_pct:
        return None
    mood = _mood(seed, slot0, dark, scare, scary_scene)
    chosen = None
    for m in (mood, "tense", "fun", "awe"):
        if m == "terror" and scare == "gentle":
            continue
        if m == "tense" and mood != "tense" and scare == "gentle":
            continue
        cand = _fit(items, m)
        if cand:
            chosen, mood = _pick(cand, seed, slot0, "animal", m), m
            break
    if not chosen:
        return None
    slot, start = schedule(step, seed, every, lambda s: DURATION[mood])
    pos = step - start
    if not (0 <= pos < DURATION[mood]):
        return None
    hab = "Indoors" if inside else next((h for h, _ in sorted(habs.items(), key=lambda kv: -kv[1]) if h in chosen["habs"]), (chosen["habs"] or [""])[0])
    return {"animal": chosen, "mood": mood, "stage": pos, "of": DURATION[mood], "habitat": hab, "indoors": inside, "watery": watery, "slot": slot}


def words(enc, CH, US, narrator=False):
    """(block line for the prompt, compact line, private per-turn note) for an encounter."""
    a, mood, st = enc["animal"], enc["mood"], enc["stage"]
    nm = a["name"]
    beh = BEHAVIOR.get(a["class"], BEHAVIOR["Mammal"])
    stage = GOOD[mood][min(st, len(GOOD[mood]) - 1)].replace("{a}", nm).replace("{CH}", CH).replace("{US}", US)
    head = (f"[An animal in the scene: {nm}] Facts, true to the real animal: {facts(a)} How dangerous it really is: {TIER_TXT[a['tier']]}. "
            f"Behaviour: {beh}. Keep every detail faithful to this species (how it moves, sounds, smells, hunts or defends, what it does and does not do). "
            + (INDOOR_NOTE + " " if enc["indoors"] else "") + ALONE.replace("{CH}", CH))
    line = f"An encounter with {nm} is under way (stage {st + 1} of {enc['of']}, tone: {mood}). It is the same animal in every stage; do not swap it or add a second one."
    note = (f"Encounter, stage {st + 1} of {enc['of']} ({mood}) - {stage} Keep it the same {nm} as before and let it live in the scene (sound, smell, light, distance); if it has not appeared yet, bring it in now. "
            f"Write it as the story, not as a description of an animal fact sheet; no list of statistics, no naming this note.")
    if narrator:
        note = (f"The world: {nm} is part of this scene (stage {st + 1} of {enc['of']}, tone: {mood}). " + stage)
    return head, line, note


def info(enc):
    """What the page needs to draw an encounter card."""
    a = enc["animal"]
    return {"name": a["name"], "sci": a["sci"], "class": a["class"], "mood": enc["mood"], "stage": enc["stage"] + 1, "of": enc["of"], "tier": a["tier"],
            "rarity": a["rarity"], "habitat": enc["habitat"], "sprite": sprite_url(a["name"]), "size": a["size"], "weight": a["weight"], "diet": a["diet"]}
