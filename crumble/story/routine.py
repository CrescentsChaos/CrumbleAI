"""Daily routines. Every character has a day: they sleep, wake up groggy, commute, work, eat, slump in the afternoon, relax and wind down.

The routine comes from the sheet, with no model call: the author's own "Daily routine" field wins ("Weekdays: up 6:30, bakery 7-3, gym 5pm, in bed
by 11. Weekends: sleeps in"), otherwise it is guessed from occupation and description (student, teacher, nurse, baker, guard, artist...), shifted
for night owls and early birds. The routine is the character's USUAL rhythm: whatever the story has established still wins over it.

    schedule(c, daykind)        -> 48 half-hour slots, each (key, custom_label or "")
    now(c, sim)                 -> what they are doing right now, how free they are, what comes next, what they did earlier; None without a story clock
    ACT                         activity key -> (label, state, how free to talk 0..1)
Pure functions, nothing is stored: the same chat always gives the same answer, so swipes and rewinds can never leave it stale.
"""
import re

ACT = {
    "sleep": ("asleep", "asleep", 0.0), "wake": ("waking up and getting ready", "groggy", .45), "breakfast": ("having breakfast", "free", .8),
    "commute": ("on the way somewhere", "moving", .6), "work": ("at work", "busy", .35), "class": ("in class or studying", "busy", .35),
    "lunch": ("on a lunch break", "free", .85), "break": ("taking a short break", "free", .75), "errands": ("running errands", "moving", .6),
    "exercise": ("exercising", "busy", .4), "dinner": ("cooking and eating dinner", "free", .75), "chores": ("doing chores around the home", "free", .7),
    "hobby": ("busy with a hobby or a project of their own", "free", .8), "social": ("out with friends or family", "free", .6),
    "relax": ("relaxing", "free", .95), "winddown": ("winding down for bed", "winding", .7), "shift": ("on shift", "busy", .3),
    "nap": ("taking a nap", "asleep", .1), "custom": ("", "free", .7),
}
STATE_HINT = {
    "asleep": "this is when they would normally be asleep",
    "groggy": "slow, not fully awake, hair a mess, still on the first coffee or the first yawn",
    "busy": "their attention is half on what they are doing; they can talk, but in short bursts, glancing at the time, interrupted now and then",
    "moving": "they are on the move, so they talk in passing, a bit distracted by the way, the crowd, their bags",
    "free": "they have the time and headspace to talk properly",
    "winding": "they are slowing down: quieter, softer, more honest, with the day finally off their shoulders",
}

# archetype name -> (regex over the sheet, wake, bed, core block (start, end, key) or None, weekend core or None, label of the core)
ARCH = [
    ("student", r"\b(?:student|university|college|school(?:girl|boy)?|undergrad\w*|freshman|sophomore|pupil|classmates?|lectures?|academy|campus|exam\w*)\b", 7.5, 24.0, (9, 16, "class"), None, "in class"),
    ("teacher", r"\b(?:teacher|professor|lecturer|tutor|instructor|headmaster|headmistress|principal)\b", 6.5, 22.5, (8, 16, "work"), None, "teaching"),
    ("healthcare", r"\b(?:nurse|doctor|surgeon|paramedic|medic|physician|healer|pharmacist|midwife|vet(?:erinarian)?|clinic|hospital)\b", 6.0, 22.5, (7, 17, "shift"), (8, 16, "shift"), "on shift at the clinic or ward"),
    ("nightlife", r"\b(?:bartender|dj|nightclub|club owner|bouncer|night[- ]shift|night owl|stripper|burlesque|pub owner|croupier|casino)\b", 13.0, 6.0, (20, 28, "work"), (20, 28, "work"), "working the night"),
    ("food", r"\b(?:barista|chef|cook|baker|waiter|waitress|innkeeper|tavern ?keeper|brewer|caf[eé] owner|restaurant|bakery|kitchen staff|pastry)\b", 5.5, 22.0, (7, 15, "work"), (8, 16, "work"), "working the counter or kitchen"),
    ("retail", r"\b(?:shopkeeper|cashier|clerk|merchant|vendor|salesperson|salesman|saleswoman|receptionist|store owner|shop owner|stall)\b", 7.0, 23.0, (9, 18, "work"), (10, 17, "work"), "minding the shop"),
    ("trades", r"\b(?:mechanic|builder|carpenter|plumber|electrician|farmer|blacksmith|smith|fisher\w*|miner|driver|courier|labou?rer|lumberjack|dock ?worker|herder|shepherd|rancher)\b", 5.5, 22.0, (7, 16, "work"), None, "on the job"),
    ("security", r"\b(?:guard|police|cop|detective|officer|soldier|knight|sentinel|bodyguard|ranger|warden|sheriff|military|captain|patrol|marshal|guardsman)\b", 6.0, 22.5, (8, 18, "shift"), (9, 17, "shift"), "on duty"),
    ("creative", r"\b(?:artist|writer|author|painter|musician|streamer|designer|photographer|poet|bard|freelanc\w*|game dev\w*|youtuber|illustrator|composer|novelist|animator)\b", 9.5, 1.5, (11, 18, "hobby"), (12, 18, "hobby"), "working on their craft"),
    ("office", r"\b(?:engineer|developer|programmer|manager|accountant|lawyer|attorney|analyst|consultant|executive|ceo|banker|office|scientist|researcher|journalist|editor|administrator|secretary|assistant|hacker|coder)\b", 7.0, 23.0, (9, 17.5, "work"), None, "at work"),
    ("noble", r"\b(?:noble|prince|princess|king|queen|lord|lady|heir|heiress|aristocrat|royal|duke|duchess|baron|emperor|empress)\b", 8.0, 23.5, (10, 17, "work"), (11, 16, "social"), "attending to their duties"),
    ("retired", r"\b(?:retired|homemaker|housewife|house-?husband|stay-at-home|grandma|grandpa|grandmother|grandfather|pensioner|widow\w*|elderly)\b", 6.5, 22.0, None, None, ""),
    ("default", r"", 7.5, 23.5, (9, 17, "work"), None, "busy with their day"),
]
EARLY = re.compile(r"(?i)\b(?:early (?:bird|riser)s?|morning person|up (?:at|before) dawn|lark|wakes? (?:up )?early|up with the sun)\b")
LATE = re.compile(r"(?i)\b(?:night owl|nocturnal|insomni\w*|stays? up late|sleeps? in|not a morning person|hates mornings|vampire|never sleeps)\b")
ANDI = re.compile(r"(?i)\b(?:no job|jobless|unemployed|between jobs|drifter|wanderer|vagabond|hermit|on holiday|on vacation|on leave|day off)\b")
WEEKEND = {5, 6}


def pick_arch(c):
    blob = " ".join(str(c.get(k) or "") for k in ("occupation", "tags")) + " " + " ".join(str(c.get(k) or "")[:260] for k in ("description", "skills", "backstory", "personality"))
    occ = str(c.get("occupation") or "").lower()
    for name, rx, *rest in ARCH:
        if name != "default" and re.search(rx, occ):
            return next(a for a in ARCH if a[0] == name), blob
    for name, rx, *rest in ARCH:
        if name != "default" and re.search(rx, blob.lower()):
            return next(a for a in ARCH if a[0] == name), blob
    return ARCH[-1], blob


def _slots():
    return [("relax", "")] * 48


def _fill(sl, s, e, key, label="", only_over=None):
    """Write an activity into the half-hour slots from s to e (hours; e may run past 24 or be less than s: it wraps)."""
    if e <= s:
        e += 24
    a, b = int(round(s * 2)), int(round(e * 2))
    for i in range(a, b):
        j = i % 48
        if only_over is None or sl[j][0] in only_over:
            sl[j] = (key, label)


def _template(arch, weekend, shift, minimal=False):
    name, _, wake, bed, core, wcore, label = arch
    sl = _slots()
    wake, bed = wake + shift, bed + shift
    core = (wcore if weekend else core)
    if weekend and wcore is None:
        wake, bed = wake + 1.5, bed + .5
    if minimal:     # the author wrote this day out themselves: only the basics of a day stay, everything else is theirs
        core = None
    _fill(sl, bed, wake, "sleep")
    _fill(sl, wake, wake + .75, "wake")
    _fill(sl, wake + .75, wake + 1.25, "breakfast")
    if core:
        s, e, key = core
        s, e = s + (shift if name in ("creative", "student") and not weekend else 0), e
        _fill(sl, s - .5, s, "commute", only_over={"relax", "breakfast", "wake"}) if key != "hobby" else None
        _fill(sl, s, e, key, label if key not in ("class",) else "")
        if e - s >= 6 and key != "hobby":
            mid = s + (e - s) / 2 - .25
            _fill(sl, mid, mid + .75, "lunch")
        elif key == "hobby":
            _fill(sl, s + (e - s) / 2 - .25, s + (e - s) / 2 + .5, "lunch")
        _fill(sl, e, e + .5, "commute", only_over={"relax"}) if key != "hobby" else None
        after = e + .5
    elif minimal:
        after = 24
    else:
        _fill(sl, wake + 1.25, wake + 3.5, "chores" if name == "retired" else "errands", only_over={"relax"})
        _fill(sl, 12.5, 13.5, "lunch", only_over={"relax"})
        after = 15.5
    if weekend and not core and not minimal:
        _fill(sl, 11, 13, "social", only_over={"relax"})
        _fill(sl, 12.75, 13.5, "lunch")
    dn = 18.5 + (shift / 2 if abs(shift) < 3 else 0)
    if after < dn - 1.5:
        _fill(sl, after, after + 1.5, "exercise" if name in ("student", "office", "retail", "teacher", "healthcare") and not weekend else "errands", only_over={"relax"})
    _fill(sl, dn, dn + 1.25, "dinner", only_over={"relax"})
    if name == "nightlife":
        _fill(sl, dn + 1.25, 20, "hobby", only_over={"relax"})
    _fill(sl, bed - 1.25, bed, "winddown", only_over={"relax", "dinner", "hobby", "social"})
    # the free evening: a mix, not one long "relaxing"
    for i in range(48):
        h = i / 2
        if sl[i][0] == "relax" and 14 <= h < 17.5:
            sl[i] = ("break" if weekend else "relax", "")
        if sl[i][0] == "relax" and 20 <= h < bed - 1.25 + (24 if bed < 12 else 0):
            sl[i] = ("hobby" if (i % 4 < 2 and weekend) else "relax", "")
    return sl


# ------------------------------------------------------------ the author's own routine text
_TM = r"(?P<{p}h>\d{{1,2}})(?::(?P<{p}m>\d{{2}}))?\s*(?P<{p}a>a\.?m\.?|p\.?m\.?)?(?![\w:])"
_RANGE = re.compile(r"(?<![\w:])" + _TM.format(p="a") + r"\s*(?:-|\u2013|\u2014|to|until|till|til)\s*" + _TM.format(p="b"), re.I)
_TIME = re.compile(r"(?<![\w:])(?:(?P<w>midnight|noon|dawn|sunrise|sunset|dusk)|" + _TM.format(p="a") + r")", re.I)
_UNTIL = re.compile(r"(?i)\b(?:till|until|til|by|before)\s*$")
_DAYS = re.compile(r"(?i)\b(weekdays?|weekends?|workdays?|mondays?|tuesdays?|wednesdays?|thursdays?|fridays?|saturdays?|sundays?|every day|daily)\b")
_WORDHRS = {"midnight": 0.0, "noon": 12.0, "dawn": 5.5, "sunrise": 6.0, "sunset": 18.5, "dusk": 18.5}
_PERIOD = [(r"\bearly morning\b", 6, 9), (r"\bmornings?\b", 8, 12), (r"\bafternoons?\b", 12.5, 17), (r"\bevenings?\b", 18, 22), (r"\bnights?\b|\bat night\b", 21, 24)]
DUR = {"sleep": 8, "nap": 1, "wake": .75, "breakfast": .5, "lunch": .75, "dinner": 1.25, "commute": .5, "class": 3, "exercise": 1.5, "shift": 4, "work": 4,
       "errands": 1.5, "chores": 1.5, "social": 3, "hobby": 2, "winddown": 1, "relax": 2, "break": .5, "custom": 1.5}
KEYWORDS = [
    ("nap", r"\bnaps?\b"), ("sleep", r"\b(?:sleep\w*|asleep|in bed|bed|bed ?time|lights out|goes to bed|turns in)\b"),
    ("wake", r"\b(?:wak\w+|gets? up|\bup\b|rises?|alarm|gets? ready|shower\w*|morning routine)\b"), ("breakfast", r"\bbreakfast|brunch\b"),
    ("lunch", r"\blunch\b"), ("dinner", r"\b(?:dinner|supper|cooks?|cooking|evening meal)\b"),
    ("commute", r"\b(?:commut\w+|bus|train|subway|metro|drives? to|walks? to|rides? to|travel\w*|heads? (?:out|to))\b"),
    ("class", r"\b(?:class\w*|lectures?|school|university|college|studies|studying|lessons?|seminar|exam)\b"),
    ("exercise", r"\b(?:gym|run\w*|jog\w*|workout|trains?|training|exercis\w+|yoga|swim\w*|sparring|drills?)\b"),
    ("shift", r"\b(?:shift|on duty|patrol|rounds|ward|clinic|guard duty|watch)\b"),
    ("errands", r"\b(?:errands?|shopping|groceries|market|bank|post office)\b"), ("chores", r"\b(?:chores?|clean\w*|laundry|tidy\w*|dishes|housework|garden\w*)\b"),
    ("work", r"\b(?:work\w*|job|office|shop|store|caf[e\u00e9]|bakery|kitchen|counter|forge|farm\w*|field|site|meetings?|deliver\w*|opens?|customers?|clients?|bar|serv\w+|restaurant|studio|garage)\b"),
    ("social", r"\b(?:friends?|family|dates?|party|parties|drinks|pub|hang\w* out|visits?|church|temple|mosque|dance|club|social\w*)\b"),
    ("winddown", r"\b(?:wind\w* down|unwind\w*|bath|skincare)\b"),
    ("hobby", r"\b(?:hobby|paint\w*|writ\w+|read\w*|gam(?:e|es|ing)|stream\w*|practis\w+|practice|music|guitar|piano|draw\w*|craft\w*|tinker\w*|project|cod(?:e|ing))\b"),
    ("relax", r"\b(?:relax\w*|tv|netflix|chill\w*|free time|couch|sofa|watch\w*)\b"), ("break", r"\b(?:break|coffee|smoke|snack)\b"),
    ("dinner", r"\b(?:eats?|meal|food)\b"),
]


def _hour(h, m, ap):
    h = int(h)
    ap = (ap or "").lower().replace(".", "")
    if ap.startswith("p") and h < 12:
        h += 12
    elif ap.startswith("a") and h == 12:
        h = 0
    return h + int(m or 0) / 60


def _bare(h, key):
    """A time written with no am/pm ('gym at 5', 'in bed by 11'): which half of the day is meant depends on what it is."""
    if h >= 13 or h == 0:
        return h % 24
    if key == "sleep":
        return h + 12 if 8 <= h <= 11 else h if h <= 5 else (0.0 if h == 12 else h + 12)
    if key in ("dinner", "social", "relax", "hobby", "exercise", "winddown", "errands", "break") and 1 <= h <= 9:
        return h + 12
    if key == "lunch" and h < 11:
        return h + 12 if h < 6 else h
    return h


def _keyfor(what):
    w = what.lower()
    for k, rx in KEYWORDS:
        if re.search(rx, w):
            return k
    return "custom"


def _label(what):
    w = re.sub(r"(?i)^\s*(?:then|and|she|he|they|goes|go|is|are|to|at|from|by|till|until)\s+", "", what)
    w = re.sub(r"\s+", " ", w).strip(" ,.;:-")
    return w[:60]


def parse_author(text):
    """The author's own routine -> {"weekday": [(s, e, key, label)], "weekend": [...]}. Understands '7-3 bakery', 'bakery 7-3', '6:30am wake up',
    'in bed by 11', 'sleeps in till 10', 'friends in the evening', and groups ('Weekdays: ... Weekends: ...'; text before a group name is for every day)."""
    out = {"weekday": [], "weekend": []}
    text = (text or "").strip()
    if len(text) < 6:
        return out
    both = ("weekday", "weekend")
    marks = [(m.start(), m.group(1).lower()) for m in _DAYS.finditer(text)]
    parts = []
    if not marks:
        parts = [(text, both)]
    else:
        if marks[0][0] > 0:
            parts.append((text[:marks[0][0]], both))
        for i, (pos, nm) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            scope = ("weekend",) if nm.startswith(("weekend", "saturday", "sunday")) else ("weekday",) if nm.startswith(("weekday", "workday", "monday", "tuesday", "wednesday", "thursday", "friday")) else both
            parts.append((text[pos:end], scope))
    for seg, scope in parts:
        seg = _DAYS.sub(" ", seg)
        for clause in re.split(r"[,;.\n]+|\band then\b|\bthen\b", seg):
            clause = clause.strip()
            if len(clause) < 3:
                continue
            blk = None
            m = _RANGE.search(clause)
            if m:
                rest = clause[:m.start()] + " " + clause[m.end():]
                key = _keyfor(rest)
                ap = m["aa"] or m["ba"]
                a = _hour(m["ah"], m["am"], m["aa"] or m["ba"]) if ap else _bare(int(m["ah"]) + int(m["am"] or 0) / 60, key)
                b = _hour(m["bh"], m["bm"], m["ba"] or m["aa"]) if ap else _bare(int(m["bh"]) + int(m["bm"] or 0) / 60, key)
                if not ap and b <= a and b < 12:
                    b += 12
                if not ap and a < 7 and key not in ("sleep", "wake") and b > a + 9:
                    a += 12
                blk = (a, b, key, _label(rest) if key in ("custom", "work", "shift", "class") else "")
            else:
                t = _TIME.search(clause)
                if t:
                    rest = clause[:t.start()] + " " + clause[t.end():]
                    key = _keyfor(rest)
                    if t["w"]:
                        h = _WORDHRS[t["w"].lower()]
                    elif t["aa"] or t["aa"] == "" and t["am"]:
                        h = _hour(t["ah"], t["am"], t["aa"])
                    else:
                        h = None
                    until = bool(_UNTIL.search(clause[:t.start()])) and "by" not in clause[max(0, t.start() - 5):t.start()].lower()
                    if h is None:
                        h = _bare(int(t["ah"]) + int(t["am"] or 0) / 60, "wake" if (key == "sleep" and until) else key)
                    if key == "sleep" and until:
                        blk = (0.0, h, "sleep", "")
                    else:
                        blk = (h, h + DUR.get(key, 1.5), key, _label(rest) if key in ("custom", "work", "shift", "class") else "")
                else:
                    for rx, a, b in _PERIOD:
                        if re.search(rx, clause, re.I):
                            rest = re.sub(rx, " ", clause, flags=re.I)
                            kk = _keyfor(rest)
                            blk = (a, b, kk, _label(rest) if kk in ("custom", "work", "shift", "class") else "")
                            break
            if blk:
                for sc in scope:
                    out[sc].append(blk)
    return out


def schedule(c, weekend=False):
    arch, blob = pick_arch(c)
    routine = str(c.get("routine") or "")
    shift = 0.0
    if EARLY.search(blob + " " + routine):
        shift = -1.5
    elif LATE.search(blob + " " + routine):
        shift = 2.0
    if ANDI.search(blob) and arch[0] == "default":
        arch = ("drifter",) + arch[1:4] + (None, None, "")
    au = parse_author(routine)
    blocks = au["weekend" if weekend else "weekday"]
    sl = _template(arch, weekend, shift, minimal=len(blocks) >= 2)
    for s, e, k, lab in sorted(blocks, key=lambda x: (x[2] != "sleep",)):
        _fill(sl, s, e, k, lab)
    return sl, arch[0], bool(blocks), (arch[6] if len(arch) > 6 else "")


def _label_of(slot, arch_label, occ, hour=12.0):
    key, lab = slot
    if key == "lunch" and (hour < 5 or hour >= 22):
        return "on a break"
    if lab and key in ("work", "shift", "class"):
        return lab if re.match(r"(?i)(?:at|in|on|working|teaching|serving|studying)\b", lab) or lab.lower() in ("work", "shift", "class", "classes") else f"working ({lab})"
    if lab:
        return lab
    if key in ("work", "shift") and occ and len(occ) <= 36:
        return {"work": f"at work ({occ})", "shift": f"on shift ({occ})"}[key]
    if key in ("work", "shift") and arch_label:
        return arch_label
    return ACT.get(key, ACT["custom"])[0]


def _run(sl, i):
    """(first slot, last slot + 1) of the block that contains slot i (the same activity and label), wrapping around midnight."""
    a = i
    while sl[(a - 1) % 48] == sl[i] and (i - a) < 47:
        a -= 1
    b = i + 1
    while sl[b % 48] == sl[i] and (b - i) < 48:
        b += 1
    return a, b


def now(c, sim, hour=None):
    """What this character is doing at the story's current hour. None when the story has no clock."""
    if not sim:
        return None
    h = float(sim["hour"] if hour is None else hour) % 24
    dn = sim.get("dayn")
    weekend = (dn % 7 in WEEKEND) if dn is not None else False
    if hour is not None and dn is not None and sim["hour"] < hour:
        weekend = ((dn - 1) % 7 in WEEKEND)
    sl, arch, own, alabel = schedule(c, weekend)
    occ = str(c.get("occupation") or "").strip()
    i = int(h * 2) % 48
    key, lab = sl[i]
    a, b = _run(sl, i)
    nk = sl[b % 48]
    mins_left = int(round(((b * 30) - h * 60) % 1440)) or 30
    label = _label_of(sl[i], alabel, occ, h)
    state, free = ACT.get(key, ACT["custom"])[1:]
    if key == "custom":
        state = "busy" if re.search(r"(?i)\b(?:work|shift|class|meeting|study|serving|practice|train|duty|patrol|lesson)\b", lab) else "free"
        free = .35 if state == "busy" else .75
    # what they did earlier today, in order (distinct, from the start of the waking day)
    earlier, seen = [], set()
    wake_i = next((j for j in range(48) if sl[j][0] == "wake"), 0)
    for j in range(wake_i, i):
        k2, l2 = sl[j]
        lb = _label_of(sl[j], alabel, occ, j / 2)
        if k2 not in ("sleep", "relax") and lb not in seen and lb != label:
            seen.add(lb)
            earlier.append(lb)
    return {"key": key, "label": label, "state": state, "free": free, "mins_left": mins_left, "next": _label_of(nk, alabel, occ, (b / 2) % 24), "next_key": nk[0],
            "earlier": earlier[-4:], "weekend": weekend, "arch": arch, "own": own, "hour": h, "block": (a / 2 % 24, b / 2 % 24)}


def chrono(c):
    """Hours a night owl (+) or an early bird (-) is offset from an ordinary day."""
    blob = " ".join(str(c.get(k) or "") for k in ("personality", "description", "quirks", "routine", "backstory"))[:1500]
    return -1.5 if EARLY.search(blob) else 2.0 if LATE.search(blob) else 0.0
