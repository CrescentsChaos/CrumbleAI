"""Tiny text helpers shared by the identity modules."""
import re

ACTION = re.compile(r"\*[^*\n]*\*")
SENT = re.compile(r"(?<=[.!?…])[\"”')\]]*\s+|\n+")


def norm(t):
    return str(t or "").replace("’", "'").replace("“", '"').replace("”", '"')


def speech_only(t):
    """A chat message without its *actions* (roleplay narration is not a statement of fact)."""
    return re.sub(r"[ \t]+", " ", ACTION.sub(" ", norm(t))).strip()


def sentences(t):
    return [s.strip() for s in SENT.split(norm(t)) if s and s.strip()]


def word_in(name, text, flags=re.I):
    return bool(name) and bool(re.search(r"(?<![\w'])" + re.escape(name) + r"(?![\w])", text or "", flags))


def first_name(n):
    return (str(n or "").strip().split(" ") or [""])[0]
