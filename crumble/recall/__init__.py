"""Hierarchical memory: four layers, searched instead of pasted.

    store.py      the memory store inside a chat state: short-term, episodic, semantic, emotional
    lexicon.py    stemmer, event types, feelings (data)
    analyze.py    reads the latest message (people, topics, event, feeling), rates moments, finds stated facts
    retrieve.py   ranks every memory by relevance, recency and importance and injects only the most useful
    learn.py      updates memory after each reply, and after important events (one extra model call)

The rest of the app calls only the names exported here.
"""
from .learn import backfill, update
from .retrieve import DEPTH, rank, select, settings, short_term, view
from .store import ensure, placeholders, remove, resolve, touch

__all__ = ["DEPTH", "backfill", "ensure", "placeholders", "rank", "remove", "resolve", "select", "settings", "short_term", "touch", "update", "view"]
