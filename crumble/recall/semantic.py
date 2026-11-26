"""Meaning-level matching for memory retrieval, with no model call and no dependency.

Keyword overlap alone cannot connect "what is that shiny thing round your neck?" to "Mira gave Tonoy a silver locket":
the two sentences share no word. Three cheap signals bridge that gap:

    concepts   words are grouped by meaning (locket / pendant / necklace / chain -> `jewelry`; present / gift / gave -> `gift`),
               so two texts that talk about the same kind of thing match even in different words
    fuzzy      a misspelling or a variant ("pendent", "lockett") still matches by character trigrams
    embedder   an optional real embedding function can be plugged in (set_embedder); when it is set its cosine similarity
               joins the score. Nothing here requires it and nothing here loads a second model.

score() returns 0..1 and the reasons, ready to be folded into the retrieval score next to the keyword, people and event signals.
"""
import math
import re

from . import lexicon as lx

# ---- concept groups: one line each, words that point at the same kind of thing ----
_GROUPS = {
    "jewelry": "locket pendant necklace chain charm amulet ring bracelet earring brooch jewel jewelry jewellery gem gemstone diamond pearl silver gold shiny sparkly neck wrist finger wearing worn trinket",
    "gift": "gift present gave give given giving hand handed surprise wrapped keepsake token souvenir offered",
    "birthday": "birthday anniversary celebrate celebration cake candle party turned",
    "promise": "promise promised swear swore vow pledge oath guarantee word committed commitment",
    "secret": "secret secrets confess confessed confession hidden private confide confided whisper whispered undisclosed",
    "lie": "lie lied lying liar fib deceive deceived dishonest false fake pretend",
    "meeting": "meet meeting met rendezvous appointment gather arrive arrived encounter",
    "place_water": "water swim swimming drown drowning deep wave waves pier dock harbor harbour port wharf shore beach lake river sea ocean pond bay boat ship",
    "place_home": "house home apartment flat room kitchen bedroom cottage cabin hut lodge dwelling",
    "place_town": "town city village street market square tavern inn bar cafe shop store bakery",
    "place_nature": "hills hill forest woods jungle mountain hill valley field meadow cave desert swamp island",
    "family": "family relatives household",
    "parents": "mother father mom mum dad parent parents mama papa",
    "siblings": "sister brother sibling siblings twin",
    "grandparents": "grandmother grandfather grandma grandpa granny grandparent",
    "children": "son daughter child children kid kids baby",
    "extended": "cousin uncle aunt relative niece nephew",
    "partner": "wife husband spouse girlfriend boyfriend partner fiance fiancee lover married marriage dating engaged",
    "friend": "friend friends buddy pal companion ally mate",
    "enemy": "enemy enemies rival foe nemesis hostile adversary",
    "pet": "dog cat puppy kitten pet hound horse bird parrot rabbit hamster",
    "food": "ramen noodles noodle pizza burger rice curry pasta sandwich salad spicy sweet dessert food meal dinner lunch breakfast supper eat ate eaten cook cooked bake baked snack feast hungry soup bread cookie cake pie",
    "drink": "drink drank tea coffee wine ale beer water juice milk whiskey cocktail thirsty",
    "allergy": "allergic allergy peanut peanuts shellfish gluten lactose intolerance reaction nuts",
    "illness": "sick ill illness fever cough cold flu disease infection sickness unwell nausea plague",
    "injury": "injured injury wound wounded hurt bleeding blood cut broken broke bruise sprain scar bandage stitches",
    "death": "alive survive survived survivor died dead death dying killed murdered funeral grave buried corpse mourn mourning grief perished",
    "violence": "fight fought attack attacked punch punched hit slap slapped stab stabbed shoot shot sword weapon battle duel brawl",
    "danger": "danger dangerous threat threatened risk peril trap ambush chase chased escape escaped",
    "likes": "love loved like liked likes enjoy enjoys adore favorite favourite prefer prefers fond",
    "love": "love loved kiss kissed hug hugged embrace cuddle romance romantic affection adore crush flirt blush",
    "anger": "angry anger furious mad rage yelled yell shouted shout irritated annoyed livid",
    "sadness": "sad sadness cry cried crying tears tearful grief sorrow lonely heartbroken depressed miserable",
    "fear": "afraid scared fear terrified frightened anxious nervous panic dread worried",
    "joy": "happy joy glad delighted cheerful laugh laughed smile smiled excited thrilled",
    "apology": "sorry apologize apologise apologized forgive forgave forgiveness regret mistake blame",
    "money": "money coin coins gold silver cash pay paid owe owes owed debt loan price cost cheap expensive rich poor wage salary rent",
    "work": "living earn earned profession nurse doctor teacher blacksmith baker farmer work job career boss employer employee office shift occupation profession hired fired quit",
    "school": "school class teacher student exam test homework university college lesson study studied degree",
    "travel": "trip travel journey voyage flight train ship road visit visited vacation holiday abroad",
    "time_day": "morning noon afternoon evening night midnight dawn dusk sunrise sunset today tomorrow tonight yesterday",
    "weather": "thunderstorm thunderstorms storming rain rainy storm thunder snow wind windy fog sunny cloudy cold hot weather lightning",
    "music": "music song sing sang singing guitar piano violin melody band concert instrument drum flute",
    "books": "diary journal book books read reading novel story poem library write wrote diary journal letter",
    "game": "game play played playing chess cards dice puzzle toy sport match",
    "weapon": "sword dagger knife bow arrow gun pistol rifle axe spear blade shield armor armour",
    "clothing": "dress shirt coat cloak jacket hat scarf gloves boots shoes uniform robe clothes clothing wearing",
    "vehicle": "car carriage cart wagon bike bicycle boat ship horse train bus",
    "magic": "magic spell wizard witch curse potion enchanted sorcery power ability",
    "crime": "steal stole stolen thief theft rob robbed arrest arrested prison jail crime criminal guard smuggle",
    "name": "name named called nickname alias",
    "age": "age old years young birthday born",
    "home_place": "live lives lived living resident residence address hometown",
    "health_care": "doctor nurse hospital medicine medication pill treatment healer clinic",
    "trust": "trust trusted betray betrayed betrayal loyal loyalty faithful suspicion suspicious doubt",
    "help": "help helped save saved rescue rescued protect protected assist support",
    "decision": "decide decided decision choose chose choice agree agreed agreement settled deal",
    "plan": "plan plans planning scheme intend intended arrange arranged schedule",
    "memory": "remember remembered memory memories forget forgot recall reminded",
    "building": "building tower lighthouse castle temple church barn mill palace fortress hall",
    "night_sky": "moon moonlight star stars sky constellation lunar crescent",
    "light": "lighthouse beacon lamp lantern candle torch light fire flame glow",
    "key_item": "key keys unlock unlocked unlocks lock locked cellar door gate chest box vault safe",
    "map_item": "map compass route path direction treasure",
    "letter": "letter note message mail envelope telegram package parcel",
    "photo": "photo photograph picture portrait painting drawing sketch",
    "ring_item": "ring wedding engagement band proposal proposed",
    "dream": "dream dreamed nightmare sleep slept asleep wake woke awake",
    "hobby": "hobby hobbies paint painting garden gardening fishing hiking knit knitting collect collecting",
    "royal": "king queen prince princess baron duke lord lady noble castle throne crown court",
    "military": "soldier army captain general guard knight war battle siege commander troops",
    "religion": "god church temple prayer pray priest blessing faith holy",
    "language": "speak spoke language accent translate dialect words",
    "shop": "buy bought sell sold shop merchant trade vendor market",
    "noise": "loud noise sound scream screamed whisper bang crash",
    "touch": "hold held touch touched grab grabbed hand hands holding",
    "leave": "leave left leaving depart departed goodbye farewell walked away abandoned",
    "return": "return returned came back comeback arrived home",
    "lost_item": "lost missing misplaced vanished disappeared gone",
    "find_item": "found discovered noticed spotted uncovered",
    "teach": "teach taught learn learned lesson train trained practice practised",
    "cook": "cook cooking kitchen recipe chef baked oven",
    "body_face": "face eyes eye smile hair cheek lips voice",
    "allergy_food": "peanut peanuts nuts shellfish dairy wheat eggs soy",
}

_BOILER = re.compile(r"\s*\([^()]*(?:second-hand|unverified|not real|said when they turned)[^()]*\)")


def core(text):
    """The memory's own content, without the labels the extractor adds ('second-hand, unverified'): those words must not match anything."""
    return _BOILER.sub("", str(text or "")).strip()


_STEM = lx.stem
CONCEPTS = {}                     # stem -> set of concept ids
for _cid, _words in _GROUPS.items():
    for _w in _words.split():
        CONCEPTS.setdefault(_STEM(_w), set()).add(_cid)

_embedder = None
_emb_cache = {}


def set_embedder(fn):
    """Plug in a real embedding function: fn(list[str]) -> list[list[float]]. None switches it off again."""
    global _embedder
    _embedder = fn
    _emb_cache.clear()


def embedder_on():
    return _embedder is not None


def concepts(stems):
    """The concept ids a set of stems points at."""
    out = set()
    for s in stems:
        out |= CONCEPTS.get(s, set())
    return out


def _grams(w):
    w = f"^{w}$"
    return {w[i:i + 3] for i in range(len(w) - 2)}


def _fuzzy(a, b):
    """Typos and variants: two longer words that share most character trigrams are the same word."""
    if len(a) < 5 or len(b) < 5 or a[0] != b[0] or abs(len(a) - len(b)) > 3:
        return 0.0
    ga, gb = _grams(a), _grams(b)
    j = len(ga & gb) / len(ga | gb)
    return j if j >= .5 else 0.0


def _cos(a, b):
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def _embed(texts):
    todo = [t for t in texts if t not in _emb_cache]
    if todo:
        try:
            for t, v in zip(todo, _embedder(todo)):
                _emb_cache[t] = v
        except Exception:        # a failing embedder must never break a reply: fall back to the built-in signals
            return None
        if len(_emb_cache) > 3000:
            _emb_cache.clear()
    return [_emb_cache.get(t) for t in texts]


KIND_TAGS = {"gift": "gift gave given present", "promise": "promise promised swear", "secret": "secret confided private", "plan": "plan arranged schedule meet decide decided agreed",
             "decision": "decide decided agreed", "body": "injury hurt health", "claim": "said told claimed", "hypothetical": "imagine pretend", "relationship": "relationship family friend",
             "feeling": "feeling felt emotion"}


def prepare(query_text):
    """What the query needs for scoring, computed once per reply."""
    stems = set(lx.terms(query_text))
    return {"text": query_text or "", "stems": stems, "concepts": concepts(stems)}


def concept_idf(items):
    """Rarer concepts count more (everything mentions 'time_day'; few things mention 'jewelry')."""
    df, n = {}, max(1, len(items))
    for i in items:
        for c in concepts(set(lx.terms(core(i["text"])))):
            df[c] = df.get(c, 0) + 1
    return {c: 1 + math.log(1 + n / (1 + k)) for c, k in df.items()}


def score(prep, item_text, cidf=None, kind=""):
    """-> (0..1, [reasons], strength) how close this memory is in meaning to the query. strength = how many query words (up to two per
    concept) found a partner in the memory: 1 is a loose topical hint, 2 or more is a real match."""
    if not prep["stems"]:
        return 0.0, [], 0
    its = set(lx.terms(item_text + " " + KIND_TAGS.get(kind, "")))
    why, keep, strength = [], 1.0, 0
    ic = concepts(its)
    shared = prep["concepts"] & ic
    if kind and prep["concepts"] & concepts({lx.stem(w) for w in KIND_TAGS.get(kind, "").split()}):
        strength += 1                       # the question asks for this kind of thing ("what did I give" -> a gift)
    literal = concepts(prep["stems"] & its)
    raw = 0.0
    for c in shared:
        hits = sum(1 for q in prep["stems"] if c in CONCEPTS.get(q, ()))
        strength += min(2, hits)
        raw += (cidf or {}).get(c, 1.5) * (.35 if c in literal else .55 + .25 * min(3, hits))
    if raw:
        keep *= 1 - raw / (raw + 2.2)
        why.append("meaning")
    fz = 0.0
    for q in prep["stems"] - its:
        for s_ in its - prep["stems"]:
            fz = max(fz, _fuzzy(q, s_))
    if fz:
        keep *= 1 - .8 * fz
        why.append("similar word")
        strength += 2
    if _embedder is not None:
        v = _embed([prep["text"], item_text])
        if v and v[0] is not None and v[1] is not None:
            c = max(0.0, _cos(v[0], v[1]))
            if c > .5:
                keep *= 1 - min(.9, (c - .5) * 2)
                why.append("embedding")
                strength += 2
    return round(1 - keep, 4), why, strength
