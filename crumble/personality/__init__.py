"""Personality engine: keeps a character behaving like themselves.

    lexicon.py     word lists
    profile.py     sheet -> stable traits, temperament, triggers, rules
    stimulus.py    reads what the user just did (tone, triggers, comforts)
    dynamics.py    personality-shaped mood and affection (bounded, inertial, grudges, time heals)
    canon.py       what the character has said about themselves, and contradiction checks
    voice.py       voice fingerprint and the consistency guard
    directives.py  the prompt text built from all of the above
    engine.py      the API the rest of the app uses
"""
from .engine import active, after_turn, check_reply, prepare, settings
from .profile import profile_for, public

__all__ = ["active", "after_turn", "check_reply", "prepare", "profile_for", "public", "settings"]
