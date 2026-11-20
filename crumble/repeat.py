"""Is this reply saying what was already said?

The old check compared whole replies with difflib at a .8 ratio and only looked at the character's OWN earlier messages, and only
when Quick replies was off (it is on by default). So in a group two characters could say the same line back to back, and one
character could repeat a sentence inside a longer reply without ever being noticed.

    score(text, prev)            0..1, how much of `text` was already said in `prev` (whole-text ratio, shared word 3-grams,
                                 shared sentences: whichever is highest)
    worst(text, prevs)           (highest score, index into prevs)
    SOFT / HARD                  a retry is worth it from SOFT; HARD means it is practically the same message

Pure text functions, no imports from the rest of the package.
"""
import difflib
import re

SOFT, HARD = .72, .9
_SENT = re.compile(r"(?<=[.!?…])\s+|\n+")
_WORD = re.compile(r"[a-z0-9']+")


def toks(t):
    return _WORD.findall(re.sub(r"[*_`\"“”]", " ", (t or "").lower()))


def _grams(w, n=3):
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def _sents(t):
    return [toks(s) for s in _SENT.split(re.sub(r"<think>.*?(?:</think>|$)", "", t or "", flags=re.S)) if s and len(toks(s)) >= 5]


def score(text, prev):
    a, b = toks(text), toks(prev)
    if len(a) < 2 or len(b) < 2:
        return 0.0
    best = 0.0
    if min(len(a), len(b)) >= 0.5 * max(len(a), len(b)):   # comparable length: the replies as a whole
        best = difflib.SequenceMatcher(None, a, b).ratio()
    ga, gb = _grams(a), _grams(b)
    if min(len(ga), len(gb)) >= 4:                           # one reply inside the other, or heavy overlap
        best = max(best, len(ga & gb) / min(len(ga), len(gb)))
    sb = _sents(prev)
    for s in _sents(text):                                   # one sentence repeated word for word inside a longer reply
        for x in sb:
            if min(len(s), len(x)) >= 0.8 * max(len(s), len(x)) and difflib.SequenceMatcher(None, s, x).ratio() >= .9:
                best = max(best, .8 + min(.15, .02 * len(s)))
                break
    return round(best, 3)


def worst(text, prevs):
    hi, at = 0.0, -1
    for i, p in enumerate(prevs or []):
        if p and p.strip():
            s = score(text, p)
            if s > hi:
                hi, at = s, i
    return hi, at
