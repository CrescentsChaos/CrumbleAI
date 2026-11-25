"""Places: location / scene cards that characters live in and you can explore.

A place card has a name, biome, description, atmosphere, a background picture for the chat, objects, activities, exits, events, history and
secrets, plus the characters that belong there. Cards live in data/places/<id>.json and pictures in data/places/img/.

How a place reaches the story (all derived from what the page sends each turn, no model call, nothing extra saved):
    context(spec)         the card the chat is standing in ({id, since} from the chat) with its residents, or None
    parts(loc, ...)       the prompt lines, the compact lines, this turn's event and the climate text for the wildlife/weather readers
    visit(...)            in a one-to-one chat: does a resident wander over and join in? (called by name, chiming in, or arriving)
    stage(b, getter)      turns a one-to-one chat that has visitors in it into a small group for the prompt, so everyone is labelled
    visit_tail(b, CH, US) the instruction for a visitor's message

Secrets, events and history are the author's: guests only ever get the public view of a card.
"""
import base64
import json
import re
import uuid
import zlib
from pathlib import Path

from .config import ROOT

TEXTS = {"name": 80, "biome": 60, "description": 1800, "atmosphere": 900, "history": 2500}
LISTS = {"objects": (30, 160), "activities": (30, 160), "exits": (20, 160), "events": (24, 300), "secrets": (20, 400)}
PRIVATE = ("secrets", "events", "history")      # what guests never see
EVERY = {"off": 0, "rare": 16, "normal": 10, "lively": 6}          # turns between chances for a resident to wander over
CHANCE = {"rare": 70, "normal": 75, "lively": 90}                  # percent of those slots that really bring someone
EVENT_EVERY = {"off": 0, "rare": 14, "normal": 9, "lively": 5}     # turns between the card's own events
MAX_IMG = 6 * 1024 * 1024
IMG_TYPES = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpg", b"RIFF": "webp", b"GIF8": "gif"}
BIOMES = ["Forest", "Jungle", "Swamp", "Desert", "Savanna", "Plains", "Mountain", "Tundra", "Taiga", "Cave", "Shore", "Open sea", "River", "Lake",
          "Village", "City street", "Market", "Home", "Tavern", "School", "Hospital", "Ruins", "Castle", "Ship", "Spaceship", "Underground", "Laboratory", "Garden"]


def start_id(x):
    """The id of an existing place card to start in, or "" (a card that was deleted, or something that is not an id, means no starting place)."""
    pid = _id(x)
    return pid if pid and get(pid) else ""


def home():
    return ROOT / "data" / "places"


def imgdir():
    return home() / "img"


def _id(x):
    return re.sub(r"\W", "", str(x or ""))[:40]


def _lines(v, n, w):
    if isinstance(v, str):
        v = v.splitlines()
    out = []
    for x in v if isinstance(v, (list, tuple)) else []:
        x = re.sub(r"\s+", " ", str(x or "")).strip()[:w]
        if x and x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return out[:n]


def clean(b, old=None):
    """A place card from what the page sent (anything missing keeps the old value)."""
    old = old or {}
    p = {"id": _id(b.get("id") or old.get("id")) or uuid.uuid4().hex[:8]}
    for k, w in TEXTS.items():
        p[k] = str(b[k] if k in b else old.get(k, "")).strip()[:w]
    for k, (n, w) in LISTS.items():
        p[k] = _lines(b[k] if k in b else old.get(k, []), n, w)
    ch = b["characters"] if "characters" in b else old.get("characters", [])
    p["characters"] = [i for i in dict.fromkeys(_id(x) for x in (ch if isinstance(ch, list) else [])) if i][:16]
    p["bg"] = str(old.get("bg") or "")
    p["bg_v"] = int(old.get("bg_v") or 0)
    p["name"] = p["name"] or "Unnamed place"
    return p


def _path(pid):
    return home() / f"{_id(pid)}.json"


def get(pid):
    pid = _id(pid)
    if not pid:
        return None
    try:
        p = json.loads(_path(pid).read_text("utf-8"))
        return clean(p, p) if isinstance(p, dict) else None
    except (OSError, ValueError):
        return None


def load_all():
    out = []
    for f in sorted(home().glob("*.json")) if home().is_dir() else []:
        p = get(f.stem)
        if p:
            out.append(p)
    return sorted(out, key=lambda p: p["name"].lower())


def save(p):
    home().mkdir(parents=True, exist_ok=True)
    _path(p["id"]).write_text(json.dumps(p, ensure_ascii=False, indent=1), "utf-8")
    return p


def remove(pid):
    p = get(pid)
    _path(pid).unlink(missing_ok=True)
    if imgdir().is_dir():
        for f in imgdir().glob(_id(pid) + ".*"):
            f.unlink(missing_ok=True)
    return bool(p)


def save_image(p, data_url):
    """Stores a picture sent as a data URL; returns the card with its new background. Raises ValueError for anything that is not a real image."""
    m = re.fullmatch(r"data:image/(?:png|jpe?g|webp|gif);base64,([A-Za-z0-9+/=\s]+)", str(data_url or ""))
    if not m:
        raise ValueError("That is not a picture the app can use (PNG, JPG, WebP or GIF).")
    raw = base64.b64decode(m[1], validate=False)
    if len(raw) > MAX_IMG:
        raise ValueError("That picture is too big (6 MB at most).")
    ext = next((e for sig, e in IMG_TYPES.items() if raw.startswith(sig)), "")
    if not ext or (ext == "webp" and raw[8:12] != b"WEBP"):
        raise ValueError("That file is not a PNG, JPG, WebP or GIF picture.")
    imgdir().mkdir(parents=True, exist_ok=True)
    for f in imgdir().glob(p["id"] + ".*"):
        f.unlink(missing_ok=True)
    (imgdir() / f"{p['id']}.{ext}").write_bytes(raw)
    return dict(p, bg=f"{p['id']}.{ext}", bg_v=p.get("bg_v", 0) + 1)


def clear_image(p):
    if imgdir().is_dir():
        for f in imgdir().glob(p["id"] + ".*"):
            f.unlink(missing_ok=True)
    return dict(p, bg="", bg_v=p.get("bg_v", 0) + 1)


def image_file(name):
    """The path of a place picture by file name, or None (names are checked, nothing outside data/places/img is ever read)."""
    if not re.fullmatch(r"\w+\.(?:png|jpg|webp|gif)", str(name or "")):
        return None
    f = imgdir() / name
    return f if f.is_file() else None


def view(p, admin=True):
    """What the page gets: guests never see secrets, events or history."""
    v = dict(p, bg_url=f"/places/img/{p['bg']}?v={p.get('bg_v', 0)}" if p.get("bg") else "")
    if not admin:
        for k in PRIVATE:
            v[k] = "" if k == "history" else []
    return v


# ---------------------------------------------------------------- in the story

def context(spec, turn=0, getter=None):
    """{'card', 'since', 'people': [names], 'ids': [ids]} for the place the chat stands in (spec = {'id', 'since'}), or None."""
    if not isinstance(spec, dict):
        return None
    card = get(spec.get("id"))
    if not card:
        return None
    if getter is None:
        from .storage import get_char as getter
    people, ids = [], []
    for i in card["characters"]:
        c = getter(i)
        if c and c.get("name"):
            people.append(c["name"])
            ids.append(i)
    try:
        since = int(spec.get("since") or 0)
    except (TypeError, ValueError):
        since = 0
    return {"card": card, "since": since, "people": people, "ids": ids, "turn": int(turn or 0)}


def climate_text(loc):
    """What the weather, habitat and wildlife readers should see of this place (they read words)."""
    if not loc:
        return ""
    c = loc["card"]
    return f"{c['name']}. {c['biome']}. {c['description']}"[:600]


OUTDOOR_BIOMES = {"forest", "jungle", "swamp", "desert", "savanna", "plains", "mountain", "tundra", "taiga", "shore", "open sea", "river", "lake",
                  "village", "city street", "market", "ruins", "garden"}
INDOOR_BIOMES = {"cave", "home", "tavern", "school", "hospital", "castle", "ship", "spaceship", "underground", "laboratory"}


def scene(loc):
    """The place the scene readers must treat as true: {'name', 'indoors', 'sense'}. The card wins over anything guessed from the words of the
    chat (a scenario that says "apartment" must not keep calling the Gate of Divinity an apartment)."""
    if not loc:
        return None
    from . import ambience
    c = loc["card"]
    text = f"{c['name']} {c.get('biome', '')} {c.get('description', '')}"
    indoors = None
    for _, rx, ind, _ in ambience.PLACES:
        if re.search(rx, text, re.I):
            indoors = ind
            break
    b = (c.get("biome") or "").strip().lower()
    if indoors is None:
        indoors = True if b in INDOOR_BIOMES else False if b in OUTDOOR_BIOMES else None
    sense = re.sub(r"\s+", " ", c.get("atmosphere") or c.get("description") or "").strip()[:220]
    return {"name": c["name"], "indoors": indoors, "sense": sense or "whatever the place card describes", "card": True}


def note(loc):
    """The author's-setting note the scene readers (place, indoors, light) get for this place. `place` says where the chat stands and `since` from
    which message on (earlier messages were somewhere else), so the reader can put it at the right point in the story."""
    return {"kind": "setting", "text": climate_text(loc), "place": scene(loc), "since": int(loc.get("since") or 0)} if loc else None


def _pick(seed, n):
    return zlib.crc32(str(seed).encode()) % n if n else 0


def event(loc, turn, setting="normal", skip=False):
    """This turn's event from the card's own list, or ''. An event lasts two turns so it has time to unfold; the same turn always gives the same event."""
    c = loc["card"]
    n = EVENT_EVERY.get(setting, 9)
    if skip or not n or not c["events"] or turn < 2:
        return ""
    if turn % n >= 2:
        return ""
    return c["events"][_pick(f"{c['id']}:{turn // n}", len(c["events"]))]


def parts(loc, ch, us, turn, events="normal", skip=False, narrator=False, doing=None):
    """{'lines', 'compact', 'event'} for the prompt. `ch` and `us` are the names (or placeholders) of the character and the user."""
    c = loc["card"]
    arrived = turn - loc["since"] <= 1 and loc["since"] > 0
    head = f"{ch} and {us} are at {c['name']}" + (f" ({c['biome']})" if c["biome"] else "") + "."
    if arrived:
        head += " They have only just arrived."
    L = ["[Where you are - the location card. What the story has already established still wins over what follows.]", head]
    if c["description"]:
        L.append(f"What it is like: {c['description']}")
    if c["atmosphere"]:
        L.append(f"Atmosphere: {c['atmosphere']} Let it colour the senses (sound, smell, light, temperature), the mood and how people talk. Show it; never recite it.")
    if c["objects"]:
        L.append("Things here that can be seen, touched or used: " + "; ".join(c["objects"]) + ". Only use them when it suits the moment.")
    if c["activities"]:
        L.append("What people do here: " + "; ".join(c["activities"]) + ".")
    if c["exits"]:
        L.append("Ways out: " + "; ".join(c["exits"]) + ".")
    if c["history"]:
        L.append(f"Its past (known to whoever would really know it, such as a local; nobody else): {c['history']}")
    if c["secrets"]:
        L.append("Hidden things about this place (the world's own secrets): " + " | ".join(c["secrets"]) +
                 f". Never state, hint at or hand over one unless {us} actually searches, investigates, follows a clue or asks someone who would really know. "
                 "Then give one small piece at a time, the way the scene would, and never all at once.")
    L.extend(people_lines(loc, doing, us))
    compact = [f"At {c['name']}" + (f" ({c['biome']})" if c["biome"] else "") + (f": {c['description'][:160]}" if c["description"] else ".") +
               (f" Atmosphere: {c['atmosphere'][:100]}" if c["atmosphere"] else "")]
    ev = event(loc, turn, events, skip or narrator)
    out = {"lines": L, "compact": compact, "event": ""}
    if ev:
        out["event"] = (f"Something happens here, from this place's own events: {ev}. Let it unfold naturally in this reply or the next "
                        f"(nothing {us} must answer), in the way the people there would really notice it.")
    return out


def people_lines(loc, doing, us):
    """Who lives or turns up here. With the model's answer for this moment it says who is in and what each is doing; without it, only that they exist."""
    if not loc or not loc.get("people"):
        return []
    items = {i: d for i, d in (doing or {}).items() if i in loc.get("ids", [])}
    if items:
        from .story import doing as dm
        return dm.roster_lines(items, dict(zip(loc["ids"], loc["people"])), us)
    return ["People who live or turn up here: " + ", ".join(loc["people"]) + ". They are not always in, they have their own business, and nobody has to be on hand for " + us + "."]


def narrator_lines(loc, turn, doing=None, us="the user"):
    c = loc["card"]
    L = [f"Place: {c['name']}" + (f" ({c['biome']})" if c["biome"] else "") + (f". {c['description']}" if c["description"] else ".")]
    if c["atmosphere"]:
        L.append(f"Atmosphere to convey: {c['atmosphere']}")
    if c["objects"]:
        L.append("Things here you may describe: " + "; ".join(c["objects"]) + ".")
    L.extend(people_lines(loc, doing, us))
    return L


def standalone(loc, ch, us, turn):
    """The prompt pieces when the story engine is off: the place still joins the prompt."""
    if not loc:
        return {}
    p = parts(loc, ch, us, turn, "off")
    return {"block": "\n".join(p["lines"]), "compact": "\n".join(p["compact"]), "tail": "", "plan": None}


# ---------------------------------------------------------------- visiting a place (a scene of its own)

SCENE = "pl_"        # a visit is a chat that belongs to the place: its id is pl_<place id>


def scene_id(pid):
    return SCENE + _id(pid)


def is_scene(gid):
    return str(gid or "").startswith(SCENE) and len(str(gid)) > len(SCENE)


def scene_group(gid):
    """The group a visit to a place runs as, or None. The people who live or turn up there are its cast; who is actually in right now is decided
    in the scene (story/doing.py) and sent with each request as `present`. A Narrator always describes the place and what goes on in it."""
    if not is_scene(gid):
        return None
    card = get(str(gid)[len(SCENE):])
    if not card:
        return None
    sc = " ".join(x for x in (f"{card['name']}" + (f" ({card['biome']})" if card["biome"] else "") + ".", card["description"]) if x)
    return {"id": scene_id(card["id"]), "name": card["name"], "members": list(card["characters"])[:16], "pace": "natural", "narrator": True,
            "scenario": sc[:1200], "place": card["id"]}


def only_present(members, present):
    """The members that are in the scene right now. `present` is None for an ordinary chat (everyone counts)."""
    if present is None:
        return members
    keep = {str(i) for i in present} if isinstance(present, (list, tuple, set)) else set()
    return [m for m in members if m.get("id") in keep]


# ---------------------------------------------------------------- visitors

def first(name):
    return (str(name or "").split() or [""])[0]


def called(text, names):
    """Names of residents the user is clearly speaking to ('Mira, ...', 'hey Mira', '@Mira', '..., Mira?'), not merely talking about."""
    t = str(text or "")
    out = []
    for n in names:
        forms = {n.strip(), first(n)}
        for x in forms:
            if len(x) < 3:
                continue
            e = re.escape(x)
            if re.search(rf"(?i)(?:@{e}\b|^[\s*\"'(]*{e}\b\s*[,:!?]|(?:\b(?:hey|hi|hello|oi|yo|oh|ah|excuse me|psst|pssst|hiya)\b[ ,]+){e}\b|,\s*{e}[\s.!?*\")]*$|\b(?:call|fetch|get|wave over|wave|ask|find)\s+{e}\b)", t):
                out.append(n)
                break
    return out


def mood_blocks(text):
    """True when the user's last message is grief, a goodbye or a quarrel: nobody wanders in."""
    try:
        from .story import moment
        k = moment.read(text)["kinds"] if text else []
        return bool({"sad", "hostile", "bye"} & set(k))
    except Exception:
        return bool(re.search(r"(?i)\b(?:goodbye|bye|see you|i have to go|funeral|died|crying|i hate you|shut up)\b", str(text or "")))


def visit(card, main_id, chars, hist, turn, text, setting="normal", seed="", dead=(), sim=None, force="", routines=True, since=0):
    """Does a resident of this place join the one-to-one chat now? -> {'id', 'name', 'why'} or None.

    sim, routines: kept for older callers and ignored. Nobody is kept out by the clock: what a resident is doing, or whether they are around at all, is for the
    model to decide in the scene (see story/doing.py), so a vigilante can turn up at 3 AM and a baker can be up before dawn.
    chars: {id: character} for the card's residents. why: 'called' (you spoke to them or asked for them), 'chime' (they are already
    in the scene and join in again) or 'arrive' (they wander over). Deterministic from the chat position: swipes and rewinds keep it."""
    pool = [chars[i] for i in card["characters"] if i in chars and i != main_id and i not in set(dead)]
    if not pool or setting == "off":
        return None
    if force:
        c = next((x for x in pool if x["id"] == force), None)
        return {"id": c["id"], "name": c["name"], "why": "called"} if c else None
    nm = called(text, [c["name"] for c in pool])
    if nm:
        c = next(x for x in pool if x["name"] == nm[0])
        return {"id": c["id"], "name": c["name"], "why": "called"}
    if mood_blocks(text):
        return None
    here = [m for m in (hist or [])[-6:] if m.get("role") == "assistant" and m.get("cid") and m.get("cid") != main_id and m.get("pl") == card["id"]]
    if here:       # already in the scene: they join in again about every other turn, and drift off after a while
        c = next((x for x in pool if x["id"] == here[-1]["cid"]), None)
        if c and _pick(f"{seed}:{turn}:chime", 100) < 50:
            return {"id": c["id"], "name": c["name"], "why": "chime"}
        return None
    n = EVERY.get(setting, 10)
    if not n or turn < 3 or turn - since < 2 or turn % n != 0:
        return None
    if _pick(f"{seed}:{turn // n}:slot", 100) >= CHANCE.get(setting, 75):
        return None
    c = pool[_pick(f"{seed}:{turn // n}:who", len(pool))]
    return {"id": c["id"], "name": c["name"], "why": "arrive"}


def stage(b, getter):
    """Prepares a /api/chat body for a one-to-one chat that has visitors: the main character's lines are labelled, and the prompt gets a small
    group of everyone involved. Does nothing for an ordinary chat. A visitor's turn arrives as b['visit'] = {'main', 'why'}."""
    if b.get("group"):
        return
    c = b.get("char") or {}
    v = b.get("visit") if isinstance(b.get("visit"), dict) else None
    main = c
    if v:
        main = getter(str(v.get("main") or "")) or {}
        if not main.get("id") or main["id"] == c.get("id"):
            b.pop("visit", None)
            v, main = None, c
    hist = [m for m in (b.get("history") or []) if isinstance(m, dict)]
    ids = []
    for m in hist:
        i = m.get("cid")
        if m.get("role") == "assistant" and i and i != main.get("id") and i not in ids:
            ids.append(str(i))
    if v and c.get("id") and c["id"] not in ids:
        ids.append(c["id"])
    if not ids:
        return
    members = [main] + [x for x in (getter(i) for i in ids[:6]) if x and x.get("id") != main.get("id")]
    if len(members) < 2:
        return
    for m in hist:
        if m.get("role") == "assistant" and not m.get("cid"):
            m["cid"], m["name"] = main.get("id"), main.get("name") or "Character"
    b["history"] = hist
    b["grp"] = dict(name=main.get("name") or "Character", scenario=main.get("scenario") or "", members=members, narrator=False)
    b["cue"] = b.get("cue") or {}
    if v:
        card = get((b.get("place") or {}).get("id")) if isinstance(b.get("place"), dict) else None
        b["visit"] = {"why": v.get("why") if v.get("why") in ("called", "chime", "arrive") else "chime", "main": main.get("name") or "Character",
                      "place": (card or {}).get("name", "")}


def visit_tail(b, ch, us):
    v = b.get("visit") or {}
    main, where = v.get("main") or "the other person", f" at {v['place']}" if v.get("place") else ""
    base = (f"{ch} is{where} with {us} and {main}. Write only {ch}'s next message, in {ch}'s own voice. Keep it short; do not take over the conversation. "
            f"{ch} is a person with their own business, not staff and not a helper: no offers of help, no cheerful greeting unless that is truly {ch}'s way. ")
    if v.get("why") == "called":
        return f"({us} has just spoken to {ch} or called them over. {base}Answer {us} directly, as {ch} really would; let {ch} arrive or look up the way they naturally would, and show their mood about being called.)"
    if v.get("why") == "arrive":
        return (f"({ch} lives or works nearby and has just turned up where {us} and {main} are talking. {base}"
                f"Show what {ch} was in the middle of and why they are here, in keeping with who {ch} is: they may barely acknowledge {us}, be wary, curt or amused. "
                f"Do not interrupt anything urgent or tender.)")
    return f"({ch} is already part of this scene. {base}Join in only with something {ch} would really say; react to what was just said instead of repeating anything.)"
