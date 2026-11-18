"""Identity, ownership and continuity: who is who, who said what, and what was really told.

    names.py    names, name corrections, genders, relations (pure parsing)
    claims.py   what the user said about their own life (verbatim, owner-tagged), retrieval, contradiction check
    ledger.py   the cast ledger built from sheet + persona + chat; relevance, topic change, nothing-on-record
    guard.py    structural checks on a finished reply (impersonation, speaking for the user, names, pronouns, facts)
    facts.py    grounding for the memory writers (no hallucinated or misattributed memories) and summary clean-up
"""
from .facts import make_guard, neutralize, sanitize_summary
from .guard import check
from . import claims
from .ledger import analyze, build, render_claims, render_who, roster, strip_characters, tail_notes, user_labels

__all__ = ["analyze", "build", "check", "make_guard", "neutralize", "render_claims", "render_who", "roster", "sanitize_summary", "strip_characters", "tail_notes", "user_labels"]
