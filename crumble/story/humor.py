"""Humour: characters are funny in their own way, at moments that fit, and never at the wrong one.

The sheet's "Sense of humour" field (or, failing that, the personality) gives a STYLE (dry sarcasm, teasing, goofy, deadpan, dark, self-mocking,
absurd, gentle) and a LEVEL (none, low, medium, high). A fixed cadence (the same chat always gives the same turns) decides when a playful
beat is invited; it is held back when the other person is hurting, in horror, in a tense argument or a tender moment, and invited sooner
when the other person just joked or the mood is light. The model writes the joke; this module only sets the stage.

    profile(c)                          {'style', 'how', 'level'}
    cue(h, ...)                         the instruction for this turn ('' when no beat is due)
Pure functions.
"""
import re
import zlib

STYLES = [
    ("none", r"\b(?:no sense of humou?r|humou?rless|never jokes?|doesn'?t joke|stern|grim|solemn|austere)\b", "rarely jokes; a joke from them is rare, small and unmistakably theirs"),
    ("sarcastic", r"\b(?:sarcas\w*|snark\w*|wry|dry wit|cynical|biting|sharp[- ]tongued|roast\w*|acerbic)\b", "dry, sarcastic understatement: says the opposite of what is meant, a deadpan roast, a raised eyebrow in words"),
    ("teasing", r"\b(?:teas\w+|banter\w*|playful|cheeky|mischiev\w*|flirty|ribbing|needl\w+)\b", "affectionate teasing and banter: picks on small things the other said or did, then softens it"),
    ("goofy", r"\b(?:goofy|silly|clown\w*|jokester|prankster|bubbly|giggl\w*|pun\w*|dad jokes?|zany|wacky|comedian)\b", "goofy and exaggerated: puns, silly voices, dramatic overreactions, laughing at their own jokes"),
    ("deadpan", r"\b(?:deadpan|straight[- ]faced|stoic humou?r|bone[- ]dry|understated)\b", "deadpan: absurd or cutting things said in a flat tone with a perfectly straight face"),
    ("dark", r"\b(?:dark humou?r|gallows|morbid|macabre|grim humou?r|black humou?r)\b", "gallows humour: jokes about bad situations, danger and mortality, said lightly"),
    ("selfdep", r"\b(?:self[- ]deprecat\w*|self[- ]mock\w*|awkward|clumsy|bumbling|laughs at (?:himself|herself|themselves))\b", "makes fun of themselves first: a rueful aside about their own mistakes and quirks"),
    ("absurd", r"\b(?:absurd\w*|surreal|random|quirky|eccentric|offbeat|whimsical)\b", "random, absurd tangents and strange observations delivered with total sincerity"),
    ("gentle", r"\b(?:gentle|warm|wholesome|soft humou?r|kind humou?r|sweet|cheerful|sunny)\b", "warm, light humour: small smiles, kind observations, nothing sharp"),
]
HIGH = re.compile(r"(?i)\b(?:jokes? (?:a lot|constantly|all the time)|always joking|funny|witty|comedian|class clown|jokester|life of the party|playful|bubbly|chatty|outgoing|extrovert\w*|talkative|banter\w*)\b")
LOW = re.compile(r"(?i)\b(?:serious|stoic|reserved|quiet|shy|introvert\w*|aloof|cold|solemn|stern|laconic|guarded|withdrawn|brooding)\b")


def profile(c):
    field = " ".join(str(c.get(k) or "") for k in ("humor",)).strip()
    soft = " ".join(str(c.get(k) or "") for k in ("personality", "speech", "quirks", "texting", "catchphrases"))[:900]
    style, how = "", ""
    for src in ([field] if field else []) + [soft]:
        for name, rx, h in STYLES:
            if re.search(rx, src, re.I):
                style, how = name, h
                break
        if style:
            break
    if field and not style:
        style, how = "custom", field[:140]
    if style == "none":
        level = 0
    elif field and re.search(r"(?i)\b(?:a lot|constantly|always|loves? to|can'?t stop)\b", field):
        level = 3
    elif HIGH.search(field + " " + soft) and not LOW.search(field):
        level = 3
    elif field:
        level = 2
    elif LOW.search(soft):
        level = 1
    else:
        level = 2
    if not style:
        style, how = ("gentle", "light, natural humour that fits who they are; small and quick, never a performance") if level else ("none", STYLES[0][2])
    return {"style": style, "how": how, "level": level}


EVERY = {0: 0, 1: 8, 2: 5, 3: 3}
KINDS = ["tease the other person about something they just said or did, lightly",
         "make a dry or funny observation about something real in the surroundings, the weather or the moment",
         "make a small joke at their own expense",
         "exaggerate something for comic effect",
         "answer an ordinary thing in an unexpectedly absurd or deadpan way",
         "call back to something funny that was said earlier, if anything was",
         "turn a small annoyance into a quick comedic complaint"]


def cue(h, name, user, turn, cid, moment, mood="", tension=0, horror=0, tender=0, setting="auto", tired=False):
    """The instruction for this turn: '' when nothing is due. moment: the read of the other person's last message (story.moment.read)."""
    lvl = h["level"]
    if setting == "more":
        lvl = min(3, lvl + 1) if lvl else 1
    elif setting == "less":
        lvl = max(0, lvl - 1)
    kinds = moment.get("kinds") or ()
    if "joke" in kinds and lvl:
        return (f"{user} is joking. Meet it the way {name} would ({h['how']}): laugh, groan, roast it, or top it with a line of their own. "
                f"Do not explain the joke or announce that it is funny.")
    if "joke" in kinds:
        return f"{user} is joking. {name} is not much of a joker, but notices and reacts in their own small way (a snort, a dry look, a quiet 'ha')."
    low_mood = bool(re.search(r"(?i)\b(?:sad|hurt|grief|grieving|angry|furious|scared|anxious|worried|lonely|guilty|devastated|upset|heartbroken|hopeless)\b", mood or ""))
    dark = h["style"] == "dark"
    if not lvl or tension >= 2 or horror == 2 or tender == 2 or "sad" in kinds or "hostile" in kinds or (low_mood and not dark):
        return ""
    every = EVERY[lvl]
    if "goodnews" in kinds or re.search(r"(?i)\b(?:happy|joyful|playful|amused|excited|smug|content|relaxed)\b", mood or ""):
        every = max(2, every - 1)
    if tired:
        every += 2
    k = zlib.crc32(f"{cid}|{turn}".encode()) % every
    if k != 0:
        return ""
    way = KINDS[zlib.crc32(f"{cid}|{turn // every}|kind".encode()) % len(KINDS)]
    return (f"A playful beat is due: if it fits the moment, let {name} be funny the way {name} is ({h['how']}). For example, {way}. "
            f"Keep it short and natural; never explain it. Skip it if the moment turns out to be serious.")
