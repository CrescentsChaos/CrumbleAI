"""Keeps internal instructions out of what a character says, and keeps narration visibly separate from dialogue.

    strip_directives()   removes leaked prompt text: '[Reply as Crescent. Be casual ...]', '[As Faith]', '<<private note>>',
                         '(Write only Faith's next message.)', 'Reply as Faith:' prefaces. Reports whether the model
                         wrote as the USER (a role flip) so the caller can retry.
    enclose_narration()  everything that is not spoken dialogue ends up between *asterisks*: leftover (aside) and [aside]
                         text, and bare third-person sentences about the character or the user.
Pure text functions, no imports from the rest of the package."""
import re

# text that is only ever an instruction, whatever the brackets around it
STRONG = re.compile(
    r"(?i)\b(?:write\s+only|only\s+write|next\s+message|the\s+author|author'?s\s+notes?|stay\s+in\s+character|"
    r"never\s+(?:write|mention|speak|act|break|talk|use|reveal)|reply\s+(?:as|with|only)|respond\s+as|narrate\s+what|"
    r"be\s+casual|be\s+friendly|casual\s+and\s+friendly|in\s+this\s+(?:conversation|scene|roleplay)|"
    r"system\s+(?:prompt|instruction)|instructions?|persona\s+note|private\s+note|out\s+of\s+character|"
    r"as\s+an?\s+(?:ai|assistant)|react\s+in\s+character|no\s+preface|no\s+label|scene\s+note|follow\s+the)\b")
# a square-bracket block that starts like an instruction or a label
BRACKET_HEAD = re.compile(
    r"(?i)^\s*(?:reply\b|respond\b|write\b|output\b|be\s|stay\b|never\b|always\b|do\s+not\b|don'?t\b|follow\b|correction\b|style\b|"
    r"realism\b|right\s+now\b|scene\b|narrate\b|continue\b|the\s+author\b|private\b|system\b|instruction|note\b|ooc\b|as\s+[A-Z]|"
    r"react\b|you\s+are\b|you're\b|keep\b|use\b|speak\b|answer\b|format\b|voice\b|variety\b|who'?s\s+who\b|pass\b|"
    r"character\b|personality\b|behaviou?r\b|group\s+chat\b|example\s+dialogue\b|world\s+info\b|about\s+\w+\b)")
LEAD_LABEL = re.compile(r"(?i)^[ \t]*(?:\*+)?(?:(?:reply(?:ing)?|respond(?:ing)?|speak(?:ing)?|writ(?:e|ing)|answer(?:ing)?)\s+as|as|in\s+the\s+role\s+of)"
                        r"\s+(?P<who>[A-Z][\w'’-]*(?:\s[A-Z][\w'’-]*)?)\s*(?:\*+)?\s*[:\-—]\s*")


def _names(*groups):
    out = []
    for g in groups:
        for n in ([g] if isinstance(g, str) else (g or [])):
            n = (n or "").strip()
            if n:
                out += [n, n.split()[0]]
    return sorted({n for n in out if len(n) > 1}, key=lambda s: (-len(s), s.lower()))


def _flip(seg, user_names):
    """Does this removed instruction say the reply is written AS the user?"""
    for u in user_names:
        if re.search(rf"(?i)\b(?:reply(?:ing)?|respond(?:ing)?|speak(?:ing)?|writ(?:e|ing)|answer(?:ing)?)\s+as\s+{re.escape(u)}\b|^\s*as\s+{re.escape(u)}\b", seg):
            return True
    return False


def strip_directives(text, char="", user=(), others=()):
    """-> (clean text, {'leaked': bool, 'flipped': bool, 'removed': [str]}).
    `user` may be one name or several (the name set in the page and the name asked for in the chat)."""
    info = {"leaked": False, "flipped": False, "removed": []}
    unames = _names(user)
    labels = {n.lower() for n in _names(char, user, others)}

    def drop(seg):
        info["leaked"] = True
        info["removed"].append(seg.strip()[:160])
        if _flip(seg, unames):
            info["flipped"] = True
        return ""

    t = text or ""
    t = re.sub(r"<<[\s\S]*?(?:>>|$)", lambda m: drop(m[0]), t)                      # <<private note ...>> (also when cut off)
    t = re.sub(r"</?(?:system|instruction|note|ooc)[^>]*>", lambda m: drop(m[0]), t, flags=re.I)

    def square(m):
        inner = m[1].strip()
        if BRACKET_HEAD.match(inner) or STRONG.search(inner) or inner.lower() in labels:
            return drop(m[0])
        return f"*{inner}*" if inner else ""
    t = re.sub(r"\[([^\[\]\n]{1,400})\]", square, t)
    m = re.search(r"\[([^\]\n]{0,400})$", t)                                         # a bracket that was never closed (cut off)
    if m and (BRACKET_HEAD.match(m[1]) or STRONG.search(m[1]) or not m[1].strip()):
        t = t[:m.start()] + drop(m[0])

    def paren(m):
        inner = m[1].strip()
        if STRONG.search(inner) or re.match(r"(?i)^(?:narrate|the author|continue your|write only)\b", inner):
            return drop(m[0])
        return m[0]                                                                  # an ordinary aside: enclose_narration() fixes the format
    t = re.sub(r"\(([^()\n]{3,400})\)", paren, t)

    def lead(m):   # 'Reply as Faith:' / 'As Crescent -' at the start: only when it names someone in this chat
        return drop(m[0]) if m["who"].lower() in labels or m["who"].split()[0].lower() in labels else m[0]
    for _ in range(2):
        t = LEAD_LABEL.sub(lead, t, count=1)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r" +([.,!?…])", r"\1", t)
    t = re.sub(r"(?m)^[ \t]+$", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip(), info


_SPAN = re.compile(r"\*\*[^*\n]+\*\*|\*[^*\n]+\*|\"[^\"\n]*\"|“[^”\n]*”")
_SENT = re.compile(r"(?<=[.!?…])\s+")


def _paren_to_narration(t):
    return re.sub(r"\(([^()\n]{3,})\)", lambda m: f"*{m[1].strip()}*", t)


_VOICE = re.compile(r"\b(?:i|i'm|i've|i'll|i'd|me|my|mine|myself|we|we're|we'll|we've|us|our|ours|you|you're|you'll|you've|you'd|your|yours|yourself|thou|thee|thy|thine|ye|let's|lets)\b", re.I)
_NARR_OPEN = re.compile(r"^(?:he|she|they|it|his|her|their|its|the|a|an|this|that|these|those|then|there|here|for|with|without|as|after|before|when|while|until|once|one|another|each|every|some|nothing|something|outside|inside|behind|beyond|across|above|below|around|far|several|no|silence|wind|rain|fire|light|shadows?)\b|^[a-z]+(?:ly|ing)\b", re.I)


def looks_like_action(sent):
    """A bare sentence with no quotes that reads as narration rather than speech: three or more words, nobody addressed or speaking
    in the first or second person, and it opens the way a description does ('His eyes narrow.', 'Slowly, he turns.', 'Rain taps the glass.')."""
    s = sent.strip().strip("*").strip()
    return len(s.split()) >= 3 and not s.endswith("?") and not _VOICE.search(s) and bool(_NARR_OPEN.match(s))


def enclose_narration(text, char="", user=()):
    """Put every non-dialogue passage between *asterisks*. Dialogue ("quoted" or plain first-person speech) is untouched.
    Deliberately conservative: a bare sentence counts as narration only when it starts with the character's or the user's
    NAME as its subject (not as an address like 'Faith, wait'), or is a (parenthetical aside)."""
    if not text:
        return text
    names = _names(char, user)
    head = re.compile(r"^(?:" + "|".join(re.escape(n) for n in names) + r")\b(?!\s*[,!?:;])") if names else None
    out_lines = []
    for line in _paren_to_narration(text).split("\n"):
        pieces, pos = [], 0
        for m in _SPAN.finditer(line):
            if m.start() > pos:
                pieces.append(("bare", line[pos:m.start()]))
            pieces.append(("keep", m[0]))
            pos = m.end()
        if pos < len(line):
            pieces.append(("bare", line[pos:]))
        built, buf = [], []

        def flush():
            if buf:
                built.append("*" + " ".join(buf).strip() + "*")
                buf.clear()
        for kind, s in pieces:
            if kind == "keep":
                flush()
                built.append(s)
                continue
            for sent in _SENT.split(s.strip()):
                if not sent.strip():
                    continue
                if (head and head.match(sent.strip())) or looks_like_action(sent):
                    buf.append(sent.strip().strip("*"))
                else:
                    flush()
                    built.append(sent.strip())
        flush()
        out_lines.append(" ".join(x for x in built if x))
    res = "\n".join(out_lines)
    return re.sub(r"\*\s+\*", " ", res).strip()   # '*a.* *b.*' -> one span
