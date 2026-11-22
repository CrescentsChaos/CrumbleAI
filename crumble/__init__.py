"""Crumble: a local character-chat app for .gguf models.

Layout
    config.py     paths, shared state, character-sheet schema
    storage.py    characters, groups and chats on disk
    textutil.py   reply clean-up, repetition checks, JSON recovery
    rp/           the roleplay engine: skills (no dice), wounds and death, romance, group turn-taking
    story/        the living world: daily routines, story clock, weather, humour, varied endings, world events, conflict as story
    personality/  the personality engine: stable traits, dynamics, canon, consistency guard
    prompt.py     builds the messages the model sees
    llm.py        runs the model and the reply pipeline
    memory.py     mood, affection and long-term memory
    sharing.py    hosting for guests
    server.py     the HTTP server and API
    web.py + web/ the browser UI
    app.py        command line entry point
"""
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True   # no new __pycache__ folders are written
for _d in Path(__file__).resolve().parent.rglob("__pycache__"):   # and any old ones are removed at startup
    shutil.rmtree(_d, ignore_errors=True)
