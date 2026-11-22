"""Turn a free-text description of someone's skills, powers and gear into data a fight (or any attempt) can really use.

The player writes "Master swordsman, 12 years of kenjutsu. Can throw fire lance (level 4). Weak to water. Carries a katana and a
silver ankh" and this module reads it, with no model call, into a profile:

    parse(skills, gear="") -> {"techs": [{name, kinds, tags, level, src}], "lim": [..], "weak": {tags}, "lvl": {kind: best level}}
    derive(profile)        -> the combat numbers the skills grant (attack, magic, guard, toughness, speed, aid, revive...)
    pick(profile, text, act) -> the technique the action text is using (by name, by the words it uses, else the best fit)
    tactics(text)          -> +/- circumstance bonus for HOW the move is described (feint, high ground, flanking... / flailing)
    sheet(profile, name)   -> a short plain-English line for the prompt, so the fight is written with the real techniques and limits

Kinds: melee, ranged, magic, heal, revive, stealth, social, mind, tough, swift, guard.
Pure functions; levels run 1 (novice) to 5 (legendary); an unmarked skill counts as 2.
"""
import re

LEVEL_WORDS = [
    (5, r"legendary|mythic|godlike|ultimate|unmatched|peerless|grandmaster|supreme|world[- ]class|apex|unrivall?ed|transcendent"),
    (4, r"master\w*|expert|elite|exceptional|veteran|prodigy|prodigious|advanced|formidable|deadly|devastating|champion|renowned|incredibly"),
    (3, r"skilled|proficient|adept|trained|capable|competent|practiced|experienced|seasoned|accomplished|talented|gifted|very good|strong"),
    (1, r"novice|beginner|basic|amateur|learning|minor|slight|rusty|untrained|barely|a little|small|weak|apprentice|clumsy"),
]
RANKS = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1, "E": 1, "F": 1}

# tag -> (kinds, regex)
TAGS = {
    "blade": (("melee",), r"sword\w*|fencing|katana|kenjutsu|sabre|saber|rapier|dagger|knife|knives|blade\w*|scimitar|cutlass|claymore|kukri|machete|iaido|kendo"),
    "heavy": (("melee",), r"\baxe\w*|hammer|mace|club\b|greatsword|spear\w*|halberd|\bstaff\b|\bbat\b|maul|lance|polearm|flail|trident|whip"),
    "unarmed": (("melee",), r"martial art\w*|karate|boxing|\bboxer\b|judo|kung ?fu|taekwondo|muay thai|jiu[- ]?jitsu|wrestl\w*|brawl\w*|\bfists?\b|punch\w*|krav maga|capoeira|aikido|unarmed|hand[- ]to[- ]hand|sambo|kickbox\w*|claws?\b|fangs?\b"),
    "bow": (("ranged",), r"archery|archer|\bbows?\b|crossbow|longbow|arrow\w*"),
    "gun": (("ranged",), r"sniper|marksman\w*|sharpshoot\w*|firearms?|pistol|rifle|\bguns?\b|revolver|shotgun|gunslinger|shooting|\bshoot\w*"),
    "throw": (("ranged",), r"throwing|shuriken|kunai|boomerang|sling\b|javelin|darts?\b"),
    "fire": (("magic",), r"fire\w*|flame\w*|pyro\w*|inferno|burn\w*|ember\w*|lava|magma"),
    "ice": (("magic",), r"\bice\b|frost\w*|cryo\w*|freez\w*|blizzard|snow"),
    "lightning": (("magic",), r"lightning|thunder\w*|electric\w*|shock\w*|storm\w*|\bvolt\w*"),
    "wind": (("magic",), r"\bwind\b|air magic|aero\w*|gale|tornado|cyclone"),
    "earth": (("magic",), r"\bearth\b|stone|rock\b|geo\w*|terra\w*|metal bend\w*|crystal"),
    "water": (("magic",), r"\bwater\b|hydro\w*|tide|\bsea\b|wave manip\w*|aqua\w*|liquid"),
    "shadow": (("magic",), r"shadow\w*|dark(?:ness)?\b|umbra\w*|void|night magic"),
    "light": (("magic",), r"\blight magic|holy|radiant|divine|sunfire|celestial|smite"),
    "poison": (("magic",), r"poison\w*|venom\w*|toxin\w*|toxic|acid\b"),
    "blood": (("magic",), r"blood ?(?:magic|bend\w*|manip\w*)|hemo\w*|sanguine"),
    "mind": (("magic",), r"telepath\w*|psychic\w*|telekin\w*|mind control|mind reading|psionic\w*|mental (?:power|blast)|hypno\w*"),
    "illusion": (("magic",), r"illusion\w*|glamou?r|mirage|phantasm\w*|trickster magic"),
    "summon": (("magic",), r"summon\w*|conjur\w*|familiar|spirit (?:pact|bond)"),
    "curse": (("magic",), r"curse\w*|\bhex\w*|jinx|malediction|witchcraft"),
    "time": (("magic",), r"time (?:magic|manip\w*|stop\w*)|chrono\w*|gravity|space (?:magic|manip\w*)|teleport\w*"),
    "arcane": (("magic",), r"\bmagic\w*|\bmage\b|wizard\w*|sorcer\w*|spells?\b|arcane|mystic\w*|supernatural|\bpowers?\b|ability|abilities|\bchi\b|\bki\b|aura|energy blast"),
    "heal": (("heal",), r"heal\w*|medic\w*|doctor|surgeon|surgery|nurse|first aid|cleric|restoration|regenerat\w*|herbalis\w*|apothecary|paramedic|mend\w*"),
    "revive": (("revive",), r"resurrect\w*|reviv\w*|necromanc\w*|raise (?:the )?dead|bring(?:s|ing)? back (?:the )?dead|bring(?:s|ing)? (?:\w+ )?back to life|phoenix|reanimat\w*|life magic|lazarus|\bankh\b|elixir of life|miracle|rebirth"),
    "stealth": (("stealth",), r"stealth\w*|sneak\w*|assassin\w*|\brogue\b|thie(?:f|ves|very)|\bninja\b|shadow ?walk\w*|lock ?pick\w*|pickpocket\w*|infiltrat\w*|spy\b|camouflage"),
    "social": (("social",), r"persuas\w*|charisma\w*|charm\w*|diplomat\w*|negotiat\w*|silver tongue|leader\w*|orator\w*|seduc\w*|manipulat\w*|intimidat\w*|deceiv\w*|bard\b|performer|smooth talk\w*"),
    "wits": (("mind",), r"hack\w*|engineer\w*|inventor|strateg\w*|tactic\w*|genius|detective|scholar|alchemis\w*|chemist|scientist|mechanic\w*|tinker\w*|investigat\w*|survivalist|tracker|brilliant"),
    "tough": (("tough",), r"super ?human strength|giant|\btank\b|\btough\w*|durable|iron skin|unyielding|resilien\w*|immortal|invulnerab\w*|thick skin|endur\w*|stamina|bulletproof|regenerat\w*|powerlift\w*|bodybuild\w*|strong|strength"),
    "swift": (("swift",), r"speed\w*|\bfast\b|agile|agility|acrobat\w*|parkour|nimble|reflex\w*|flexible|quick|swift|dodg\w*|sprint\w*|blink"),
    "guard": (("guard",), r"shield\w*|parry\w*|armou?r\w*|barrier|\bward\b|deflect\w*|defen[cs]e|bulwark|fortif\w*|block\w*"),
}
TAG_RX = {t: re.compile(r"\b(?:%s)" % rx, re.I) for t, (_, rx) in TAGS.items()}
NOUN_KIND = {"melee": ("blade", "heavy", "unarmed"), "ranged": ("bow", "gun", "throw")}
LIM_RX = re.compile(r"(?i)\b(?:weak(?:ness(?:es)?)?\s*(?:to|:)|vulnerab\w*|allerg\w*|afraid of|fear(?:s)? of|phobia|can'?t |cannot |unable to|only works|limit(?:s|ation|ations)?\b|drawback|downside|side effect|cooldown|exhaust\w* (?:after|when)|costs? |sickly|frail|asthma\w*|chronic|blind\b|deaf\b|crippl\w*|one[- ]armed|one[- ]eyed|limp\w*|bad (?:knee|heart|back|lungs?)|weak (?:heart|lungs?|knees?))")
HEAD_RX = re.compile(r"(?i)^\s*(?:skills?|abilities|powers?|talents?|gear|equipment|inventory|weapons?|items?|carries|wears|wielding|has|can|knows|specialt(?:y|ies)|about me)\s*[:\-]\s*")
LVL_NUM = re.compile(r"(?i)\b(?:level|lvl?\.?|lv\.?|tier|rank)\s*[:\-]?\s*([0-9]{1,2}|[SABCDEF])\b")
YEARS = re.compile(r"(?i)\b(\d{1,2})\+?\s*(?:years?|yrs?|decades?)\b")
SPLIT = re.compile(r"[\n;•·|]+|(?:^|\s)[-–—*]\s+|\.\s+(?=[A-Z])")


def _level(clause):
    t = clause or ""
    m = LVL_NUM.search(t)
    if m:
        v = m.group(1).upper()
        if v in RANKS:
            return RANKS[v]
        n = int(v)
        return 1 if n <= 2 else 2 if n <= 4 else 3 if n <= 6 else 4 if n <= 8 else 5
    for lv, rx in LEVEL_WORDS:
        if re.search(r"\b(?:%s)\b" % rx, t, re.I):
            return lv
    y = YEARS.search(t)
    if y:
        n = int(y.group(1))
        return 5 if n >= 25 else 4 if n >= 12 else 3 if n >= 5 else 2
    return 0    # unmarked


AGENT = {"swordsman": "swordsmanship", "swordswoman": "swordsmanship", "swordsmen": "swordsmanship", "archer": "archery", "marksman": "marksmanship", "marksmen": "marksmanship",
         "healer": "healing", "rogue": "roguish stealth", "boxer": "boxing", "wrestler": "wrestling", "fighter": "fighting skill", "mage": "magic", "wizard": "magic",
         "sorcerer": "sorcery", "sorceress": "sorcery", "thief": "thievery", "assassin": "assassin's craft", "ninja": "ninja arts", "brawler": "brawling",
         "hacker": "hacking", "detective": "detective work", "doctor": "medicine", "surgeon": "surgery", "nurse": "nursing", "soldier": "soldiering", "sniper": "sniping",
         "necromancer": "necromancy", "pyromancer": "pyromancy", "cleric": "clerical magic", "bard": "a bard's craft", "duelist": "duelling", "gunslinger": "gunslinging"}


def _clean_name(c):
    t = HEAD_RX.sub("", c or "")
    t = re.sub(r"(?i)^\s*\d{1,2}\+?\s*(?:years?|yrs?|decades?)\s*(?:of\s+)?(?:experience\s+(?:in|with)\s+)?", "", t)
    t = LVL_NUM.sub("", t)
    t = re.sub(r"(?i)\b(?:%s)\b" % "|".join(rx for _, rx in LEVEL_WORDS), "", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"(?i)^\s*(?:and|a|an|the|of|in|with|can|able to)\b\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip(" .,:;-–—()'\"")[:46]
    low = t.lower()
    for k, v in AGENT.items():
        if low == k or low == "a " + k or low == "the " + k:
            return v
    return t


def _clauses(text):
    out = []
    for line in SPLIT.split(text or ""):
        line = HEAD_RX.sub("", line.strip())
        if not line:
            continue
        parts = [p.strip() for p in re.split(r",\s*(?![^()]*\))|\s+and\s+(?=[A-Za-z]+\s)", line)] if len(line) < 220 else [line]
        base = _level(line) if len(parts) > 1 and not any(_level(p) for p in parts) else 0
        out += [(p, base) for p in parts if len(p) > 2]
    return out


def parse(skills="", gear=""):
    """Read the description. Skills come from the skills text; gear adds weapon, armour and item techniques at level 2."""
    techs, lim, weak = [], [], set()
    for src, text in (("skill", skills), ("gear", gear)):
        for clause, inherited in _clauses(text):
            if LIM_RX.search(clause):
                lim.append(re.sub(r"\s+", " ", clause).strip(" .")[:90])
                for t, rx in TAG_RX.items():
                    if t not in ("arcane", "mind", "wits") and rx.search(clause):
                        weak.add(t)
                continue
            tags = [t for t, rx in TAG_RX.items() if rx.search(clause)]
            if "arcane" in tags and len(tags) > 1:
                tags.remove("arcane")      # "fire magic" is fire, not generic arcane
            if not tags:
                continue
            kinds = []
            for t in tags:
                for k in TAGS[t][0]:
                    if k not in kinds:
                        kinds.append(k)
            lv = _level(clause) or inherited or 2
            techs.append({"name": _clean_name(clause) or tags[0], "kinds": kinds, "tags": tags, "level": lv, "src": src})
    seen, uniq = set(), []
    for t in sorted(techs, key=lambda x: -x["level"]):
        key = (t["name"].lower(), tuple(t["kinds"]))
        if key not in seen:
            seen.add(key)
            uniq.append(t)
    lvl = {}
    for t in uniq:
        for k in t["kinds"]:
            lvl[k] = max(lvl.get(k, 0), t["level"])
    return {"techs": uniq[:14], "lim": lim[:6], "weak": sorted(weak), "lvl": lvl}


ATK = [0, 1, 2, 3, 5, 7]
HPB = [0, 2, 4, 6, 9, 12]
GRD = [0, 1, 1, 2, 3, 4]


def derive(p):
    """The numbers the described skills grant. Nothing here is random."""
    L = (p or {}).get("lvl") or {}
    g = lambda k: L.get(k, 0)
    return {"melee": ATK[g("melee")], "ranged": ATK[g("ranged")], "magic": ATK[g("magic")], "guard": GRD[g("guard")],
            "hp": HPB[g("tough")], "init": g("swift"), "dodge": g("swift") // 2, "aid": ATK[g("heal")], "revive": g("revive"),
            "stealth": ATK[g("stealth")], "social": ATK[g("social")], "wits": ATK[g("mind")]}


ACT_KIND = {"attack": ("melee", "ranged"), "special": ("magic",), "defend": ("guard", "swift"), "flee": ("swift", "stealth"), "heal": ("heal",),
            "intimidate": ("social", "tough"), "persuade": ("social",), "deceive": ("social", "stealth"), "comfort": ("social", "heal"),
            "sneak": ("stealth",), "steal": ("stealth",), "athletics": ("swift", "tough"), "investigate": ("mind",), "craft": ("mind",),
            "revive": ("revive",)}


def pick(p, text, act):
    """Which technique is this action using? Named in the text first, then by the words it uses, then the best fit for the act."""
    techs = (p or {}).get("techs") or []
    if not techs:
        return None
    low = (text or "").lower()
    words = set(re.findall(r"[a-z]{4,}", low))
    want = ACT_KIND.get(act, ())
    best, score = None, 0.0
    for t in techs:
        s = 0.0
        nw = set(re.findall(r"[a-z]{4,}", t["name"].lower()))
        if t["name"].lower() in low:
            s += 6
        s += 2.5 * len(nw & words)
        s += 2 * sum(1 for g in t["tags"] if TAG_RX[g].search(low))
        if any(k in want for k in t["kinds"]):
            s += 1.5
        s += t["level"] * .15
        if s > score:
            best, score = t, s
    return best if best and (score >= 1.6 or any(k in want for k in best["kinds"])) else None


TACT_POS = re.compile(r"(?i)\b(?:feint\w*|flank\w*|from behind|behind (?:him|her|them)|from above|high ground|distract\w*|throw\w* (?:sand|dust|a)|use[sd]? the (?:pillar|table|wall|door|shadows?|crowd|terrain|environment)|aim\w* for|target\w* the|exploit\w*|counter\w*|timing|timed|surprise\w*|ambush\w*|stun\w*|disarm\w*|sweep\w*|trip\w*|pin\w*|bait\w*|cover(?:ing)?|crouch\w*|duck\w* behind|feign\w*|wait\w* for (?:an|the) opening|read\w* (?:his|her|their) (?:movement|stance|moves))\b")
TACT_NEG = re.compile(r"(?i)\b(?:recklessly|blindly|wildly|flail\w*|without (?:looking|thinking|aiming)|haphazard\w*|stumbl\w*|panick\w*|desperate\w*)\b")


def tactics(text):
    """Describing HOW a move is made counts: a feint, the high ground or a well-timed counter helps; flailing wildly does not."""
    t = text or ""
    return max(-2, min(3, len(set(m.lower() for m in TACT_POS.findall(t))) - len(set(m.lower() for m in TACT_NEG.findall(t)))))


LV_TXT = {1: "novice", 2: "capable", 3: "skilled", 4: "master-level", 5: "legendary"}


def sheet(p, name):
    """One compact plain-English line (no numbers) for the prompt: what this person can really do, and what limits them."""
    techs = (p or {}).get("techs") or []
    if not techs and not (p or {}).get("lim"):
        return ""
    bits = [f"{t['name']} ({LV_TXT.get(t['level'], 'capable')}, {'/'.join(t['kinds'][:2])})" for t in techs[:6]]
    s = f"{name} can really do: " + "; ".join(bits) + "." if bits else ""
    if p.get("lim"):
        s += f" Limits and weaknesses: {'; '.join(p['lim'][:3])}."
    return s.strip()


def has_revive(p):
    return derive(p)["revive"]
