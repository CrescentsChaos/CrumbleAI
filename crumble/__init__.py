"""Crumble: a local character-chat app for .gguf models.

Layout
    config.py     paths, shared state, character-sheet schema
    storage.py    characters, groups and chats on disk
    textutil.py   reply clean-up, repetition checks, JSON recovery
    rp/           the roleplay engine: dice, fights, romance, group turn-taking
    personality/  the personality engine: stable traits, dynamics, canon, consistency guard
    prompt.py     builds the messages the model sees
    llm.py        runs the model and the reply pipeline
    memory.py     mood, affection and long-term memory
    sharing.py    hosting for guests
    server.py     the HTTP server and API
    web.py + web/ the browser UI
    app.py        command line entry point
"""
