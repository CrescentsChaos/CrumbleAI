"""Story time. The clock the character lives by is the one the STORY established, not the computer's wall clock.

A scene that opens on 'Monday morning' and then says 'three hours later, in the library' is at about noon on Monday, even if
the person is really chatting at 2 a.m. The clock is derived from the whole chat every turn (scenario, every message,
then the author's setting notes), the same way the identity ledger is, so edits, swipes and rewinds can never leave it stale.

    derive(messages, scenario='', notes=()) -> None when the story never says what time it is (the caller then falls
                                               back to the real clock), else
        {'clock': 'Monday, around 12:05 PM (midday)', 'period': 'midday', 'daytime': True, 'elapsed': seconds since the
         previous message, 'hour': 12.08, 'day': 'Monday' or ''}
    guide(sim, name)    prompt text telling the character what time of day it is, in story terms
    time_note(text, sim) a note for a retry when a reply contradicts the story clock (night talk at noon), else ''
Pure functions, no imports from the rest of the package."""
import re

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TICK = 1.0   # story minutes that pass with every message when nothing says otherwise

NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
       "ten": 10, "eleven": 11, "twelve": 12, "half an": .5, "half": .5, "a couple of": 2, "couple of": 2, "a few": 3, "few": 3,
       "several": 4, "fifteen": 15, "twenty": 20, "thirty": 30, "forty-five": 45, "forty five": 45}
_N = r"(?:\d+(?:\.\d+)?|" + "|".join(sorted((re.escape(k) for k in NUM), key=len, reverse=True)) + r")"
_U = r"(?:minutes?|mins?|hours?|hrs?|days?)"
PERIOD_HOUR = [("early morning", 7), ("morning", 9), ("dawn", 6), ("sunrise", 6), ("noon", 12), ("midday", 12), ("lunchtime", 12.5),
               ("lunch", 12.5), ("afternoon", 15), ("dusk", 18.5), ("sunset", 18.5), ("evening", 19), ("tonight", 21),
               ("late at night", 23.5), ("midnight", 24), ("night", 22)]
_P = "|".join(re.escape(k) for k, _ in sorted(PERIOD_HOUR, key=lambda x: -len(x[0])))
TOKEN = re.compile(
    rf"(?P<clock>\b(?:at\s+)?(?P<h>\d{{1,2}})(?::(?P<m>\d{{2}}))?\s*(?P<ap>am|pm|a\.m\.|p\.m\.)(?!\w)|\bat\s+(?P<h24>[01]?\d|2[0-3]):(?P<m24>[0-5]\d)\b)"
    rf"|(?P<rel>\b(?P<n>{_N})\s+(?P<u>{_U})\s+(?:later|passes|pass|go\s+by|goes\s+by|went\s+by|had\s+passed|have\s+passed|passed)\b"
    rf"|\bafter\s+(?P<n2>{_N})\s+(?P<u2>{_U})\b)"
    rf"|(?P<skip>\b(?:the\s+)?(?:next|following)\s+(?P<sk>morning|day|evening|afternoon|night)\b|\b(?:later\s+)?that\s+(?P<sk2>morning|afternoon|evening|night)\b"
    rf"|\btime\s*skip(?:ped)?\s+(?:to|until)\s+(?:the\s+)?(?P<sk3>morning|noon|midday|afternoon|evening|night|midnight|{'|'.join(d.lower() for d in DAYS)})\b)"
    rf"|(?P<day>\b(?:{'|'.join(d.lower() for d in DAYS)})\b)"
    rf"|(?P<per>\b(?:{_P})\b)", re.I)
NOT_A_CLOCK = {"last", "yesterday", "every", "each", "one", "some", "tomorrow", "all", "whole", "good", "this", "early"}


def _num(s):
    s = (s or "").lower().strip()
    return float(s) if re.fullmatch(r"\d+(?:\.\d+)?", s) else NUM.get(s, 1)


def _hour_of(word):
    word = word.lower()
    return next((h for k, h in PERIOD_HOUR if k == word), None)


class _Clock:
    def __init__(self):
        self.t = None        # story minutes since a Monday 00:00; None until the story says what time it is
        self.day_known = False
        self.moved = False

    def _set_time(self, hour, forward=True):
        d0 = 0 if self.t is None else int(self.t // 1440) * 1440
        cand = d0 + hour * 60
        if self.t is not None and forward and cand < self.t - 90:   # an earlier time of day than now = the next day
            cand += 1440
        self.t, self.moved = cand, True

    def _set_day(self, w):
        base = 0 if self.t is None else int(self.t // 1440)
        tod = 9 * 60 if self.t is None else self.t % 1440
        target = base - base % 7 + w
        if target < base and self.day_known:
            target += 7
        self.t, self.day_known, self.moved = target * 1440 + tod, True, True

    def _add(self, minutes):
        if self.t is not None:
            self.t += minutes
            self.moved = True

    def feed(self, text, tick=True):
        self.moved = False
        text = text or ""
        for m in TOKEN.finditer(text):
            g = m.lastgroup
            if m["clock"]:
                if m["ap"]:
                    h = int(m["h"]) % 12 + (12 if m["ap"].lower().startswith("p") else 0)
                    self._set_time(h + int(m["m"] or 0) / 60)
                else:
                    self._set_time(int(m["h24"]) + int(m["m24"]) / 60)
            elif m["rel"]:
                n, u = _num(m["n"] or m["n2"]), (m["u"] or m["u2"]).lower()
                self._add(n * (1440 if u.startswith("d") else 60 if u.startswith("h") else 1))
            elif m["skip"]:
                w = (m["sk"] or m["sk2"] or m["sk3"] or "").lower()
                if w in ("day",):
                    self._add(1440)
                elif w in [d.lower() for d in DAYS]:
                    self._set_day(DAYS.index(w.capitalize()))
                    self._set_time(9)
                elif w and self.t is not None:
                    h = _hour_of(w) or 9
                    if "next" in m[0].lower() or "following" in m[0].lower():   # 'the next morning': tomorrow, not later today
                        self.t, self.moved = (int(self.t // 1440) + 1) * 1440 + h * 60, True
                    else:
                        self._set_time(h, forward=True)
            elif g == "day":
                self._set_day([d.lower() for d in DAYS].index(m[0].lower()))
            elif g == "per":
                prev = re.findall(r"[a-z']+", text[:m.start()].lower())[-1:]
                if prev and prev[0] in NOT_A_CLOCK and prev[0] != "this" and prev[0] != "good" and prev[0] != "early":
                    continue
                h = _hour_of(m[0])
                if h is not None:
                    self._set_time(h)
        if tick and not self.moved:
            self._add(TICK)


def _period(h):
    return ("late at night" if h < 5 else "early morning" if h < 7 else "morning" if h < 11 else "midday" if h < 13.5 else
            "afternoon" if h < 17 else "early evening" if h < 19 else "evening" if h < 21 else "night")


def derive(messages, scenario="", notes=()):
    """messages: [{'role','content'}] in order (the whole in-character chat). notes: the author's notes [{'kind','text'}]."""
    c = _Clock()
    c.feed(scenario, tick=False)
    before = None
    msgs = [m for m in (messages or []) if (m.get("content") or "").strip()]
    for i, m in enumerate(msgs):
        if i == len(msgs) - 1:
            before = c.t
        txt = re.sub(r"<think>.*?(?:</think>|$)", "", m["content"], flags=re.S)
        c.feed(txt, tick=c.t is not None)
    for n in notes or []:
        if n.get("kind") in ("setting", "direct", "correct") or not n.get("kind"):
            c.feed(n.get("text", ""), tick=False)
    if c.t is None:
        return None
    elapsed = max(0.0, (c.t - before) * 60) if before is not None else 0.0
    hr = (c.t % 1440) / 60
    mins = int(round((c.t % 1440) / 5.0) * 5) % 1440
    h12 = (mins // 60) % 12 or 12
    stamp = f"{h12}:{mins % 60:02d} {'AM' if mins // 60 < 12 else 'PM'}"
    day = DAYS[int(c.t // 1440) % 7] if c.day_known else ""
    per = _period(hr)
    return {"clock": (f"{day}, " if day else "") + f"around {stamp} ({per})", "period": per, "daytime": 5 <= hr < 19,
            "night": hr >= 21 or hr < 5, "elapsed": elapsed, "hour": hr, "day": day}


def guide(sim, name="the character"):
    """The prompt line. It says what time it is in the story and that the real-world time does not exist for the character."""
    s = f"Story time: {sim['clock']}. This is the only clock in the scene; the real-world date and time do not exist for {name}, so never mention them. "
    if sim["night"]:
        s += "It is night: it is dark out and people are winding down or asleep."
    elif sim["daytime"]:
        s += f"It is daytime ({sim['period']}): it is light out, people are up and about, classes, shops and offices are running. Do NOT describe or act as if it were night, late, dark or bedtime."
    else:
        s += f"It is {sim['period']}: the light is fading and the day is ending."
    return s


_NIGHT = re.compile(r"(?i)\b(?:midnight|late\s+at\s+night|so\s+late|middle\s+of\s+the\s+night|moonlit|moonlight|starlit|starry\s+sky|pitch[- ]dark|"
                    r"bed\s*time|go(?:ing)?\s+to\s+bed|(?:good\s*)?night(?:\s+now)?|can'?t\s+sleep|should\s+be\s+asleep|past\s+curfew)\b")
_DAY = re.compile(r"(?i)\b(?:good\s+morning|bright\s+and\s+early|this\s+morning|midday\s+sun|broad\s+daylight|lunch\s*time)\b")


def time_note(text, sim):
    """'' when the reply fits the story clock, else a correction for a retry."""
    if not sim or not text:
        return ""
    plain = text
    if sim["daytime"] and sim["period"] in ("morning", "midday", "afternoon", "early morning") and _NIGHT.search(plain):
        return (f"The story clock says {sim['clock']}. It is daytime. Do not mention night, darkness, being late or bedtime; "
                "describe the daytime scene instead.")
    if sim["night"] and _DAY.search(plain):
        return f"The story clock says {sim['clock']}. It is night, so it cannot be morning or midday."
    return ""
