"""Canon: what the character has already said about themselves in this chat. Small models forget their own
claims (a job, a dislike, a promise) and contradict them later; keeping a short list and checking replies
against it fixes most of that."""
import difflib
import re

from . import lexicon as lx
from .profile import stem

MAX = 30
LOVE = re.compile(r"\bI (?:really |absolutely |totally |do )?(?:love|adore|enjoy|like|prefer)\s+([^.!?\n]+)", re.I)
HATE = re.compile(r"\bI (?:really |absolutely |totally )?(?:hate|can't stand|cannot stand|despise|detest|dislike|don't like|do not like|never (?:eat|drink|touch))\s+([^.!?\n]+)", re.I)
NEVER = re.compile(r"\bI never\s+([^.!?\n]+)", re.I)
ALWAYS = re.compile(r"\bI (?:always|often|usually|every day)\s+([^.!?\n]+)", re.I)
AGE = re.compile(r"\bI(?:'m| am) (\d{2})\b(?! (?:minutes|hours|percent|%))", re.I)
NAME = re.compile(r"\bmy name(?: is|'s) ([A-Z][a-z]+)")
SOFTENED = re.compile(r"\b(?:used to|no longer|anymore|but now|changed my mind|didn't use to|wasn't|not anymore|but i do now)\b", re.I)


def _clean(text):
    t = re.sub(r"\*[^*\n]*\*", " ", text or "")
    t = re.sub(r"\([^)\n]*\)", " ", t)
    return t.replace("’", "'").replace("“", '"').replace("”", '"')


def is_ai_statement(s):
    return bool(lx.AI_HARD.search(s) or lx.AI_SOFT.search(s) or re.search(r"\b(?:ai\b|artificial intelligence|chatbot|bot\b|virtual assistant|language model|llm|computer program)\b", s, re.I))


def extract(text):
    """First-person statements about the self, worth remembering."""
    out = []
    for sent in re.split(r"(?<=[.!?…])\s+|\n+", _clean(text)):
        s = sent.strip(" \"'")
        if len(s) < 6 or _transient(s) or is_ai_statement(s):
            continue
        for rx in lx.CANON_PATTERNS:
            m = rx.search(s)
            if m:
                frag = m.group(0).strip(" ,;:-\"'")
                frag = re.sub(r"\s+", " ", frag)
                if 6 <= len(frag) <= 100 and not is_ai_statement(frag):
                    out.append(frag)
                break
    return out


def _transient(s):
    return bool(lx.TRANSIENT.search(s))


def merge(canon, new):
    """Add new lines, skipping near-duplicates; newest kept when over the cap."""
    canon = [str(x) for x in (canon or []) if str(x).strip() and not is_ai_statement(str(x))]
    for n in new:
        if is_ai_statement(n):
            continue
        low = n.lower()
        if any(difflib.SequenceMatcher(None, low, o.lower()).ratio() > .8 or low in o.lower() or o.lower() in low for o in canon):
            continue
        canon.append(n)
    return canon[-MAX:]


def _stems(s):
    return {stem(w) for w in re.findall(r"[a-z]{4,}", s.lower())}


def contradictions(text, canon):
    """[(established line, what the new reply says)] for the clear cases: love vs hate, never vs always, age, name."""
    found = []
    t = _clean(text)
    for sent in re.split(r"(?<=[.!?…])\s+|\n+", t):
        if SOFTENED.search(sent):
            continue
        for line in canon or []:
            pairs = ((LOVE, HATE), (HATE, LOVE), (NEVER, ALWAYS), (ALWAYS, NEVER))
            for old_rx, new_rx in pairs:
                mo, mn = old_rx.search(line), new_rx.search(sent)
                if mo and mn and _stems(mo.group(1)) & _stems(mn.group(1)):
                    found.append((line, sent.strip()[:90]))
            ao, an = AGE.search(line), AGE.search(sent)
            if ao and an and ao.group(1) != an.group(1):
                found.append((line, sent.strip()[:90]))
            no, nn = NAME.search(line), NAME.search(sent)
            if no and nn and no.group(1) != nn.group(1):
                found.append((line, sent.strip()[:90]))
    seen, out = set(), []
    for o, n in found:
        if (o, n) not in seen:
            seen.add((o, n))
            out.append((o, n))
    return out
