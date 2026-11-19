"""Register: HOW a character is required to sound, as concrete grammar rather than adjectives.

A sheet that says "refined, theatrical Shakespearean" or "formal, no slang" is a description. Small models read a description
as flavour and drift back to ordinary modern chat within a line or two, especially when the generic realism rules ask for
contractions and fillers. This module turns the description into something that can be enforced:

    detect(c, mode)       read the sheet -> {"kind": "archaic" | "formal", ...} or None (ordinary speech, nothing to enforce)
    render(reg)           the mandatory speech block for the prompt: grammar rules, favoured words, a few demonstration lines
    tail(reg)             one-line reminder for the end of the last turn (the spot a model weighs most)
    realism_line / natural_line   replacements for the two generic rules that otherwise contradict the register
    audit(reg, text)      score a finished reply: modern "you", contractions, slang, no archaic diction at all
    repair(text, reg)     mechanical fix for the one thing that is always safe to fix: expanding contractions

Pure functions, no model calls. Only the spoken words are judged: *actions* and (asides) are narration and stay plain prose.
"""
import re
from functools import lru_cache

from ..config import CH, US

# Sheet fields that can declare how someone speaks (the author may write it almost anywhere).
SPEECH_FIELDS = ("speech", "dialect", "vocab", "catchphrases", "mood_speech", "consistency", "system_prompt", "post_history",
                 "description", "personality")
SPOKEN_ONLY = ("speech", "dialect", "vocab", "catchphrases", "mood_speech")   # where "formal" / "refined" is about voice, not manners

# ------------------------------------------------------------------------------------------------ reading the sheet
_ARCHAIC = re.compile(
    r"shakespear\w*|elizabethan|early[- ]modern english|king james|\bkjv\b|\bye olde\b|\bolde english\b|middle english|"
    r"\b(?:thou|thee|thy|thine|thyself|wouldst|couldst|shouldst|hath|doth|dost|forsooth|prithee|methinks|verily)\b|"
    r"\barchaic (?:english|speech|language|diction|grammar|dialect|manner|style|tone|phrasing|way of speaking)\b|"
    r"\b(?:speaks?|talks?|speaking|talking|dialogue|delivered|written|writes?|diction)\b[^.]{0,40}\barchaic\b|"
    r"\bold[- ]fashioned (?:english|speech|diction)\b|\bmedieval (?:english|speech|diction)\b", re.I)
_FORMAL = re.compile(r"(?<![\w-])(?:formal|ceremonial|courtly|aristocratic|dignified|stately|regal|solemn|refined|eloquent|polished)(?![\w-])", re.I)
_NEG = re.compile(r"(?:\bnot|\bnever|\bno|n't|\bwithout|\brather than|\binstead of|\bunlike|\bavoids?|\bnor|\bneither|\bnot quite)\W+(?:\w+\W+){0,4}$", re.I)
_QUOTED = re.compile(r"[\"“]([^\"”]{12,170})[\"”]")
_WORDLIST = re.compile(r"\b(?:words|terms|expressions|phrases|vocabulary)\b[^.:]{0,40}?(?:such as|like|including|:)\s+([^.]+)", re.I)


def _negated(text, start):
    pre = re.split(r"[.!?;\n]", text[:start])[-1][-50:]
    return bool(_NEG.search(pre))


def _cue(rx, text):
    return any(not _negated(text, m.start()) for m in rx.finditer(text or ""))


def _lexicon(c):
    """Words the author says the character favours ('words such as grace, heresy, flame')."""
    out = []
    for field in ("vocab", "catchphrases", "speech"):
        for m in _WORDLIST.finditer(c.get(field) or ""):
            for w in re.split(r",|\band\b|;", m.group(1)):
                w = w.strip(" \"“”'’.").lower()
                if 2 < len(w) <= 22 and len(w.split()) <= 2 and w not in out:
                    out.append(w)
    return out[:12]


def _lines(c):
    """Signature declarations written in quotes in the catchphrases field (three or more words)."""
    out = []
    for m in _QUOTED.finditer(c.get("catchphrases") or ""):
        t = m.group(1).strip()
        if len(t.split()) >= 3 and t not in out:
            out.append(t)
    return out[:3]


@lru_cache(maxsize=256)
def _detect(fields, formality, name, lex, lines):
    pool = "\n".join(v for v in fields if v)
    spoken = "\n".join(v for k, v in zip(SPEECH_FIELDS, fields) if k in SPOKEN_ONLY and v)
    kind = "archaic" if _cue(_ARCHAIC, pool) else "formal" if (_cue(_FORMAL, spoken) or formality >= 70) else None
    return {"kind": kind, "name": name, "lex": list(lex), "lines": list(lines)} if kind else None


def detect(c, mode="story"):
    """The register this sheet requires, or None for ordinary speech. In texting mode only the texting field counts:
    a character who writes modern English on a phone is not forced into thou and thee there."""
    from .profile import profile_for
    c = c or {}
    name = (c.get("name") or "").strip()
    if mode == "text":
        t = c.get("texting") or ""
        kind = "archaic" if _cue(_ARCHAIC, t) else "formal" if _cue(_FORMAL, t) else None
        return {"kind": kind, "name": name, "lex": _lexicon(c), "lines": []} if kind else None
    try:
        formality = profile_for(c)["traits"]["formality"]
    except Exception:
        formality = 50
    return _detect(tuple((c.get(k) or "") for k in SPEECH_FIELDS), formality, name, tuple(_lexicon(c)), tuple(_lines(c)))


# ------------------------------------------------------------------------------------------------ the prompt
_ARCHAIC_RULES = [
    "Address {US} as thou (subject), thee (object), thy / thine (possessive) and thyself. Use you / your / yours / yourself only for several people at once, never for {US} alone.",
    "Verbs take the old forms: thou art, hast, dost, wilt, shalt, canst, wouldst, couldst, shouldst, speakest, standest, darest; "
    "and for everyone else goeth, standeth, cometh, hath, doth. Wherever modern English would say \"you are / you have / you do / what do you\", {CH} says \"thou art / thou hast / thou dost / what dost thou\".",
    "No contractions, ever. Write do not, cannot, I am, it is, never don't, can't, I'm, it's, you're.",
    "Period words, never modern ones: hence, whence, wherefore, ere, anon, naught, aught, nay, yea, verily, mayhap, methinks, prithee, perchance, mine own (before a vowel), 'tis. "
    "Never okay, yeah, hey, guys, stuff, kind of, sort of, gonna, wanna, awesome, basically, whatever, I guess, you know.",
    "Sentence shape is ceremonial and weighty: commands (\"Speak thy purpose.\"), inverted order (\"Rarely doth a trespasser leave this place.\"), "
    "rhetorical questions (\"What wouldst thou have of me?\"), solemn declarations and direct address by title or name.",
    "This speech never fades. It is the same when {CH} is angry, tender, tired, bored or answering something casual. If {US} writes modern slang, {CH} does not echo it and does not switch to it.",
    "Only the spoken words are archaic. Actions and narration between *asterisks* stay plain prose.",
]
_ARCHAIC_DEMO = [
    "Thou darest speak so to me? My patience hath limits, and thou hast found them.",
    "What wouldst thou have of me? Speak plainly, ere I weary of thy silence.",
    "Thy words are bold, yet they are naught but wind. Stand thou there, and behold what cometh.",
    "I do not forgive, and I cannot forget. Doth that trouble thee?",
]
_FORMAL_RULES = [
    "No contractions: write do not, cannot, I am, it is.",
    "Complete, composed sentences. No slang, no fillers (uh, um, like, you know, I mean), no casual interjections (yeah, okay, hey, wow).",
    "Choose exact, elevated words over everyday ones. Statements are deliberate declarations, not chatter.",
    "Mood does not loosen this: anger turns colder and more precise, not looser or louder.",
]


def render(reg):
    """The mandatory speech block. {{char}} / {{user}} placeholders are filled by the prompt builder."""
    arch = reg["kind"] == "archaic"
    head = (f"{CH} speaks Early Modern English (Shakespearean, King James cadence) in every spoken line, in every mood, from the first word to the last. "
            f"This is how {CH} actually sounds. It is not optional flavour and it does not fade as the chat goes on."
            if arch else f"{CH} speaks in a formal, dignified register in every spoken line, whatever the mood.")
    lines = [head]
    lines += ["- " + r for r in (_ARCHAIC_RULES if arch else _FORMAL_RULES)]
    if reg["lex"]:
        lines.append(f"Favoured words (work them in naturally, do not list them): {', '.join(reg['lex'])}.")
    if reg["lines"]:
        lines.append("Signature declaration (now and then, never every reply): " + " / ".join(f"\"{x}\"" for x in reg["lines"]))
    if arch:
        lines.append("Demonstration of the speech only, never repeat these lines or their content:")
        lines += ["  " + x for x in _ARCHAIC_DEMO]
    lines = [x.replace("{US}", US).replace("{CH}", CH) for x in lines]
    return f"[{CH} - Speech pattern (mandatory)]\n" + "\n".join(lines)


def tail(reg):
    if reg["kind"] == "archaic":
        return (f"{CH}'s spoken words are Early Modern English: thou / thee / thy, -est and -eth verbs, no contractions, and never \"you\" or \"your\" for {US} alone.")
    return f"{CH}'s speech is formal: no contractions, no slang, no fillers."


def realism_line(reg):
    """Replaces the generic 'talk like a real person: contractions, fragments' rule, which contradicts the register."""
    what = "the archaic speech described in the Speech pattern block" if reg["kind"] == "archaic" else "the formal register described in the Speech pattern block"
    return (f"Talk like a person, not an assistant, but in {CH}'s own voice: {what}, never in everyday modern chat. "
            f"No contractions. Vary sentence length. No lecturing, no lists, no summarising what {US} just said.")


def natural_line(reg):
    return (f"Speech may pause, trail off with an ellipsis or turn a thought mid-sentence, always inside {CH}'s register. "
            "No modern fillers (uh, um, like, I mean, you know).")


# ------------------------------------------------------------------------------------------------ judging a reply
_THOU = re.compile(r"\b(?:thou|thee|thy|thine|thyself)\b", re.I)
_CORE = re.compile(r"\b(?:hast|hath|doth|dost|wilt|shalt|canst|mayst|wert|wast|wouldst|couldst|shouldst|didst|hadst|ere|whence|wherefore|"
                   r"whither|thither|hither|anon|naught|aught|nay|yea|verily|forsooth|prithee|methinks|mayhap|perchance|nigh|oft|betwixt|mine own)\b|['’]tis\b|['’]twas\b", re.I)
_ETH = re.compile(r"\b[a-z]{2,}eth\b", re.I)
_ETH_NOT = {"teeth", "kenneth", "elizabeth", "macbeth", "gareth", "heneth", "beneath"}
_YOU = re.compile(r"\b(?:you|your|yours|yourself|yourselves|y['’]all|ya)\b", re.I)
_A = r"['’]"
_CONTR = re.compile(rf"\b(?:\w+n{_A}t|i{_A}(?:m|ve|ll|d)|(?:you|we|they){_A}(?:re|ve|ll|d)|(?:he|she|it|that|there|here|what|who|let){_A}s|(?:he|she|it){_A}(?:ll|d)|gonna|wanna|gotta)\b", re.I)
_MODERN = re.compile(r"\b(?:yeah|yep|yup|nope|okay|ok|hey|guys|dude|bro|buddy|kinda|sorta|awesome|basically|literally|totally|whatever|wow|uh|um|lol|omg|you know)\b", re.I)
_QUOTE_SPAN = re.compile(r"[\"“]([^\"”]+)[\"”]")


def _spoken(text):
    t = re.sub(r"\*[^*\n]*\*", " ", text or "")
    t = re.sub(r"\([^)\n]*\)", " ", t).strip()
    quoted = _QUOTE_SPAN.findall(t)      # a reply that quotes its speech has narration outside the quotes: judge only the quotes
    return " ".join(quoted) if quoted else t


def _uniq(xs, n=5):
    out = []
    for x in xs:
        x = x.lower()
        if x not in out:
            out.append(x)
    return out[:n]


def audit(reg, text):
    """-> ([(penalty, flag, instruction for a retry)], hard). `hard` means the reply is plainly not in the required register."""
    s = _spoken(text)
    words = len(re.findall(r"[\w'’]+", s))
    if not reg or words < 6:
        return [], False
    contr = [m.group(0) for m in _CONTR.finditer(s)]
    modern = [m.group(0) for m in _MODERN.finditer(s)]
    found, hard = [], False
    if reg["kind"] == "archaic":
        thou = len(_THOU.findall(s))
        arch = thou + len(_CORE.findall(s)) + sum(1 for w in _ETH.findall(s) if w.lower() not in _ETH_NOT)
        you = [m.group(0) for m in _YOU.finditer(s)]
        shown = _uniq(you + contr + modern)
        fix = ("Rewrite every spoken line in Early Modern English: thou / thee / thy instead of you / your (\"you are\" becomes \"thou art\", "
               "\"what do you want\" becomes \"what wouldst thou have\"), -est / -eth verbs (thou standest, he standeth), no contractions, "
               "words like ere, hence, naught, prithee.")
        if arch == 0:
            found.append((50, "speaks modern English, not the character's archaic speech",
                          "Your last attempt used modern English" + (f" ({', '.join(repr(x) for x in shown)})" if shown else "") + ". " + fix))
            hard = True
        else:
            if you:
                found.append((30, "slips into modern 'you' instead of thou", f"You wrote {', '.join(repr(x) for x in _uniq(you))} to address someone. Use thou / thee / thy. " + fix))
            if words >= 30 and arch < 2:
                found.append((12, "archaic diction too thin", "Make the archaic speech stronger: thou / thee / thy and -est / -eth verbs throughout."))
        if contr:
            found.append((18 if len(contr) == 1 else 28, "uses contractions", f"No contractions ({', '.join(repr(x) for x in _uniq(contr))}): write them out in full."))
        if modern and arch:
            found.append((15, "modern slang or fillers", f"Remove modern words ({', '.join(repr(x) for x in _uniq(modern))}); use period words."))
    else:
        if contr:
            found.append((12 if words >= 8 else 0, "uses contractions", f"No contractions ({', '.join(repr(x) for x in _uniq(contr))}): write them out in full."))
        if modern:
            found.append((10, "slang or fillers in a formal voice", f"Remove casual words ({', '.join(repr(x) for x in _uniq(modern))}); keep a formal register."))
    return [x for x in found if x[0]], hard


# ------------------------------------------------------------------------------------------------ repair
_PRON = r"(I|you|thou|he|she|it|we|they|there|that|this)"
_INV = re.compile(rf"\b(is|are|was|were|do|does|did|have|has|had|would|could|should|must)n{_A}t\s+{_PRON}\b", re.I)    # "isn't it" -> "is it not"
_INV_IRR = re.compile(rf"\b(can|won){_A}t\s+{_PRON}\b|\b(ca)n{_A}t\s+{_PRON}\b", re.I)


def _inv_irregular(m):
    word = (m.group(1) or "can").lower()
    pron = m.group(2) or m.group(4)
    aux = "will" if word == "won" else "can"
    return (aux.capitalize() if (m.group(0)[0].isupper()) else aux) + " " + pron + " not"


_FIX = [
    (_INV, r"\1 \2 not"), (_INV_IRR, _inv_irregular),
    (re.compile(rf"\bwon{_A}t\b", re.I), "will not"), (re.compile(rf"\bcan{_A}t\b", re.I), "cannot"),
    (re.compile(rf"\bshan{_A}t\b", re.I), "shall not"), (re.compile(rf"\bain{_A}t\b", re.I), "is not"),
    (re.compile(rf"\b(\w+?)n{_A}t\b", re.I), r"\1 not"),
    (re.compile(rf"\bI{_A}m\b", re.I), "I am"),
    (re.compile(rf"\b(I|you|we|they){_A}ve\b", re.I), r"\1 have"),
    (re.compile(rf"\b(I|you|we|they|he|she|it|that|there|who|what){_A}ll\b", re.I), r"\1 will"),
    (re.compile(rf"\b(you|we|they){_A}re\b", re.I), r"\1 are"),
    (re.compile(r"\bgonna\b", re.I), "going to"), (re.compile(r"\bwanna\b", re.I), "want to"), (re.compile(r"\bgotta\b", re.I), "must"),
]
_SKIP = re.compile(r"(\*[^*\n]*\*|\([^)\n]*\))")


def repair(text, reg):
    """Expand the unambiguous contractions in the spoken parts. ('s and 'd are left alone: they could mean is / has / would / had.)"""
    if not reg or not text:
        return text
    out = []
    for part in _SKIP.split(text):
        if not _SKIP.fullmatch(part):
            for rx, rep in _FIX:
                part = rx.sub(rep, part)
        out.append(part)
    return "".join(out)
