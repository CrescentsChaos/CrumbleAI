"""Finds internal state that a model echoed into its reply, and removes only that.

Everything the prompt tells a character privately (scene summaries, relationship and mood data, memory text, the story clock,
location notes, author's notes, instructions) is written for the model. When a small model repeats it, the reader sees a status
panel instead of a story. Two layers catch that:

    scrub(text, ...)            STRUCTURAL leaks: text that is only ever prompt scaffolding. 'Location: ...' field lines,
                                'SETTING & STATE' headings, '[Right now]' blocks, 'Story time: ...', rating numbers like
                                'affection 72/100', unresolved {{char}} placeholders, the prompt's own instruction sentences,
                                a time stamp used as a line header. Only the offending span is removed. Anything inside
                                "dialogue" or *narration* that is not one of those exact shapes is left alone.
    find_echoes(text, private)  VERBATIM leaks: a run of 8+ words copied out of the private background. This is only a signal
                                (the caller retries); drop_echo_sentences() is the last resort when retries ran out, and it only
                                removes sentences that are almost entirely copied and that are not spoken dialogue.

Pure text functions, no imports from the rest of the package.
"""
import re

# field names the prompt (and the summary template) use; a line that STARTS with one of these and a colon is metadata
FIELDS = (r"location|current\s+state|primary\s+dynamic|tone|setting\s*(?:&|and)\s*state|relationship\s+dynamic|pivotal\s+moments?|"
          r"scene|just\s+happened|story\s+time|current\s+time|timestamp|time\s*stamp|clock|mood|current\s+mood|energy|affection|"
          r"relationship(?:\s+(?:status|stage|path|level))?|romance(?:\s+level)?|trust|bond|stage|memory|memories|summary|recap|"
          r"character\s+state|scene\s+summary|scene\s+state|inner\s+state|internal\s+state|who'?s\s+who|present|"
          r"author'?s\s+notes?|scene\s+note|reactions|weather|place")
_FIELD_LINE = re.compile(r"(?im)^[ \t]*(?:[-•>][ \t]*)?\**[ \t]*(?:" + FIELDS + r")[ \t]*\**[ \t]*:[ \t]*\**[ \t]*(?=\S)")
# ALL-CAPS section headings of the summary template, alone on a line
_HEADING = re.compile(r"(?im)^[ \t]*#*[ \t]*\**[ \t]*(?:SETTING\s*(?:&|AND)\s*STATE|RELATIONSHIP\s+DYNAMIC|PIVOTAL\s+MOMENTS|CHARACTERS|"
                      r"CURRENT\s+STATE|PRIVATE\s+BACKGROUND|END\s+OF\s+PRIVATE\s+BACKGROUND|EARLIER\s+EVENTS)[ \t]*\**[ \t]*:?[ \t]*$\n?")
_ENVELOPE = re.compile(r"(?im)^[ \t]*={3,}[^\n]*$\n?")
# a bracket / parenthesis that wraps a field: (Location: the garage) [Mood: happy]
_WRAPPED = re.compile(r"(?i)[\[(][ \t]*(?:" + FIELDS + r")[ \t]*:[^\])\n]{0,160}[\])]")
# '[Right now]' style block headers and what follows them on that line
_BLOCK_HEAD = re.compile(r"(?i)\[(?:right\s+now|scene|environment[^\]]*|earlier[^\]]*|what\s+[^\]]{0,30}remembers[^\]]*|things\s+[^\]]{0,30}\s+knows[^\]]*|"
                         r"romance\s+with[^\]]*|who'?s\s+who[^\]]*|author'?s\s+notes[^\]]*|resolved[^\]]*|fight|style|realism|variety|"
                         r"group\s+chat[^\]]*|about\s+[^\]]{1,40}|[^\]]{1,40}\s+-\s+(?:core|identity|behaviou?r|voice[^\]]*|mind[^\]]*))\]")
# numbers that only exist as hidden state
_STATE_NUM = re.compile(r"(?i)\b(?:affection|trust|romance|bond|mood|energy|relationship)\s*(?:score|level|value|meter|points?)?\s*[:=]\s*[+-]?\d{1,3}(?:\s*/\s*100)?\b|"
                        r"\b\d{1,3}\s*/\s*100\b|\b(?:affection|trust)\s+(?:is|at|of)\s+\d{1,3}\b")
# the mood line in the prompt: "<name>'s current mood: happy; energy: medium."
_MOOD_DATA = re.compile(r"(?i)\b(?:[\w']+\s+)?current\s+mood\s*:\s*[^.\n;]{1,40}(?:;\s*energy\s*:?\s*\w+)?\.?|\benergy\s*:\s*(?:low|medium|high)\b")
# story-clock data used as a line header: 'Monday, around 9:00 AM (morning).' / '[Today 3:15 PM]' / '(Friday 15:15)'
_DAY = r"(?:mon|tues?|wed(?:nes)?|thu(?:rs?)?|fri|sat(?:ur)?|sun)(?:day)?"
_STAMP = re.compile(r"(?im)^[ \t]*[\[(][ \t]*(?:(?:today|yesterday|" + _DAY + r")[ ,]*)?(?:\d{1,2}[:.]\d{2}(?:[ \t]*[ap]\.?m\.?)?|\d{4}-\d{2}-\d{2}[^\])\n]{0,12})[ \t]*[\])][ \t]*[:\-–—]?[ \t]*")
_STORY_TIME = re.compile(r"(?i)\b(?:in the story it is|story time is)\b[^.\n]{0,80}\.?|\bthe real-world date and time do not exist\b[^.\n]*\.?")
# unresolved template variables
_PLACEHOLDER = re.compile(r"\{\{\s*(char|user)\s*\}\}|\{(CH|US|USER|CHAR)\}")
# the prompt's own sentences (distinctive 4+ word runs). Kept in sync with prompt.py by tests/test_leakage.py.
INSTRUCTIONS = [
    r"let\s+this\s+shape\s+warmth,?\s+openness",
    r"never\s+mention\s+numbers\s+or\s+scores",
    r"this\s+is\s+the\s+only\s+clock\s+in\s+the\s+scene",
    r"let\s+(?:it|that)\s+colou?r\s+tone\s+and\s+word\s+choice",
    r"acknowledge\s+that\s+naturally\s+only\s+if\s+it\s+matters",
    r"do\s+not\s+describe\s+or\s+act\s+as\s+if\s+it\s+were\s+night",
    r"pick\s+one\s+or\s+two\s+of\s+these\s+per\s+reply",
    r"these\s+notes\s+come\s+from\s+outside\s+the\s+story",
    r"apply\s+them\s+silently",
    r"stay\s+aware\s+of\s+this\s+environment\s+in\s+every\s+reply",
    r"never\s+a\s+service\s+waiting\s+for\s+instructions",
    r"weather\s+has\s+physics",
    r"whatever\s+the\s+scene\s+has\s+established",
    r"silent\s+(?:reference|knowledge|background)\s+for\s+the\s+writer",
    r"private\s+note\s+for\s+the\s+writer",
    r"write\s+only\s+\S+(?:\s+\S+)?'s\s+next\s+message",
    r"never\s+copy,?\s+quote,?\s+answer\s+or\s+mention\s+it",
    r"events\s+only:\s+who\s+someone\s+is\s+comes\s+from",
    r"how\s+to\s+use\s+the\s+private\s+background",
    r"is\s+also\s+the\s+author\s+of\s+this\s+story",
]
_INSTR = re.compile("|".join(INSTRUCTIONS), re.I)
# the exact words stage() puts after '{char} is' (config.STAGES): the character is not 'fond of them and close' in a story
STAGE_PHRASES = ("hostile toward them", "cold and wary", "distant and guarded", "neutral, still getting to know them",
                 "friendly and comfortable with them", "fond of them and close", "deeply attached and trusting")
_STAGE = re.compile(r"(?i)\b(?:is|feels|seems)\s+(?:" + "|".join(re.escape(p) for p in STAGE_PHRASES) + r")\b")
# the model is planning out loud instead of writing the reply (outside quotes only)
_PLANNING = re.compile(r"(?im)^[ \t]*(?:okay|ok|alright|so)?[ ,.:-]*(?:the\s+user\s+(?:is|wants|said|asked|just|has)\b|i\s+(?:need|should|must|have)\s+to\s+(?:respond|reply|write|stay|keep|play)\b|"
                       r"let\s+me\s+(?:think|write|respond|craft)\b|(?:my|the)\s+(?:reply|response|plan)\s+(?:is|will|should)\b|"
                       r"(?:inner|internal)\s+(?:monologue|narration|state)\s*:)[^\n]*$\n?")
CUT = "\x00"   # marks a removal inside a line
_SPAN = re.compile(r"\*[^*\n]+\*|\"[^\"\n]*\"|“[^”\n]*”")
_WORD = re.compile(r"[a-z0-9']+")


def _protected(line):
    """Spans of a line that are dialogue or narration."""
    return [(m.start(), m.end()) for m in _SPAN.finditer(line)]


def _inside(pos, spans):
    return any(a < pos < b for a, b in spans)


def _first_span_after(line, pos):
    for a, _ in _protected(line):
        if a >= pos:
            return a
    return len(line)


def _names(*groups):
    out = []
    for g in groups:
        for n in ([g] if isinstance(g, str) else (g or [])):
            n = (n or "").strip()
            if n:
                out.append(n)
    return out


def scrub(text, char="", user=(), others=()):
    """-> (clean text, [{'kind', 'text'}]). Removes structural leaks only; see the module docstring."""
    found = []
    t = text or ""
    if not t.strip():
        return t, found

    def note(kind, s):
        found.append({"kind": kind, "text": re.sub(r"\s+", " ", s).strip()[:160]})

    # placeholders are resolved, never shown
    def ph(m):
        who = (m.group(1) or m.group(2) or "").lower()
        name = (char if who in ("char", "ch") else (_names(user) or ["you"])[0])
        note("placeholder", m[0])
        return name or ("you" if who not in ("char", "ch") else "")
    t = _PLACEHOLDER.sub(ph, t)
    # envelope markers and caps headings
    t = _ENVELOPE.sub(lambda m: (note("envelope", m[0]), "")[1], t)
    t = _HEADING.sub(lambda m: (note("heading", m[0]), "")[1], t)
    t = _PLANNING.sub(lambda m: (note("planning", m[0]), "")[1], t)
    # line by line: field labels, stamps, block headers
    out = []
    for line in t.split("\n"):
        m = _FIELD_LINE.match(line)
        if m:
            end = _first_span_after(line, m.end())
            note("field", line[:end])
            line = line[end:]
        s = _STAMP.match(line)
        if s:
            note("stamp", s[0])
            line = line[s.end():]
        spoken = [(a, b) for a, b in _protected(line) if line[a] in "\"“"]   # (Mood: happy) inside *narration* is still a leak; inside spoken words it is not touched
        for rx, kind in ((_WRAPPED, "field"), (_BLOCK_HEAD, "block")):
            line = rx.sub(lambda m, spoken=spoken: m[0] if _inside(m.start(), spoken) else (note(kind, m[0]), CUT)[1], line)
        out.append(line)
    t = "\n".join(out)
    # sentences that are the prompt's own wording or hidden state, wherever they sit
    for rx, kind in ((_INSTR, "instruction"), (_STORY_TIME, "clock"), (_STATE_NUM, "number"), (_STAGE, "state"), (_MOOD_DATA, "state")):
        for _ in range(6):
            m = rx.search(t)
            if not m:
                break
            a = max(t.rfind(".", 0, m.start()), t.rfind("\n", 0, m.start()), t.rfind("*", 0, m.start()), t.rfind('"', 0, m.start()))
            a = 0 if a < 0 else a + 1
            if t[m.end() - 1:m.end()] in (".", "!", "?"):   # the match already ends its sentence
                b = m.end()
            else:
                cands = [i for i in (t.find(".", m.end()), t.find("\n", m.end())) if i >= 0]
                b = (min(cands) + 1) if cands else len(t)
            if kind in ("number", "state") and not (kind == "state" and rx is _MOOD_DATA):   # these are short facts inside a longer sentence: cut the clause, not the whole line
                a = max(t.rfind(",", 0, m.start()) + 1, a) if t.rfind(",", 0, m.start()) > a else a
            note(kind, t[a:b])
            t = t[:a] + CUT + t[b:]
    # leftovers of removal. CUT marks where text was taken out of a line, so a span or quote that is now empty goes too, while
    # *two spans* or "two quotes" that merely touch are left exactly as they were written.
    t = re.sub(r"\*[ \t]*" + CUT + r"[ \t]*\*", " ", t)
    t = re.sub(r"\"[ \t]*" + CUT + r"[ \t]*\"", " ", t)
    t = re.sub(r"[\[(][ \t]*" + CUT + r"[ \t]*[\])]", " ", t)
    t = t.replace(CUT, "")
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip(), found


def words(t):
    return _WORD.findall(re.sub(r"[*_`]", " ", (t or "").lower()))


def corpus(pieces, n=8):
    """The set of n-word runs in the private background, for find_echoes()."""
    grams = set()
    for p in pieces:
        w = words(p)
        for i in range(len(w) - n + 1):
            grams.add(tuple(w[i:i + n]))
    return grams


def find_echoes(text, grams, n=8):
    """Runs of >= n words in `text` that appear verbatim in the private background -> [str]. Empty when nothing was copied."""
    if not grams or not text:
        return []
    w, runs, i = words(text), [], 0
    while i <= len(w) - n:
        if tuple(w[i:i + n]) in grams:
            j = i + n
            while j < len(w) and tuple(w[j - n + 1:j + 1]) in grams:
                j += 1
            runs.append(" ".join(w[i:j]))
            i = j
        else:
            i += 1
    return runs


def drop_echo_sentences(text, grams, n=8, share=.7):
    """Last resort once retries ran out: remove narration/prose sentences that are mostly copied from the private background.
    Spoken dialogue (inside quotes) is kept, and so is anything that is not mostly a copy, so nothing legitimate is lost."""
    if not grams or not text:
        return text
    lines = []
    for line in text.split("\n"):
        spans, kept, pos = _protected(line), [], 0
        pieces = []
        for m in re.finditer(r"[^.!?…]+[.!?…]*\s*", line):
            pieces.append(m)
        for m in pieces:
            s = m[0]
            w = words(s)
            quoted = _inside(m.start() + 1, [(a, b) for a, b in spans if line[a] in "\"“"])
            if not quoted and len(w) >= n and sum(len(r.split()) for r in find_echoes(s, grams, n)) >= share * len(w):
                continue
            kept.append(s)
        lines.append("".join(kept))
    out = "\n".join(lines)
    out = re.sub(r"\*\s*\*", " ", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip() if out.strip() else text
