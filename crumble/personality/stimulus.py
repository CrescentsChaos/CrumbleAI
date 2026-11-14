"""Reads what the user just did: tone, and whether it touches the character's triggers, boundaries, comforts or interests."""
import re

from . import lexicon as lx
from .profile import stem


def _norm(text):
    return (text or "").replace("’", "'").replace("“", '"').replace("”", '"').lower()


def tone(text):
    t = _norm(text)
    out = {}
    for k, pats in lx.STIM_RX.items():
        hits = [w for w, rx in pats if rx.search(t)]
        out[k] = round(min(1.0, max(hits) + .2 * (len(hits) - 1)), 2) if hits else 0.0
    return out


def _hits(kws, words):
    out = []
    for k in kws:
        if sum(1 for s in k["stems"] if s in words) >= k["need"]:
            out.append(k["text"])
    return out


def read(text, prof):
    """-> {'hostile': 0..1, ..., 'triggers': [...], 'boundary': [...], 'comforts': [...], 'likes': [...], 'tags': [...]}"""
    s = tone(text)
    spoken = re.sub(r"\*[^*\n]*\*", " ", _norm(text))      # keywords count in what is said, not in stage directions
    words = {stem(w) for w in re.findall(r"[a-z]{3,}", spoken + " " + _norm(text))}
    kw = prof["kw"] if prof else {}
    s["triggers"] = _hits(kw.get("triggers", []), words)
    s["boundary"] = _hits(kw.get("boundary", []), words)
    s["fears"] = _hits(kw.get("fears", []), words)
    s["dislikes"] = _hits(kw.get("dislikes", []), words)
    s["comforts"] = _hits(kw.get("comforts", []), words)
    s["likes"] = _hits(kw.get("likes", []), words)
    s["short"] = len((text or "").split()) <= 2
    s["tags"] = [k for k in ("hostile", "kind", "praise", "vulnerable", "challenge", "apology", "flirt", "dismissive") if s[k] >= .5]
    return s
